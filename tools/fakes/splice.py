"""Splice a `fakes` column into the hand-written question files.

The text files under supabase/questions all share one shape: a `spec` CTE of
board rows, then a fixed footer that flattens the pairs and inserts them. This
adds the fakes to both halves -- the literal on each board, and the CTE plus
insert that stores them -- and it is written to be run once per file and then
be a no-op, so a half-converted tree can be finished by running it again.

Usage:  python tools/fakes/splice.py <file.sql> <fakes.json>

`fakes.json` maps a board slug to a list of [label, explanation] pairs.
"""

import json
import re
import sys
from pathlib import Path

SPEC_HEAD_OLD = """with spec (subject_slug, slug, title, description, difficulty,
           source_title, source_url, pairs) as ("""

SPEC_HEAD_NEW = """with spec (subject_slug, slug, title, description, difficulty,
           source_title, source_url, pairs, fakes) as ("""

FOOTER_OLD = """new_categories as (
    insert into categories (quiz_id, label, position)
    select quiz_id, label, position from flat
    returning id, quiz_id, label
)

insert into items (quiz_id, category_id, label, position, explanation)
select f.quiz_id, c.id, f.answer, f.position, f.explanation
  from flat f
  join new_categories c
    on c.quiz_id = f.quiz_id
   and c.label = f.label;"""

FOOTER_NEW = """-- The answers that belong to no category. Numbered after the pairs so the two
-- sets never collide on `position`, though nothing reads it for a fake: the
-- pool is shuffled before a player sees it, and the review lists fakes on their
-- own rather than in board order.
fakes as (
    select q.id                                         as quiz_id,
           k.value ->> 0                                as label,
           k.value ->> 1                                as explanation,
           (jsonb_array_length(sp.pairs) + k.ord)::int  as position
      from spec sp
      join new_quizzes q on q.slug = sp.slug
     cross join lateral jsonb_array_elements(sp.fakes) with ordinality k(value, ord)
),

new_categories as (
    insert into categories (quiz_id, label, position)
    select quiz_id, label, position from flat
    returning id, quiz_id, label
),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select f.quiz_id, c.id, f.answer, f.position, f.explanation
      from flat f
      join new_categories c
        on c.quiz_id = f.quiz_id
       and c.label = f.label
    returning id
)

-- Same table, `category_id` left null. Both inserts run in the one statement,
-- so `items_quiz_id_label_key` still sees the pairs above: a fake written to
-- repeat an answer already on its own board fails the file rather than becoming
-- a second row nobody can tell apart.
insert into items (quiz_id, category_id, label, position, explanation)
select k.quiz_id, null, k.label, k.position, k.explanation
  from fakes k;"""

BOARD_START = re.compile(r"^    \('([a-z0-9-]+)', '([a-z0-9-]+)',", re.M)
PAIRS_END = "]]'::jsonb)"

# What a board that already carries its fakes looks like: the pairs array closed
# with a comma rather than the paren, and a second literal under it. Checked
# before splicing, because on such a board `PAIRS_END` finds the *fakes*
# terminator and appending there would give the board four of them.
SPLICED = "'::jsonb,\n     '["


def as_literal(pairs: list[list[str]]) -> str:
    """The jsonb literal for one board's fakes, indented to match the pairs.

    The doubled apostrophe is not decoration. The written questions use the
    typographic one (Link's Awakening), but nothing stops a fake from carrying
    the ASCII one, and a single unescaped quote closes the literal mid-word and
    leaves the rest of the file as syntax.
    """
    rows = [
        "[" + ", ".join(json.dumps(part, ensure_ascii=False) for part in pair) + "]"
        for pair in pairs
    ]
    body = ",\n       ".join(rows)
    return "'[" + body.replace("'", "''") + "]'::jsonb"


def splice(text: str, fakes: dict[str, list[list[str]]]) -> tuple[str, list[str]]:
    if SPEC_HEAD_OLD not in text and SPEC_HEAD_NEW not in text:
        raise SystemExit("unrecognised spec header")

    text = text.replace(SPEC_HEAD_OLD, SPEC_HEAD_NEW)
    if FOOTER_OLD in text:
        text = text.replace(FOOTER_OLD, FOOTER_NEW)
    elif FOOTER_NEW not in text:
        raise SystemExit("unrecognised footer")

    starts = [(m.start(), m.group(2)) for m in BOARD_START.finditer(text)]
    done = []
    # Back to front, so an edit never moves an offset still to be used.
    for start, slug in reversed(starts):
        end = text.index(PAIRS_END, start) + len(PAIRS_END) - 1
        if SPLICED in text[start:end]:
            continue  # already carries its fakes; `end` found their terminator
        if slug not in fakes:
            continue
        text = text[:end] + ",\n     " + as_literal(fakes[slug]) + text[end:]
        done.append(slug)

    return text, done


def main() -> None:
    path, fakes_path = Path(sys.argv[1]), Path(sys.argv[2])
    fakes = json.loads(fakes_path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")

    slugs = {m.group(2) for m in BOARD_START.finditer(text)}
    missing = sorted(slugs - set(fakes))
    if missing:
        raise SystemExit(f"no fakes written for: {', '.join(missing)}")

    out, done = splice(text, fakes)
    path.write_text(out, encoding="utf-8")
    print(f"{path.name}: {len(done)} board(s) spliced")


if __name__ == "__main__":
    main()
