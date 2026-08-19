"""Apply the hand-written question files to a Supabase project.

`psql < file.sql` is the better tool for this and should be preferred wherever
it is available -- it runs the real statement, with the real constraints, in one
transaction per file. This exists for the case the repo otherwise has no answer
for: a **hosted** project, where `supabase db push` carries migrations only,
`seed.sql` never runs, and reaching the database directly needs the database
password rather than the service-role key that is already in `.env`.

So the files are parsed (see `parse.py`) and written over PostgREST with the
service-role key, exactly as `tools/ingest` and `tools/copy_pool` write.

What is faithfully reproduced from the SQL:

* **A board is skipped if its slug already exists**, so a second run adds only
  what is new -- the `where not exists` guard every file carries.
* **Pairs and fakes are written in one insert.** The files do this deliberately:
  `items_quiz_id_label_key` then sees both sets at once, so a fake written to
  repeat an answer on its own board fails the board instead of quietly becoming
  a second row nobody can tell apart.
* **A board is all-or-nothing.** PostgREST has no transaction across three
  tables, so a failure after the quiz row deletes it again -- the same guard
  `tools/ingest` uses. A quiz with categories and no answers would be dealt
  into a round and be unplayable.

What is not: each board is its own unit of failure rather than each file, and
`--replace` empties the hand-written pool in a separate step from refilling it.
Between those two steps the project has no hand-written questions, which is a
visible state to a player mid-game. Do it when nobody is playing.

Dry run is the default. Nothing is written without --commit.

    python -m tools.questions.apply                        # every file, dry run
    python -m tools.questions.apply --commit
    python -m tools.questions.apply --replace --commit     # wipe seed, then refill
    python -m tools.questions.apply supabase/questions/unnuetzes-wissen-*.sql --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from supabase import Client, create_client

from tools.ingest.config import (
    REPO_ROOT,
    ConfigError,
    is_local,
    load_dotenv,
    service_role_key,
    supabase_url,
)
from tools.questions.parse import HAND_WRITTEN, Board, ParseError, Subject, parse

CHUNK = 100
"""Quizzes deleted per request.

