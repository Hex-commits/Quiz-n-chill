"""Print a picture-question file compactly, for writing its fakes against."""

import re
import sys
from pathlib import Path

STATEMENT = "with new_quiz as ("
HEAD = re.compile(
    r"select s\.id, '(?P<slug>[a-z0-9-]+)', '(?P<title>[^']*)',\s*\n\s*'(?P<question>[^']*)'"
)
PAIR = re.compile(r"^    \('((?:[^']|'')*)', '((?:[^']|'')*)',", re.M)


def main() -> None:
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(re.escape(STATEMENT), text)]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(text)
        board = text[start:end]
        head = HEAD.search(board)
        print(f"\n## {head.group('slug')} -- {head.group('title')} -- {head.group('question')}")
        for label, answer in PAIR.findall(board):
            print(f"   {label.replace(chr(39)*2, chr(39))}  ->  {answer.replace(chr(39)*2, chr(39))}")


if __name__ == "__main__":
    main()
