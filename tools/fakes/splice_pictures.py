"""Splice a `fakes` CTE into the picture-question files.

The picture files have a different shape from the text ones: one whole
statement per board rather than one row in a shared `spec`, because each
category carries a photograph with its licence. So the fakes go in as their own
`values` list inside each statement rather than as a column on a spec row.

What is stored is identical to the text files -- an item with a null
`category_id`. A picture board's answers are words like every other board's;
only its categories are pictures. So a fake here is a word too, and nothing
about the licence handling is touched.

Usage:  python tools/fakes/splice_pictures.py <file.sql> <fakes.json>
"""

import json
import re
import sys
from pathlib import Path

STATEMENT = "with new_quiz as ("
SLUG = re.compile(r"select s\.id, '([a-z0-9-]+)',")

CATEGORIES_HEAD = """new_categories as ("""

FOOTER_OLD = """)
insert into items (quiz_id, category_id, label, position, explanation)
select c.quiz_id, c.id, p.answer, p.position, p.explanation
  from new_categories c
  join pairs p on p.label = c.label;"""

FOOTER_NEW = """),

paired as (
    insert into items (quiz_id, category_id, label, position, explanation)
    select c.quiz_id, c.id, p.answer, p.position, p.explanation
      from new_categories c
      join pairs p on p.label = c.label
    returning id
)

-- The answers that belong to no photograph. `new_quiz` is empty when the slug
-- was already there, so the cross join yields nothing and the file stays
-- re-runnable exactly as before.
insert into items (quiz_id, category_id, label, position, explanation)
select q.id, null, f.label, f.position, f.explanation
  from new_quiz q cross join fakes f;"""


def fakes_cte(pairs: list[list[str]], first_position: int) -> str:
    rows = []
    for offset, (label, explanation) in enumerate(pairs):
        rows.append(
            "    ('%s', '%s', %d)"
            % (label.replace("'", "''"), explanation.replace("'", "''"),
               first_position + offset)
        )
    return "fakes (label, explanation, position) as (\n    values\n" + ",\n".join(rows) + "\n),\n"


def statements(text: str):
    """Each board's statement, as (start, end) offsets."""
    starts = [m.start() for m in re.finditer(re.escape(STATEMENT), text)]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(text)
        yield start, end


def main() -> None:
    path, fakes_path = Path(sys.argv[1]), Path(sys.argv[2])
    fakes = json.loads(fakes_path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")

    done = []
    # Back to front, so an edit never moves an offset still to be used.
    for start, end in reversed(list(statements(text))):
        board = text[start:end]
        slug_match = SLUG.search(board)
        if slug_match is None:
            raise SystemExit(f"no slug found in statement at {start}")
        slug = slug_match.group(1)
        if "fakes (label, explanation, position)" in board:
            continue  # already spliced
        if slug not in fakes:
            raise SystemExit(f"no fakes written for: {slug}")

        # Number the fakes after the last pair, so the two sets never collide.
        last = max(int(n) for n in re.findall(r", (\d+)\),?\n", board))
        board = board.replace(
            CATEGORIES_HEAD,
            fakes_cte(fakes[slug], last + 1) + CATEGORIES_HEAD,
            1,
        )
        if FOOTER_OLD not in board:
            raise SystemExit(f"unrecognised footer in {slug}")
        board = board.replace(FOOTER_OLD, FOOTER_NEW, 1)

        text = text[:start] + board + text[end:]
        done.append(slug)

    path.write_text(text, encoding="utf-8")
    print(f"{path.name}: {len(done)} board(s) spliced")


if __name__ == "__main__":
    main()
