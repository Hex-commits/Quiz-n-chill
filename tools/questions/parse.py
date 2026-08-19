"""Read a hand-written question file without a Postgres to run it in.

`supabase/questions/*.sql` is the source of truth for every hand-written
question, and the only thing that has ever executed it is `psql`. That is fine
until the database you need to reach is a hosted project: the CLI pushes
migrations and nothing else, `seed.sql` never runs against a hosted project, and
a connection string wants the database password rather than the service-role key
that is already in `.env`.

So this reads the files instead, and `apply.py` writes the result through
PostgREST. Running the SQL itself is still the more faithful thing to do wherever
a `psql` is available -- see the note at the top of `apply.py`.

Two shapes are parsed, because the files come in two:

* **spec** -- `supabase/seed.sql` and every text file: one `with spec (...) as
  (values ...)` CTE holding every board on the file, pairs and fakes as `jsonb`
  literals.
* **picture** -- `bilder-*.sql`: one statement per board, pairs and fakes as
  their own `values` CTEs, with the Commons columns alongside.

The parsing is a scanner rather than a regex over the whole file. Explanations
are German prose containing commas, parentheses and doubled quotes, and the `--`
comment above a board can contain any of them too; matching brackets while
knowing what is inside a string literal is the only way to split those rows that
does not eventually cut one in half.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

HAND_WRITTEN = "seed"
"""What these files write into `quizzes.origin`.

