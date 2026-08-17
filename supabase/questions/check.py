"""Validate supabase/questions/batch-*.sql against the rules the pipeline enforces.

Reads the SQL rather than the database, so it runs with nothing booted. Every
check here mirrors tools/ingest/domain/validate.py plus the column constraints
in the migrations.

Usage: python checkbatch.py <file.sql> [...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SUBJECTS = {
    "geografie",
    "geschichte",
    "naturwissenschaft",
    "kunst-kultur",
    "sport",
    "technik",
    "musik",
    "film-fernsehen",
    "essen-trinken",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_PAIRS, MAX_PAIRS = 10, 14
MAX_ITEM_WORDS = 4
MAX_EXPLANATION = 160
DIFFICULTIES = {"easy", "medium", "hard"}

FIELDS = (
    "subject_slug",
    "slug",
    "title",
    "description",
    "difficulty",
    "source_title",
    "source_url",
    "pairs",
)


def literals(sql: str) -> list[str]:
    """Every single-quoted string in `sql`, in order, with '' unescaped.

    A hand-rolled scan rather than a regex: line comments hold apostrophes and
    string bodies hold '--', so neither can be stripped without tracking the
    other.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        char = sql[i]
        if char == "-" and sql.startswith("--", i):
            i = sql.find("\n", i)
            if i == -1:
                break
        elif char == "'":
            i += 1
            start = i
            buffer: list[str] = []
            while i < n:
                if sql[i] == "'":
                    if sql.startswith("''", i):
                        buffer.append(sql[start:i] + "'")
                        i += 2
                        start = i
                        continue
                    break
                i += 1
            buffer.append(sql[start:i])
            out.append("".join(buffer))
            i += 1
        else:
            i += 1
    return out


def records(path: Path) -> list[dict]:
    sql = path.read_text(encoding="utf-8")
    # The spec CTE, not the `insert into subjects ... values` block seed.sql
    # opens with.
    _, _, spec = sql.partition("pairs) as (")
    head, _, body = spec.partition("values")
    values, _, _ = body.partition("\n),")
    strings = literals(values)
    if len(strings) % len(FIELDS):
        print(f"{path.name}: {len(strings)} literals is not a multiple of {len(FIELDS)}")
    return [
        dict(zip(FIELDS, strings[at : at + len(FIELDS)]))
        for at in range(0, len(strings) - len(FIELDS) + 1, len(FIELDS))
    ]


def check(record: dict, seen_slugs: dict[str, str], where: str) -> list[str]:
    problems: list[str] = []
    slug = record["slug"]

    if record["subject_slug"] not in SUBJECTS:
        problems.append(f"unknown subject {record['subject_slug']!r}")
    if not SLUG_RE.match(slug):
        problems.append(f"slug {slug!r} is not url-safe")
    if slug in seen_slugs:
        problems.append(f"slug {slug!r} already used in {seen_slugs[slug]}")
    if record["difficulty"] not in DIFFICULTIES:
        problems.append(f"difficulty {record['difficulty']!r}")
    if not record["title"].strip() or not record["description"].strip():
        problems.append("empty title or description")
    if not record["source_url"].startswith("http"):
        problems.append(f"source_url {record['source_url']!r}")

    try:
        pairs = json.loads(record["pairs"])
    except json.JSONDecodeError as error:
        return problems + [f"pairs is not valid JSON: {error}"]

    if not MIN_PAIRS <= len(pairs) <= MAX_PAIRS:
        problems.append(f"{len(pairs)} pairs, playable range is {MIN_PAIRS}-{MAX_PAIRS}")

    labels = [p[0].strip() for p in pairs]
    answers = [p[1].strip() for p in pairs]
    explanations = [p[2] if len(p) > 2 else "" for p in pairs]

    if any(len(p) != 3 for p in pairs):
        problems.append("a pair does not have exactly three parts")
    for name, values in (("category", labels), ("answer", answers)):
        folded = [v.casefold() for v in values]
        repeated = sorted({v for v in folded if folded.count(v) > 1})
        if repeated:
            problems.append(f"repeated {name}: {repeated}")
        if any(not v for v in values):
            problems.append(f"empty {name}")

    clash = {a.casefold() for a in answers} & {l.casefold() for l in labels}
    if clash:
        problems.append(f"used as both category and answer: {sorted(clash)}")

    long_answers = [a for a in answers if len(a.split()) > MAX_ITEM_WORDS]
    if long_answers:
        problems.append(f"answers over {MAX_ITEM_WORDS} words: {long_answers}")

    long_explanations = [e for e in explanations if len(e) > MAX_EXPLANATION]
    if long_explanations:
        problems.append(
            f"explanations over {MAX_EXPLANATION} chars: "
            + ", ".join(f"{len(e)}: {e[:40]}..." for e in long_explanations)
        )
    if any(not e.strip() for e in explanations):
        problems.append("an explanation is empty")

    seen_slugs.setdefault(slug, where)
    return problems


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    seen: dict[str, str] = {}
    seed_sql = repo / "supabase" / "seed.sql"
    if seed_sql.exists():
        for record in records(seed_sql):
            if SLUG_RE.match(record.get("slug", "")):
                seen.setdefault(record["slug"], "seed.sql")

    failed = 0
    counts: dict[str, int] = {}
    total = 0
    for name in sys.argv[1:]:
        path = Path(name)
        rows = records(path)
        for record in rows:
            total += 1
            counts[record["subject_slug"]] = counts.get(record["subject_slug"], 0) + 1
            problems = check(record, seen, path.name)
            if problems:
                failed += 1
                print(f"\n{path.name}  {record['slug']}")
                for problem in problems:
                    print(f"    - {problem}")
        print(f"{path.name}: {len(rows)} questions")

    print(f"\n{total} questions checked, {failed} with problems")
    print("per subject: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
