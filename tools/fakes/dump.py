"""Print a question file compactly, for writing its fakes against.

The SQL is 25 KB of literal per file, most of it explanations that say nothing
about what a fake would have to avoid. This prints the part that does: the
board's question, and every category with its answer.
"""

import json
import re
import sys
from pathlib import Path

BOARD = re.compile(
    r"^    \('[a-z0-9-]+', '(?P<slug>[a-z0-9-]+)', '(?P<title>[^']*)',\s*\n"
    r"\s*'(?P<question>[^']*)',",
    re.M,
)


def main() -> None:
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    starts = list(BOARD.finditer(text))
    for n, m in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(text)
        body = text[m.start():end]
        arrays = re.findall(r"'(\[.*?\])'::jsonb", body, re.S)
        pairs = json.loads(arrays[0].replace("''", "'"))
        print(f"\n## {m.group('slug')} -- {m.group('title')} -- {m.group('question')}")
        for pair in pairs:
            print(f"   {pair[0]}  ->  {pair[1]}")


if __name__ == "__main__":
    main()