Asserted rather than assumed. `origin` is what makes `delete from quizzes where
origin = ...` safe to type, and a file that disagrees is one this parser has not
seen -- better a refusal than a pool that misreports who wrote it.
"""

IMAGE_COLUMNS = ("image_file", "image_credit", "image_licence", "image_licence_url")


class ParseError(RuntimeError):
    """A file is not in a shape this parser knows. Carries the file and why."""


@dataclass(frozen=True)
class Fake:
    """An answer in the pool that belongs to no category."""

    label: str
    explanation: str | None
    position: int


@dataclass(frozen=True)
class Pair:
    """One category and the single answer that belongs to it."""

    label: str
    answer: str
    explanation: str | None
    position: int
    image: dict[str, str | None] | None = None


@dataclass(frozen=True)
class Board:
    """One quiz, with everything needed to write it."""

    subject_slug: str
    slug: str
    title: str
    description: str | None
    difficulty: str
    source_title: str | None
    source_url: str | None
    pairs: tuple[Pair, ...]
    fakes: tuple[Fake, ...]
    category_kind: str = "text"
    origin: str = HAND_WRITTEN


@dataclass(frozen=True)
class Subject:
    """A row of `subjects`, from a `subject-*.sql` file or from `seed.sql`."""

    slug: str
    name: str
    description: str | None
    position: int


# ---------------------------------------------------------------------------
# Scanning SQL: strings, comments, brackets
# ---------------------------------------------------------------------------


def _end_of_string(sql: str, i: int) -> int:
    """Index just past the string literal opening at `i`.

    `''` inside a literal is one quote, not the end of it -- the files use it
    in every other explanation.
    """
    i += 1
    while i < len(sql):
        if sql[i] == "'":
            if sql.startswith("''", i):
                i += 2
                continue
            return i + 1
        i += 1
    raise ParseError("unterminated string literal")


def _end_of_comment(sql: str, i: int) -> int:
    end = sql.find("\n", i)
    return len(sql) if end < 0 else end + 1


def _step(sql: str, i: int) -> int | None:
    """Skip a string or a comment starting at `i`, or None for neither.

    The one place that knows what is *not* structure, so every scanner below
    agrees about it.
    """
    if sql[i] == "'":
        return _end_of_string(sql, i)
    if sql.startswith("--", i):
        return _end_of_comment(sql, i)
    return None


def _matching(sql: str, opened: int) -> int:
    """Index of the bracket closing the one at `opened`."""
    depth = 0
    i = opened
    while i < len(sql):
        skip = _step(sql, i)
        if skip is not None:
            i = skip
            continue
        if sql[i] in "([":
            depth += 1
        elif sql[i] in ")]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ParseError(f"unbalanced brackets from offset {opened}")


def _split_top(sql: str, separator: str = ",") -> list[str]:
    """Split on `separator` at bracket depth zero."""
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(sql):
        skip = _step(sql, i)
        if skip is not None:
            i = skip
            continue
        char = sql[i]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(sql[start:i])
            start = i + 1
        i += 1
    parts.append(sql[start:])
    return [part for part in parts if part.strip()]


def _tuples(sql: str) -> list[str]:
    """The inside of every top-level `(...)` group, in order."""
    rows: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(sql):
        skip = _step(sql, i)
        if skip is not None:
            i = skip
            continue
        if sql[i] in "([":
            if depth == 0:
                start = i
            depth += 1
        elif sql[i] in ")]":
            depth -= 1
            if depth == 0:
                rows.append(sql[start + 1 : i])
        i += 1
    if depth:
        raise ParseError("unbalanced brackets in a values list")
    return rows


_CAST = re.compile(r"::\s*[a-zA-Z_]\w*\s*$")


def _literal(text: str):
    """One SQL value as Python: a string, an integer, or None for NULL.

    The cast is stripped first, so `'medium'::difficulty` and `'[]'::jsonb` read
    as what they quote. A cast can only follow the closing quote, so this never
    bites into a literal that happens to end in `::jsonb`.
    """
    text = _CAST.sub("", text.strip()).strip()
    if not text:
        raise ParseError("empty value in a values list")
    if text.lower() == "null":
        return None
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise ParseError(f"value is not a closed string literal: {text[:40]}")
        return text[1:-1].replace("''", "'")
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def _columns(sql: str, opened: int) -> tuple[list[str], int]:
    """The column names in the `(...)` at `opened`, and where it closes."""
    closed = _matching(sql, opened)
    names = [name.strip() for name in _split_top(sql[opened + 1 : closed])]
    return names, closed


_AS_OPEN = re.compile(r"\s*as\s*\(", re.I)
_VALUES = re.compile(r"^\s*values\b", re.I)


def _values_rows(sql: str, after: int) -> list[str]:
    """The rows of the `as ( values ... )` block that follows offset `after`."""
    opening = _AS_OPEN.match(sql, after)
    if not opening:
        raise ParseError("expected `as (` after a CTE's column list")
    body_open = opening.end() - 1
    body = sql[body_open + 1 : _matching(sql, body_open)]
    stripped, replaced = _VALUES.subn("", body, count=1)
    if not replaced:
        raise ParseError("expected `values` inside a CTE")
    return _tuples(stripped)


def _rows(sql: str, keyword: re.Pattern[str]) -> list[dict]:
    """Every row of the first `<keyword> (cols) as (values ...)` CTE, by name."""
    head = keyword.search(sql)
    if not head:
        return []
    names, closed = _columns(sql, head.end() - 1)
    rows = []
    for row in _values_rows(sql, closed + 1):
        fields = _split_top(row)
        if len(fields) != len(names):
            raise ParseError(
                f"row has {len(fields)} value(s) for {len(names)} column(s): {row[:60]}"
            )
        rows.append({name: _literal(field) for name, field in zip(names, fields)})
    return rows


# ---------------------------------------------------------------------------
# The spec shape: seed.sql and every text question file
# ---------------------------------------------------------------------------

_SPEC = re.compile(r"\bwith\s+spec\s*\(", re.I)
_ORIGIN = re.compile(r"sp\.source_url\s*,\s*'([a-z]+)'", re.I)


def _fakes_from_json(raw, offset: int) -> tuple[Fake, ...]:
    """`[[label, explanation], ...]`, numbered after the pairs.

    The offset matches `jsonb_array_length(sp.pairs) + k.ord` in the files: the
    two sets share the `position` column and must not collide on it.
    """
    return tuple(
        Fake(
            label=fake[0],
            explanation=fake[1] if len(fake) > 1 else None,
            position=offset + ordinal,
        )
        for ordinal, fake in enumerate(raw or [], start=1)
    )


def _spec_boards(sql: str) -> list[Board]:
    head = _SPEC.search(sql)
    if not head:
        return []

    names, closed = _columns(sql, head.end() - 1)
    required = {"subject_slug", "slug", "title", "description", "difficulty", "pairs"}
    if not required <= set(names):
        raise ParseError(f"spec is missing {sorted(required - set(names))}")

    origin = _ORIGIN.search(sql)
    if origin and origin.group(1) != HAND_WRITTEN:
        raise ParseError(f"file writes origin={origin.group(1)!r}, expected {HAND_WRITTEN!r}")

    boards = []
    for row in _values_rows(sql, closed + 1):
        fields = _split_top(row)
        if len(fields) != len(names):
            raise ParseError(f"board has {len(fields)} value(s) for {len(names)} column(s)")
        values = dict(zip(names, fields))

        pairs = tuple(
            Pair(
                label=pair[0],
                answer=pair[1],
                explanation=pair[2] if len(pair) > 2 else None,
                position=position,
            )
            for position, pair in enumerate(json.loads(_literal(values["pairs"])), start=1)
        )
        fakes = json.loads(_literal(values["fakes"])) if "fakes" in values else []

        boards.append(
            Board(
                subject_slug=_literal(values["subject_slug"]),
                slug=_literal(values["slug"]),
                title=_literal(values["title"]),
                description=_literal(values["description"]),
                difficulty=_literal(values["difficulty"]),
                source_title=_literal(values.get("source_title", "null")),
                source_url=_literal(values.get("source_url", "null")),
                pairs=pairs,
                fakes=_fakes_from_json(fakes, len(pairs)),
            )
        )
    return boards


# ---------------------------------------------------------------------------
# The picture shape: bilder-*.sql, one statement per board
# ---------------------------------------------------------------------------

_QUIZ_INSERT = re.compile(r"\binsert\s+into\s+quizzes\s*\(", re.I)
_SELECT = re.compile(r"\bselect\b", re.I)
_FROM = re.compile(r"\bfrom\b", re.I)
_SUBJECT_SLUG = re.compile(r"\bs\.slug\s*=\s*'([^']*)'", re.I)
_PAIRS_CTE = re.compile(r"\bpairs\s*\(", re.I)
_FAKES_CTE = re.compile(r"\bfakes\s*\(", re.I)
_END_OF_SELECT = re.compile(r"\b(from|where)\b", re.I)


def _select_list(sql: str, after: int) -> list[str]:
    """The expressions of the `select` following `after`.

    Ends at its own `from`, or at `where` for a select that reads no table --
    which is the shape of `subject-*.sql`, a bare row guarded by `where not
    exists`. Depth-aware, because that guard carries a nested `from` of its own
    that is not the end of this list.
    """
    select = _SELECT.search(sql, after)
    if not select:
        raise ParseError("no select to read values from")
    depth = 0
    i = select.end()
    while i < len(sql):
        skip = _step(sql, i)
        if skip is not None:
            i = skip
            continue
        if sql[i] in "([":
            depth += 1
        elif sql[i] in ")]":
            depth -= 1
        elif depth == 0 and _END_OF_SELECT.match(sql, i):
            return _split_top(sql[select.end() : i])
        i += 1
    raise ParseError("select ends without `from` or `where`")


def _statements(sql: str) -> list[str]:
    """Split a file into statements on top-level semicolons."""
    return [part for part in _split_top(sql, ";") if part.strip()]


def _picture_board(statement: str) -> Board | None:
    head = _QUIZ_INSERT.search(statement)
    if not head:
        return None

    names, closed = _columns(statement, head.end() - 1)
    values = _select_list(statement, closed + 1)
    if len(values) != len(names):
        raise ParseError(f"quiz insert has {len(values)} value(s) for {len(names)} column(s)")
    quiz = dict(zip(names, values))

    subject = _SUBJECT_SLUG.search(statement)
    if not subject:
        raise ParseError("quiz insert does not name a subject slug")

    origin = _literal(quiz.get("origin", f"'{HAND_WRITTEN}'"))
    if origin != HAND_WRITTEN:
        raise ParseError(f"file writes origin={origin!r}, expected {HAND_WRITTEN!r}")

    pairs = tuple(
        Pair(
            label=row["label"],
            answer=row["answer"],
            explanation=row.get("explanation"),
            position=row["position"],
            image={column: row.get(column) for column in IMAGE_COLUMNS},
        )
        for row in _rows(statement, _PAIRS_CTE)
    )
    fakes = tuple(
        Fake(label=row["label"], explanation=row.get("explanation"), position=row["position"])
        for row in _rows(statement, _FAKES_CTE)
    )

    return Board(
        subject_slug=subject.group(1),
        slug=_literal(quiz["slug"]),
        title=_literal(quiz["title"]),
        description=_literal(quiz.get("description", "null")),
        difficulty=_literal(quiz["difficulty"]),
        source_title=_literal(quiz.get("source_title", "null")),
        source_url=_literal(quiz.get("source_url", "null")),
        pairs=pairs,
        fakes=fakes,
        category_kind=_literal(quiz.get("category_kind", "'text'")),
        origin=origin,
    )


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

_SUBJECT_INSERT = re.compile(r"\binsert\s+into\s+subjects\s*\(", re.I)
_VALUES_KEYWORD = re.compile(r"\s*values\b", re.I)


def _subjects(sql: str) -> list[Subject]:
    """Every subject a file inserts, in either shape.

    `seed.sql` writes them as a `values` list; a `subject-*.sql` file, written
    for a database that is already running, writes one `select ... where not
    exists` so that a second run does nothing.
    """
    found = []
    for statement in _statements(sql):
        head = _SUBJECT_INSERT.search(statement)
        if not head:
            continue
        names, closed = _columns(statement, head.end() - 1)

        keyword = _VALUES_KEYWORD.match(statement, closed + 1)
        rows = (
            _tuples(statement[keyword.end() :])
            if keyword
            else [",".join(_select_list(statement, closed + 1))]
        )

        for row in rows:
            fields = _split_top(row)
            if len(fields) != len(names):
                raise ParseError(f"subject row has {len(fields)} value(s) for {len(names)}")
            values = {name: _literal(field) for name, field in zip(names, fields)}
            found.append(
                Subject(
                    slug=values["slug"],
                    name=values["name"],
                    description=values.get("description"),
                    position=values.get("position") or 0,
                )
            )
    return found


# ---------------------------------------------------------------------------
# What callers use
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Parsed:
    path: Path
    subjects: tuple[Subject, ...]
    boards: tuple[Board, ...]


def parse(path: Path) -> Parsed:
    """Everything one `.sql` file would write, whichever shape it is in."""
    sql = path.read_text(encoding="utf-8")
    try:
        boards = _spec_boards(sql) or [
            board
            for statement in _statements(sql)
            if (board := _picture_board(statement)) is not None
        ]
        return Parsed(path=path, subjects=tuple(_subjects(sql)), boards=tuple(boards))
    except ParseError as exc:
        raise ParseError(f"{path.name}: {exc}") from exc
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise ParseError(f"{path.name}: {exc}") from exc
