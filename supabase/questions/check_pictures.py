"""Verify a picture batch: board shape, and that every image really loads."""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.ingest.sources.wikimedia_images import commons_url  # noqa: E402

MIN_PAIRS, MAX_PAIRS, MAX_WORDS, MAX_EXPLANATION = 10, 14, 4, 160

sql = Path(sys.argv[1]).read_text(encoding="utf-8")

# Each board is one `with new_quiz ...` statement.
boards = sql.split("with new_quiz as (")[1:]
print(f"{len(boards)} picture questions\n")

problems = 0
files: list[tuple[str, str]] = []
all_slugs: set[str] = set()

for board in boards:
    slug = re.search(r"select s\.id, '([^']+)'", board).group(1)
    kind = "'image'" in board
    body = board.split("values", 1)[1].split("\n),", 1)[0]
    rows = re.findall(
        r"\(('(?:[^']|'')*'), ('(?:[^']|'')*'), ('(?:[^']|'')*'),\s*"
        r"('(?:[^']|'')*'), (null|'(?:[^']|'')*'),\s*"
        r"('(?:[^']|'')*'), (null|'(?:[^']|'')*'), (\d+)\)",
        body,
    )
    unq = lambda v: v[1:-1].replace("''", "'") if v != "null" else None  # noqa: E731

    labels = [unq(r[0]) for r in rows]
    answers = [unq(r[1]) for r in rows]
    explanations = [unq(r[2]) for r in rows]
    said = []

    if not kind:
        said.append("category_kind is not image")
    if not MIN_PAIRS <= len(rows) <= MAX_PAIRS:
        said.append(f"{len(rows)} pairs outside {MIN_PAIRS}-{MAX_PAIRS}")
    if len(set(a.casefold() for a in answers)) != len(answers):
        said.append("repeated answer")
    if len(set(l.casefold() for l in labels)) != len(labels):
        said.append("repeated category")
    if set(a.casefold() for a in answers) & set(l.casefold() for l in labels):
        said.append("term used as both category and answer")
    long_answers = [a for a in answers if len(a.split()) > MAX_WORDS]
    if long_answers:
        said.append(f"answers over {MAX_WORDS} words: {long_answers}")
    long_expl = [e for e in explanations if len(e) > MAX_EXPLANATION]
    if long_expl:
        said.append(f"explanation over {MAX_EXPLANATION} chars")
    if "Doppelt" in labels + answers + explanations:
        said.append("placeholder text left in")
    if slug in all_slugs:
        said.append("duplicate slug")
    all_slugs.add(slug)

    for row in rows:
        file_name, licence = unq(row[3]), unq(row[5])
        if not file_name or not licence:
            said.append("image without licence")
        files.append((slug, file_name))

    print(f"{'FAIL' if said else 'ok  '} {slug}: {len(rows)} pairs")
    for note in said:
        print(f"       - {note}")
        problems += 1

print(f"\nchecking {len(files)} image URLs ...")
broken = []
import time

UA = "quiz-quiz/0.1 (batch verification; contact via repo)"

for index, (slug, file_name) in enumerate(files):
    url = commons_url(file_name, width=320)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    broken.append((slug, file_name, response.status))
                break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            broken.append((slug, file_name, exc.code))
            break
        except Exception as exc:  # noqa: BLE001
            broken.append((slug, file_name, repr(exc)))
            break
    time.sleep(0.8)
    if index % 25 == 24:
        print(f"   ... {index + 1}/{len(files)}")

for slug, file_name, why in broken:
    print(f"  BROKEN {slug}: {file_name} ({why})")
print(f"{len(files) - len(broken)}/{len(files)} images load, {problems} board problems")