One `delete where origin = 'seed'` would be a single statement cascading through
roughly 17000 child rows, against a statement timeout nobody here controls. In
chunks it cannot half-finish invisibly: what got deleted is what the counter
says.
"""


def default_files() -> list[Path]:
    """Every hand-written file, subjects first.

    `subject-*.sql` has to land before the boards that name it -- their join on
    `subjects` finds nothing otherwise and they insert silently nothing, which
    is the failure this whole exercise started from. Sorting them to the front
    means a bare run cannot get the order wrong.
    """
    questions = REPO_ROOT / "supabase" / "questions"
    files = sorted(
        questions.glob("*.sql"),
        key=lambda path: (not path.name.startswith("subject-"), path.name),
    )
    return [REPO_ROOT / "supabase" / "seed.sql", *files]


def read_slugs(client: Client, table: str, column: str = "slug") -> dict[str, str]:
    """`slug -> id` for a whole table, in pages.

    PostgREST caps a response at `db-max-rows` and reports the cap only in a
    header the client does not surface, so an unpaged read *succeeds* and
    returns a prefix. Here that would mean re-inserting every quiz past the
    thousandth and failing on the unique constraint -- loudly, but only after
    the run had already been going for minutes.
    """
    found: dict[str, str] = {}
    start = 0
    while True:
        page = (
            client.table(table)
            .select(f"id, {column}")
            .order("id")
            .range(start, start + 1000 - 1)
            .execute()
            .data
        )
        found.update({row[column]: row["id"] for row in page})
        if len(page) < 1000:
            return found
        start += 1000


def sync_subjects(client: Client, subjects: list[Subject], *, commit: bool) -> dict[str, str]:
    """Make sure every subject the files name exists. Returns slug -> id."""
    existing = read_slugs(client, "subjects")

    missing = [subject for subject in subjects if subject.slug not in existing]
    for subject in missing:
        print(f"  subject  {subject.slug:<24} {'written' if commit else 'would be written'}")
    if missing and commit:
        written = (
            client.table("subjects")
            .insert(
                [
                    {
                        "slug": subject.slug,
                        "name": subject.name,
                        "description": subject.description,
                        "position": subject.position,
                    }
                    for subject in missing
                ]
            )
            .execute()
            .data
        )
        existing.update({row["slug"]: row["id"] for row in written})
    return existing


def delete_hand_written(client: Client, *, commit: bool) -> set[str]:
    """Remove every `origin = 'seed'` quiz. Categories and items cascade.

    Scoped by `origin` on purpose: the generated questions share every other
    column with these and exist in no file, so anything broader is unrecoverable
    rather than repeatable.

    Returns the slugs it removed, which a dry run needs in order to report
    honestly -- those rows are about to stop counting as "already there".
    """
    doomed = (
        client.table("quizzes").select("id, slug").eq("origin", HAND_WRITTEN).execute().data
    )
    if commit:
        ids = [row["id"] for row in doomed]
        for start in range(0, len(ids), CHUNK):
            client.table("quizzes").delete().in_("id", ids[start : start + CHUNK]).execute()
    return {row["slug"] for row in doomed}


def write_board(client: Client, board: Board, subject_id: str) -> None:
    """Write one board: quiz, then categories, then every answer."""
    quiz = (
        client.table("quizzes")
        .insert(
            {
                "subject_id": subject_id,
                "slug": board.slug,
                "title": board.title,
                "description": board.description,
                "difficulty": board.difficulty,
                "source_title": board.source_title,
                "source_url": board.source_url,
                "category_kind": board.category_kind,
                "origin": board.origin,
            }
        )
        .execute()
        .data
    )
    quiz_id = quiz[0]["id"]

    try:
        categories = (
            client.table("categories")
            .insert(
                [
                    {
                        "quiz_id": quiz_id,
                        "label": pair.label,
                        "position": pair.position,
                        **(pair.image or {}),
                    }
                    for pair in board.pairs
                ]
            )
            .execute()
            .data
        )
        by_label = {row["label"]: row["id"] for row in categories}

        # Pairs and fakes together, as the files write them: one insert is what
        # lets `items_quiz_id_label_key` refuse a fake that repeats an answer.
        client.table("items").insert(
            [
                {
                    "quiz_id": quiz_id,
                    "category_id": by_label[pair.label],
                    "label": pair.answer,
                    "position": pair.position,
                    "explanation": pair.explanation,
                }
                for pair in board.pairs
            ]
            + [
                {
                    "quiz_id": quiz_id,
                    "category_id": None,
                    "label": fake.label,
                    "position": fake.position,
                    "explanation": fake.explanation,
                }
                for fake in board.fakes
            ]
        ).execute()
    except Exception:
        client.table("quizzes").delete().eq("id", quiz_id).execute()
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.questions.apply",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Question files. Default: supabase/seed.sql and every supabase/questions/*.sql.",
    )
    parser.add_argument("--supabase-url", help="Defaults to INGEST_SUPABASE_URL / SUPABASE_URL.")
    parser.add_argument("--supabase-key", help="Defaults to SUPABASE_SERVICE_ROLE_KEY.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete every origin='seed' quiz before writing. Generated questions "
            "(origin='ingest') are left alone -- they are in no file."
        ),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write. Without this the run only reports what it would do.",
    )
    return parser


def _speak_utf8() -> None:
    """A Windows console defaults to cp1252, and these titles are German."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _speak_utf8()
    load_dotenv()

    try:
        url = supabase_url(args.supabase_url)
        key = service_role_key(args.supabase_key)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    files = args.files or default_files()
    try:
        parsed = [parse(path) for path in files]
    except (ParseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    boards = [board for one in parsed for board in one.boards]
    subjects = {subject.slug: subject for one in parsed for subject in one.subjects}

    where = "" if is_local(url) else "   [REMOTE PROJECT]"
    print("=" * 72)
    print(f"  Supabase   {url}{where}")
    replacing = (
        f"yes -- every origin={HAND_WRITTEN!r} quiz is deleted first"
        if args.replace
        else "no -- existing slugs are skipped"
    )
    mode = (
        "COMMIT -- rows will be written"
        if args.commit
        else "dry run -- nothing is written"
    )
    print(f"  Files      {len(parsed)}")
    print(
        f"  Holding    {len(boards)} board(s), "
        f"{sum(len(board.pairs) for board in boards)} pair(s), "
        f"{sum(len(board.fakes) for board in boards)} fake(s)"
    )
    print(f"  Replace    {replacing}")
    print(f"  Mode       {mode}")
    print("=" * 72)

    client = create_client(url, key)

    deleted: set[str] = set()
    if args.replace:
        deleted = delete_hand_written(client, commit=args.commit)
        verb = "Deleted" if args.commit else "Would delete"
        print(f"\n  {verb}  {len(deleted)} hand-written quiz(zes)\n")

    subject_id = sync_subjects(client, list(subjects.values()), commit=args.commit)

    unknown = sorted({board.subject_slug for board in boards} - set(subject_id))
    if unknown and args.commit:
        print(f"\nerror: no such subject: {', '.join(unknown)}", file=sys.stderr)
        return 2

    # A dry run has deleted nothing, so the rows it only *would* have removed
    # would otherwise be reported as skipped -- and a --replace rehearsal would
    # claim it was about to write nothing at all.
    already = set(read_slugs(client, "quizzes")) - deleted
    written = skipped = failed = 0

    print()
    for one in parsed:
        counts = {"written": 0, "skipped": 0, "failed": 0}
        for board in one.boards:
            if board.slug in already:
                counts["skipped"] += 1
                continue
            if not args.commit:
                counts["written"] += 1
                continue
            try:
                write_board(client, board, subject_id[board.subject_slug])
            except Exception as exc:  # noqa: BLE001 - one bad board must not stop the rest
                print(f"  FAIL  {board.slug:<38} {exc}")
                counts["failed"] += 1
                continue
            counts["written"] += 1

        if one.boards or one.subjects:
            verb = "wrote" if args.commit else "would write"
            print(
                f"  {one.path.name:<32} {verb} {counts['written']:>3}"
                f"   skipped {counts['skipped']:>3}"
                + (f"   FAILED {counts['failed']}" if counts["failed"] else "")
            )
        written += counts["written"]
        skipped += counts["skipped"]
        failed += counts["failed"]

    print()
    print("=" * 72)
    print(f"  {'Wrote' if args.commit else 'Would write'}  {written} board(s)")
    print(f"  Skipped     {skipped}   (slug already in the database)")
    if failed:
        print(f"  Failed      {failed}")
    if not args.commit:
        print("\n  Nothing was written. Re-run with --commit.")
    print("=" * 72)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
