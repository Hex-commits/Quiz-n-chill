"""Check the fakes in a question file before it is ever applied.

Four things go wrong when writing 1400 of these by hand, and all four are
cheaper to catch here than as a constraint violation halfway through a psql
run that has already inserted 300 questions.

Usage:  python tools/fakes/check.py supabase/questions/*.sql
"""

import json
import re
import sys
from pathlib import Path

BOARD = re.compile(
    r"^    \('(?P<subject>[a-z0-9-]+)', '(?P<slug>[a-z0-9-]+)',",
    re.M,
)
EXPECTED_FAKES = 2


def literals(board: str) -> list[list[list[str]]]:
    """The jsonb array literals in one board's text, parsed."""
    out = []
    for match in re.finditer(r"'(\[.*?\])'::jsonb", board, re.S):
        out.append(json.loads(match.group(1).replace("''", "'")))
    return out


def boards(text: str):
    starts = [m for m in BOARD.finditer(text)]
    for n, match in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(text)
        yield match.group("slug"), text[match.start():end]


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if "sp.fakes" not in text:
        return [f"{path.name}: file has no fakes column yet"]

    problems = []
    for slug, board in boards(text):
        arrays = literals(board)
        if len(arrays) != 2:
            problems.append(f"{path.name}:{slug}: expected pairs and fakes, got {len(arrays)}")
            continue

        pairs, fakes = arrays
        answers_list = [pair[1] for pair in pairs]
        cats_list = [pair[0] for pair in pairs]
        answers = set(answers_list)
        categories = set(cats_list)
        labels = [fake[0] for fake in fakes]

        # `items_quiz_id_label_key` refuses two answers with the same text on
        # one board, and `categories_quiz_id_label_key` the same for
        # categories. Both only fail once the file is being applied, with the
        # earlier questions of the run already inserted.
        dup_answers = sorted({a for a in answers_list if answers_list.count(a) > 1})
        if dup_answers:
            problems.append(f"{path.name}:{slug}: answer used twice: {', '.join(dup_answers)}")
        dup_cats = sorted({c for c in cats_list if cats_list.count(c) > 1})
        if dup_cats:
            problems.append(f"{path.name}:{slug}: category used twice: {', '.join(dup_cats)}")

        if len(fakes) != EXPECTED_FAKES:
            problems.append(f"{path.name}:{slug}: {len(fakes)} fake(s), expected {EXPECTED_FAKES}")
        if any(len(fake) != 2 for fake in fakes):
            problems.append(f"{path.name}:{slug}: a fake is not [label, explanation]")
        if len(set(labels)) != len(labels):
            problems.append(f"{path.name}:{slug}: two fakes share a label")

        # `items_quiz_id_label_key` would refuse these, but only once the file
        # is being applied -- and the run stops there with the earlier questions
        # already in.
        clash = sorted(set(labels) & answers)
        if clash:
            problems.append(f"{path.name}:{slug}: fake repeats an answer: {', '.join(clash)}")

        # Not a constraint, just unplayable: a fake named after a category on
        # its own board reads as the pairing the player is looking for.
        echo = sorted(set(labels) & categories)
        if echo:
            problems.append(f"{path.name}:{slug}: fake repeats a category: {', '.join(echo)}")

        for fake in fakes:
            if len(fake) == 2 and not fake[1].strip():
                problems.append(f"{path.name}:{slug}: fake '{fake[0]}' has no explanation")

    return problems


def main() -> None:
    problems = []
    for arg in sys.argv[1:]:
        problems += check(Path(arg))
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
