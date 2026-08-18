"""Copy the question pool from one Supabase project to another.

Written for the one move this project actually needs: filling a fresh hosted
project from the local stack. `supabase db push` carries the *schema* and
nothing else -- `seed.sql` never runs against a hosted project -- so a correctly
deployed project comes up with the right tables and no questions in them.

Why a script rather than piping `seed.sql` at the hosted database:

* It copies what is *in the database*, not what is in a file. Once the ingest
  tool has added generated questions locally, they come along too.
* Text crosses as JSON over HTTPS, so it stays UTF-8. Piping SQL through a
  Windows shell re-encodes it, and `Währung` arrives as `WÃ¤hrung` -- that
  already happened once in this project and was not noticed until the bytes
  were checked by hand.
* It is idempotent. A quiz whose slug already exists on the target is skipped,
  so an interrupted run is resumed by running it again.

Both ends are addressed with a service-role key, exactly like the API and the
ingest tool: row level security is on with no policies, so nothing else can
read or write these tables.

Dry run is the default. Nothing is written without --commit.

Pass the target key through the environment, not as an argument. argparse
echoes the whole command line back on a usage error, so a key given as a flag
can end up in scrollback, shell history or a CI log:

    $env:COPY_POOL_TARGET_KEY = "<service-role key>"     # PowerShell
    export COPY_POOL_TARGET_KEY="<service-role key>"     # bash

    python -m tools.copy_pool --target-url https://<ref>.supabase.co
    python -m tools.copy_pool --target-url https://<ref>.supabase.co --commit
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

from supabase import Client, create_client

from tools.ingest.config import ConfigError, load_dotenv, service_role_key, supabase_url


class CopyError(RuntimeError):
    """Something went wrong that the operator has to decide about."""



PAGE = 1000


def read_all(client: Client, table: str) -> list[dict]:
    """Every row of `table`, in pages.

    PostgREST caps a response at `db-max-rows` -- 1000 by default -- and says so
    only in the Content-Range header, which the client does not surface. An
    unpaged read therefore *succeeds* and returns a prefix. That is the worst
    possible failure for this script: a pool of 8000 answers copies as the first
    1000, and every quiz past the cut arrives with a handful of pairs or none,
    which looks like a written question and plays as a broken one.

    Paged by `id` rather than by `position`, because the page boundary needs a
    total order. `position` repeats across quizzes, and PostgREST resolves ties
    however the plan happens to, so consecutive pages could drop or repeat rows.
    Callers order by `position` themselves once the rows are in hand.
    """
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            client.table(table)
            .select("*")
            .order("id")
            .range(start, start + PAGE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def read_pool(client: Client) -> tuple[list[dict], list[dict], dict, dict]:
    """Everything needed to rebuild the pool elsewhere."""
    subjects = sorted(read_all(client, "subjects"), key=lambda row: row.get("position") or 0)
    quizzes = read_all(client, "quizzes")

    categories = defaultdict(list)
    for row in sorted(read_all(client, "categories"), key=lambda row: row["position"]):
        categories[row["quiz_id"]].append(row)

    items = defaultdict(list)
    for row in sorted(read_all(client, "items"), key=lambda row: row["position"]):
        items[row["quiz_id"]].append(row)

    return subjects, quizzes, categories, items



def sync_subjects(target: Client, subjects: list[dict], *, commit: bool) -> dict[str, str]:
    """Make sure every subject exists on the target. Returns slug -> target id.

    Subjects are matched by slug rather than id: the target may already have
    them, and their ids are its own.
    """
    existing = {
        row["slug"]: row["id"] for row in target.table("subjects").select("id, slug").execute().data
    }

    missing = [subject for subject in subjects if subject["slug"] not in existing]
    if missing and commit:
        written = (
            target.table("subjects")
            .insert(
                [
                    {
                        "slug": subject["slug"],
                        "name": subject["name"],
                        "description": subject.get("description"),
                        "position": subject.get("position", 0),
                    }
                    for subject in missing
                ]
            )
            .execute()
            .data
        )
        existing.update({row["slug"]: row["id"] for row in written})

    return existing


def copy_question(
    target: Client,
    quiz: dict,
    categories: list[dict],
    items: list[dict],
    subject_id: str | None,
) -> None:
    """Write one quiz with its pairing. Ordered quiz -> categories -> items.

    The quiz row is deleted again if a later step fails: the three tables have
    no transaction between them through PostgREST, and a quiz with categories
    but no answers would be dealt into a round and be unplayable.

    Every column that decides how a question is *played* has to cross with it.
    `category_kind` is the sharpest: it defaults to 'text', and a picture
    question copied as text has its category labels served to the players --
    labels that name the photographed thing, which is the answer. So the image
    columns and the kind move together, and `origin` comes along too, or a
    hand-written question arrives claiming to be machine-written.
    """
    written_quiz = (
        target.table("quizzes")
        .insert(
            {
                "subject_id": subject_id,
                "slug": quiz["slug"],
                "title": quiz["title"],
                "description": quiz.get("description"),
                "difficulty": quiz.get("difficulty", "medium"),
                "source_url": quiz.get("source_url"),
                "source_title": quiz.get("source_title"),
                "category_kind": quiz.get("category_kind", "text"),
                "origin": quiz.get("origin", "ingest"),
            }
        )
        .execute()
        .data
    )
    quiz_id = written_quiz[0]["id"]

    try:
        written_categories = (
            target.table("categories")
            .insert(
                [
                    {
                        "quiz_id": quiz_id,
                        "label": category["label"],
                        "position": category["position"],
                        "image_file": category.get("image_file"),
                        "image_credit": category.get("image_credit"),
                        "image_licence": category.get("image_licence"),
                        "image_licence_url": category.get("image_licence_url"),
                    }
                    for category in categories
                ]
            )
            .execute()
            .data
        )

        by_label = {row["label"]: row["id"] for row in written_categories}
        target_id = {
            category["id"]: by_label[category["label"]]
            for category in categories
            if category["label"] in by_label
        }

        target.table("items").insert(
            [
                {
                    "quiz_id": quiz_id,
                    "category_id": target_id[item["category_id"]],
                    "label": item["label"],
                    "position": item["position"],
                    "explanation": item.get("explanation"),
                }
                for item in items
            ]
        ).execute()
    except Exception:
        target.table("quizzes").delete().eq("id", quiz_id).execute()
        raise



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.copy_pool",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source-url", help="Defaults to the local stack (INGEST_SUPABASE_URL).")
    parser.add_argument("--source-key", help="Defaults to SUPABASE_SERVICE_ROLE_KEY.")
    parser.add_argument("--target-url", required=True, help="Where the questions are going.")
    parser.add_argument(
        "--target-key",
        help=(
            "Service-role key for the target. Prefer COPY_POOL_TARGET_KEY: a key "
            "passed as an argument is echoed back by any usage error, and ends up "
            "in shell history and terminal scrollback."
        ),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write. Without this the run only reports what it would do.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    try:
        source_url = supabase_url(args.source_url)
        source_key = service_role_key(args.source_key)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target_key = os.environ.get("COPY_POOL_TARGET_KEY") or args.target_key
    if not target_key:
        print(
            "error: no target key. Set COPY_POOL_TARGET_KEY (preferred) or pass "
            "--target-key.",
            file=sys.stderr,
        )
        return 2

    if source_url.rstrip("/") == args.target_url.rstrip("/"):
        print("error: source and target are the same project.", file=sys.stderr)
        return 2

    source = create_client(source_url, source_key)
    target = create_client(args.target_url.rstrip("/"), target_key)

    print("Copy question pool")
    print(f"  From    {source_url}")
    print(f"  To      {args.target_url}")
    print(f"  Mode    {'COMMIT -- rows will be written' if args.commit else 'dry run'}\n")

    subjects, quizzes, categories, items = read_pool(source)
    print(f"  Source holds {len(quizzes)} question(s), {sum(len(v) for v in items.values())} answer(s)\n")

    subject_slug = {subject["id"]: subject["slug"] for subject in subjects}
    subject_id = sync_subjects(target, subjects, commit=args.commit)

    # Paged like the source reads: past 1000 questions on the target, an unpaged
    # read would hand back a prefix and this set would claim they are new.
    already = {row["slug"] for row in read_all(target, "quizzes")}

    copied = skipped = failed = 0
    for quiz in sorted(quizzes, key=lambda q: q["slug"]):
        pairs = len(items.get(quiz["id"], []))

        if quiz["slug"] in already:
            print(f"  skip   {quiz['slug']:<34} already on the target")
            skipped += 1
            continue

        kind = quiz.get("category_kind", "text")
        if not args.commit:
            print(f"  would  {quiz['slug']:<34} {pairs} pair(s)  {kind}")
            copied += 1
            continue

        slug = subject_slug.get(quiz["subject_id"])
        try:
            copy_question(
                target,
                quiz,
                categories.get(quiz["id"], []),
                items.get(quiz["id"], []),
                subject_id.get(slug),
            )
        except Exception as exc:  # noqa: BLE001 - one bad quiz must not stop the rest
            print(f"  FAIL   {quiz['slug']:<34} {exc}")
            failed += 1
            continue

        print(f"  copied {quiz['slug']:<34} {pairs} pair(s)  {kind}")
        copied += 1

    print(f"\n  {'Would copy' if not args.commit else 'Copied'}  {copied}")
    print(f"  Skipped     {skipped}")
    if failed:
        print(f"  Failed      {failed}")
    if not args.commit:
        print("\n  Nothing was written. Re-run with --commit.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
