"""What the parser has to get right, checked against the real files.

The interesting cases are not hypothetical -- they are all in
`supabase/questions` already: explanations with commas and brackets in them,
`''` for an apostrophe, a `--` comment carrying both above a board, umlauts, and
two file shapes that share a directory. So most of these tests parse the actual
tree and assert against what the SQL would have produced, rather than against a
fixture that can agree with a broken parser.

The counts are deliberately exact. A scanner that loses a board at the end of a
file, or splits one row into two, still parses -- it just parses wrong, and only
a total catches that.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.questions.apply import default_files
from tools.questions.parse import ParseError, parse

REPO_ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = REPO_ROOT / "supabase" / "questions"

TEXT_FILES = sorted(
    path
    for path in QUESTIONS.glob("*.sql")
    if not path.name.startswith(("subject-", "bilder-"))
)
PICTURE_FILES = sorted(QUESTIONS.glob("bilder-*.sql"))


def test_every_file_in_the_tree_parses():
    for path in default_files():
        parse(path)


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda p: p.name)
def test_text_files_hold_twenty_boards(path: Path):
    """Every text file but the first batch is twenty questions by convention."""
    boards = parse(path).boards
    assert len(boards) == (10 if path.name == "batch-01.sql" else 20)


@pytest.mark.parametrize("path", TEXT_FILES + PICTURE_FILES, ids=lambda p: p.name)
def test_every_board_has_two_fakes(path: Path):
    """`tools/fakes/check.py` enforces this on the file; this proves it survives
    being read back out."""
    for board in parse(path).boards:
        assert len(board.fakes) == 2, board.slug


@pytest.mark.parametrize("path", TEXT_FILES + PICTURE_FILES, ids=lambda p: p.name)
def test_positions_never_collide(path: Path):
    """Pairs and fakes share `position`, and the file numbers the fakes after
    the pairs precisely so the two sets do not overlap."""
    for board in parse(path).boards:
        positions = [pair.position for pair in board.pairs] + [
            fake.position for fake in board.fakes
        ]
        assert len(set(positions)) == len(positions), board.slug
        assert positions == sorted(positions), board.slug


@pytest.mark.parametrize("path", TEXT_FILES + PICTURE_FILES, ids=lambda p: p.name)
def test_no_fake_repeats_an_answer(path: Path):
    """`items_quiz_id_label_key` would refuse it, halfway through a run."""
    for board in parse(path).boards:
        answers = {pair.answer for pair in board.pairs}
        assert not answers & {fake.label for fake in board.fakes}, board.slug


def test_slugs_are_unique_across_the_whole_tree():
    """`quizzes.slug` is unique, so a slug written twice is a run that stops."""
    seen: dict[str, str] = {}
    for path in default_files():
        for board in parse(path).boards:
            assert board.slug not in seen, f"{board.slug} in {path.name} and {seen[board.slug]}"
            seen[board.slug] = path.name


def test_picture_boards_carry_their_licence():
    """`categories_image_is_complete` refuses a file without a licence, and a
    board that loses its image columns in parsing would insert as plain text --
    which serves the category label, and the label names the answer."""
    for path in PICTURE_FILES:
        for board in parse(path).boards:
            assert board.category_kind == "image", board.slug
            for pair in board.pairs:
                assert pair.image["image_file"], (board.slug, pair.label)
                assert pair.image["image_licence"], (board.slug, pair.label)


def test_subject_files_and_seed_agree_on_the_subjects():
    """Together the files describe the eleven gebiete the pool is dealt from.

    A slug may be declared twice on purpose: `subject-videospiele.sql` exists
    for a database that is already running, and `seed.sql` carries the same row
    for a fresh `db reset`. The two have to say the same thing -- a subject
    whose name or position depended on which file reached the database first
    would order the pool differently on a reset than in production.
    """
    declared: dict[str, list] = {}
    for path in default_files():
        for subject in parse(path).subjects:
            declared.setdefault(subject.slug, []).append(subject)

    for slug, rows in declared.items():
        assert len(set(rows)) == 1, f"{slug} is declared two different ways: {rows}"

    assert "unnuetzes-wissen" in declared
    assert {rows[0].position for rows in declared.values()} == set(range(1, len(declared) + 1))


# ---------------------------------------------------------------------------
# The scanning itself, on the shapes that are easy to get wrong
# ---------------------------------------------------------------------------


def _spec(body: str) -> str:
    return textwrap.dedent(
        f"""\
        with spec (subject_slug, slug, title, description, difficulty,
                   source_title, source_url, pairs, fakes) as (
            values
        {body}
        ),
        new_quizzes as (
            insert into quizzes (subject_id, slug, title, description,
                                 difficulty, source_title, source_url, origin)
            select s.id, sp.slug, sp.title, sp.description,
                   sp.difficulty::difficulty, sp.source_title, sp.source_url, 'seed'
              from spec sp
              join subjects s on s.slug = sp.subject_slug
             where not exists (select 1 from quizzes q where q.slug = sp.slug)
            returning id, slug
        )
        select 1;
        """
    )


def test_commas_brackets_and_quotes_inside_prose(tmp_path: Path):
    """One board whose text carries every character that splits a row."""
    path = tmp_path / "awkward.sql"
    path.write_text(
        _spec(
            """\
    -- A comment with a comma, a (bracket) and an apostrophe's quote.
    ('geografie', 'awkward', 'Titel (mit Klammern)',
     'Frage, mit Komma?',
     'easy', 'Quelle', 'https://example.org/a',
     '[["Kategorie, mit Komma", "Antwort (geklammert)", "Erklärung: ein Apostroph''s, ein ; und ein -- Strich."]]'::jsonb,
     '[["Fake, auch mit Komma", "Weil''s dazugehört."]]'::jsonb)"""
        ),
        encoding="utf-8",
    )

    (board,) = parse(path).boards
    assert board.title == "Titel (mit Klammern)"
    assert board.pairs[0].label == "Kategorie, mit Komma"
    assert board.pairs[0].answer == "Antwort (geklammert)"
    assert board.pairs[0].explanation == "Erklärung: ein Apostroph's, ein ; und ein -- Strich."
    assert board.fakes[0].label == "Fake, auch mit Komma"
    assert board.fakes[0].explanation == "Weil's dazugehört."
    assert board.fakes[0].position == 2


def test_null_description_is_none(tmp_path: Path):
    path = tmp_path / "nulls.sql"
    path.write_text(
        _spec(
            """\
    ('musik', 'bare', 'Titel',
     null,
     'hard', null, null,
     '[["A", "B"]]'::jsonb,
     '[["C", "D"]]'::jsonb)"""
        ),
        encoding="utf-8",
    )

    (board,) = parse(path).boards
    assert board.description is None
    assert board.source_url is None
    assert board.pairs[0].explanation is None


def test_a_file_claiming_another_origin_is_refused(tmp_path: Path):
    """`origin` is what makes `delete ... where origin = 'seed'` safe to type."""
    path = tmp_path / "wrong-origin.sql"
    path.write_text(
        _spec(
            """\
    ('musik', 'x', 'T', 'D', 'easy', 'S', 'https://example.org/x',
     '[["A", "B"]]'::jsonb, '[["C", "D"]]'::jsonb)"""
        ).replace("sp.source_url, 'seed'", "sp.source_url, 'ingest'"),
        encoding="utf-8",
    )

    with pytest.raises(ParseError, match="origin"):
        parse(path)


def test_a_row_short_of_a_column_is_refused(tmp_path: Path):
    """The failure that matters: a row silently read as the wrong columns puts
    the source URL in `pairs` and inserts nothing anyone would notice."""
    path = tmp_path / "short.sql"
    path.write_text(
        _spec("""    ('musik', 'x', 'T', 'D', 'easy', 'S', 'https://example.org/x')"""),
        encoding="utf-8",
    )

    with pytest.raises(ParseError, match="value"):
        parse(path)
