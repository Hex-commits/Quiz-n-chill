"""The command line: parse the flags, walk the articles, write the reports.

Everything with a decision in it lives a layer down -- this module fetches an
article, hands it to the graph and files the result. It is deliberately the only
place that prints.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    REPO_ROOT,
    ConfigError,
    Settings,
    is_local,
    load_dotenv,
)
from .output.report import render_markdown
from .output.store import (
    connect,
    existing_slugs,
    existing_source_urls,
    subjects,
    write_question,
)
from .sources.wikimedia_images import WikimediaImages
from .pipeline.chains import (
    check_step,
    explain_step,
    extract_step,
    illustrate_step,
    reframe_step,
    repair_step,
    review_step,
)
from .pipeline.graph import build_graph, run_article
from .pipeline.llm import LLMError, available_models, chat_model
from .sources.strategies import STRATEGIES, candidates
from .sources.wikipedia import WikipediaClient, WikipediaError

DESCRIPTION = """\
Fill the question pool from Wikipedia.

    python -m tools.ingest --limit 10                 # dry run, writes a report
    python -m tools.ingest --limit 10 --commit        # also writes to Supabase
    python -m tools.ingest --titles Berlin Sonnensystem --commit

Dry run is the default on purpose. These questions are machine-written and go
straight into a game; reading a batch before committing it costs one command and
catches the ones that are technically valid but poor.

Runs entirely on this machine: the model is served by the project's Ollama
container, so nothing is sent to a third party and there is no API key.

Settings come from the command line, then the environment, then the repo-root
.env:
    SUPABASE_SERVICE_ROLE_KEY   required
    INGEST_SUPABASE_URL         the stack as reachable from the host; falls back
                                to SUPABASE_URL with host.docker.internal
                                rewritten to 127.0.0.1
    INGEST_SUPABASE_SERVICE_ROLE_KEY
                                key for that URL, when it is not the local stack
    OLLAMA_URL                  default http://localhost:11435
    INGEST_MODEL                default glm4:9b

Filling a hosted project from this machine is the same command with both halves
pointed at it -- the URL and the key have to name the same project:

    python -m tools.ingest --limit 50 --commit \\
        --supabase-url https://<ref>.supabase.co --supabase-key <service-role>

The model still runs locally; only the finished rows leave the machine.
"""

MIN_ARTICLE_CHARS = 600


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.ingest",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit", type=int, default=10, help="How many questions to aim for.")
    parser.add_argument("--titles", nargs="*", help="Specific articles instead of the top list.")
    parser.add_argument("--lang", default="de", help="Wikipedia language edition.")
    parser.add_argument(
        "--source",
        choices=sorted(STRATEGIES),
        default="mixed",
        help=(
            "Where candidate articles come from. 'mixed' (default) interleaves "
            "subjects/lists/vetted/evergreen. 'subjects' draws category members "
            "evenly across the quiz's subjects; 'lists' takes popular list "
            "articles, already tabulated into pairings; 'vetted' takes "
            "peer-reviewed Exzellent/Lesenswert articles; 'evergreen' ranks by "
            "staying power; 'recent' is today's top list."
        ),
    )
    parser.add_argument(
        "--months",
        type=int,
        default=24,
        help="How far back --source evergreen looks. Default 24.",
    )
    parser.add_argument(
        "--include-people",
        action="store_true",
        help=(
            "Also try biographies. Skipped by default: a life story has no set "
            "of categories with several members each, so it makes poor "
            "Zuordnungs material."
        ),
    )
    parser.add_argument("--model", help=f"Ollama model tag. Default {DEFAULT_MODEL}.")
    parser.add_argument(
        "--ollama-url",
        help=f"Where the Ollama container is listening. Default {DEFAULT_OLLAMA_URL}.",
    )
    parser.add_argument(
        "--supabase-url",
        help=(
            "Supabase URL as reachable from this machine. Overrides "
            "INGEST_SUPABASE_URL and SUPABASE_URL."
        ),
    )
    parser.add_argument(
        "--supabase-key",
        help=(
            "Service-role key for that project. Pass it whenever --supabase-url "
            "names a project other than the local stack -- the key has to match "
            "the URL. Overrides INGEST_SUPABASE_SERVICE_ROLE_KEY and "
            "SUPABASE_SERVICE_ROLE_KEY."
        ),
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="Tries per article before giving up (each re-feeds the complaints).",
    )
    parser.add_argument(
        "--no-explain",
        action="store_true",
        help=(
            "Skip the pass that writes a one-line reason per answer. Costs one "
            "model call per accepted question."
        ),
    )
    parser.add_argument(
        "--no-pictures",
        action="store_true",
        help=(
            "Skip illustration. Every question stays a text question; no "
            "Wikidata or Commons calls are made."
        ),
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip the second model pass that checks the content against the article.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Articles to process at once. Ollama serves them from one loaded "
            "copy of the weights, so 2-3 is close to free on a GPU; raise "
            "OLLAMA_NUM_PARALLEL to match. Default 1."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="One line per article instead of a line per pipeline step.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write to Supabase. Without this the run only produces reports.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "tools" / "ingest" / "out",
        help="Directory for the run's reports.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _speak_utf8()

    load_dotenv()
    try:
        settings = Settings.resolve(
            supabase_url_override=args.supabase_url,
            supabase_key_override=args.supabase_key,
            ollama_url=args.ollama_url,
            model=args.model,
        )
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    db = connect(settings.supabase_url, settings.supabase_key)
    try:
        known_subjects = subjects(db)
        taken_slugs = existing_slugs(db)
        seen_sources = existing_source_urls(db)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        print(
            f"Cannot reach Supabase at {settings.supabase_url}: {exc}\n"
            "  Is the stack up? `npm run db:start`\n"
            "  Wrong address? Set INGEST_SUPABASE_URL or pass --supabase-url.",
            file=sys.stderr,
        )
        return 2

    if not known_subjects:
        print(
            f"No subjects at {settings.supabase_url}. Run `npm run db:reset` first.",
            file=sys.stderr,
        )
        return 2
    subject_slugs = {slug for slug, _ in known_subjects}

    try:
        installed = available_models(settings.ollama_url)
    except LLMError as exc:
        print(exc, file=sys.stderr)
        return 2
    if settings.model not in installed:
        print(
            f"Model {settings.model!r} is not pulled. "
            f"Available: {', '.join(installed) or 'none'}\n"
            f"  docker compose exec ollama ollama pull {settings.model}",
            file=sys.stderr,
        )
        return 2

    steps_on = [
        "extract",
        "check",
        *([] if args.no_review else ["review"]),
        *([] if args.no_pictures else ["illustrate"]),
        *([] if args.no_explain else ["explain"]),
    ]
    print("=" * 72)
    print(f"  Model      {settings.model}  via {settings.ollama_url}  [{_processor(settings.ollama_url)}]")
    where = "" if is_local(settings.supabase_url) else "   [REMOTE PROJECT]"
    print(f"  Supabase   {settings.supabase_url}{where}")
    print(f"  Source     {args.source}" + (f", {args.months} months" if args.source in ("mixed", "evergreen", "lists") else ""))
    print(f"  Pipeline   {' -> '.join(steps_on)}   ({args.attempts} attempts per article)")
    print(f"  Workers    {args.workers}")
    print(f"  Mode       {'COMMIT -- questions will be written' if args.commit else 'dry run -- nothing is written'}")
    print("=" * 72)

    model = chat_model(base_url=settings.ollama_url, model=settings.model)
    pipeline = build_graph(
        extract=extract_step(model, sorted(subject_slugs)),
        check=check_step(subject_slugs=subject_slugs, taken_slugs=taken_slugs),
        review=None if args.no_review else review_step(model),
        illustrate=None if args.no_pictures else illustrate_step(WikimediaImages()),
        reframe=None if args.no_pictures else reframe_step(model),
        explain=None if args.no_explain else explain_step(model),
        repair=repair_step(),
    )

    wiki = WikipediaClient(lang=args.lang, cache_dir=args.out / ".cache")
    titles = _candidates(wiki, args, subject_slugs)
    print(f"{len(titles)} candidate articles; aiming for {args.limit} questions.\n")

    accepted: list[dict] = []
    rejected: list[dict] = []
    skipped = 0
    run_started = time.monotonic()

    seen_lock = threading.Lock()

    def process(title: str) -> _Attempt:
        """Fetch one article and run it. Output is collected, never printed.

        Runs on a worker thread, so anything printed here would interleave with
        another article mid-sentence. The caller replays `lines` as one block.
        """
        lines: list[str] = []
        try:
            article = wiki.article(title)
        except WikipediaError as exc:
            return _Attempt(title, skip=str(exc))

        with seen_lock:
            already = article.url in seen_sources
        if already:
            return _Attempt(article.title, skip="already sourced")
        if len(article.text) < MIN_ARTICLE_CHARS:
            return _Attempt(article.title, skip=f"only {len(article.text)} chars")
        if article.is_biography and not args.include_people:
            return _Attempt(article.title, skip="biography")

        if not args.quiet:
            lines.append(f"{len(article.text):,} chars from {article.url}")

        outcome = run_article(
            pipeline,
            article,
            known_subjects,
            max_attempts=args.attempts,
            on_step=None if args.quiet else (lambda _node, line: lines.append(line)),
        )
        return _Attempt(article.title, article=article, outcome=outcome, lines=lines)

    queue = deque(titles)
    done_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        in_flight: dict = {}
        while queue or in_flight:
            while queue and len(in_flight) < args.workers and len(accepted) < args.limit:
                title = queue.popleft()
                in_flight[pool.submit(process, title)] = title
            if not in_flight:
                break

            finished, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in finished:
                in_flight.pop(future)
                done_count += 1
                attempt = future.result()
                marker = f"[{done_count:>4}/{len(titles)}]"

                if attempt.skip:
                    skipped += 1
                    print(f"{marker} skip  {_short(attempt.title)}  ({attempt.skip})")
                    continue

                print(f"{marker} {attempt.title}")
                for line in attempt.lines:
                    print(f"         {line}")

                outcome, article = attempt.outcome, attempt.article
                question = outcome.question
                record = {
                    "article": {"title": article.title, "url": article.url},
                    "question": question.model_dump(),
                    "problems": outcome.problems,
                    "review": outcome.review.model_dump() if outcome.review else None,
                    "steps": outcome.steps,
                    "images": {
                        label: asdict(image) for label, image in outcome.images.items()
                    },
                    "flipped": outcome.flipped,
                }

                if outcome.problems:
                    rejected.append(record)
                    print(f"         DROPPED  {outcome.seconds:.0f}s  {outcome.problems[0][:100]}")
                else:
                    if args.commit:
                        written = write_question(db, question, article, outcome.images)
                        record["written"] = asdict(written)
                        verb = "WRITTEN"
                        detail = f"{written.items} pairs"
                    else:
                        verb = "ACCEPTED"
                        detail = f"{len(question.pairs)} pairs"
                    if outcome.is_picture:
                        detail += ", pictures" + (" (flipped)" if outcome.flipped else "")
                    print(
                        f"         {verb}  {outcome.seconds:.0f}s  {question.slug} "
                        f"({detail}, {question.difficulty})"
                    )
                    with seen_lock:
                        seen_sources.add(article.url)
                    accepted.append(record)

                print(f"         {_progress(accepted, rejected, skipped, args.limit, run_started)}\n")

            if len(accepted) >= args.limit and not in_flight:
                break

    return _write_reports(args, settings, accepted, rejected, skipped, run_started)


@dataclass
class _Attempt:
    """One article's fate, with its output held back until it can be printed."""

    title: str
    article: object | None = None
    outcome: object | None = None
    skip: str | None = None
    lines: list[str] = field(default_factory=list)


def _speak_utf8() -> None:
    """Make the console survive the titles Wikipedia actually has.

    A Windows console defaults to cp1252, and `print` on a title like
    `2.43: Seiin Kōkō Danshi Volley-bu` raises UnicodeEncodeError -- killing a
    run hours in, over a character in a heading. German Wikipedia is full of
    transliterated titles, so this is a certainty on any long run rather than an
    edge case. `errors="replace"` is the belt to the UTF-8 braces: a console
    that still cannot encode something prints a placeholder instead of throwing.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _short(title: str, width: int = 44) -> str:
    return title if len(title) <= width else title[: width - 1] + "…"


def _progress(accepted, rejected, skipped, limit, started) -> str:
    """One line of where the run stands, and what it is on course for."""
    done = len(accepted)
    elapsed = time.monotonic() - started
    parts = [f"{done}/{limit} accepted", f"{len(rejected)} dropped", f"{skipped} skipped"]

    if done and done < limit:
        remaining = (elapsed / done) * (limit - done)
        parts.append(f"~{_clock(remaining)} left")
    parts.append(f"{_clock(elapsed)} elapsed")
    return "-> " + "  |  ".join(parts)


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


def _processor(ollama_url: str) -> str:
    """Whether Ollama is on the GPU -- the single biggest factor in run time.

    Best effort: a model that is not loaded yet reports nothing, and that is
    worth saying rather than guessing.
    """
    try:
        with urllib.request.urlopen(f"{ollama_url}/api/ps", timeout=5) as response:
            models = json.loads(response.read()).get("models") or []
    except Exception:  # noqa: BLE001 - cosmetic
        return "processor unknown"
    if not models:
        return "not yet loaded"
    size = models[0].get("size", 0)
    vram = models[0].get("size_vram", 0)
    if not size:
        return "processor unknown"
    return f"{round(100 * vram / size)}% GPU"


def _candidates(wiki: WikipediaClient, args, subject_slugs: set[str]) -> list[str]:
    """The articles this run will try, in order.

    Four times `--limit`, because a good share get skipped before the model is
    ever involved -- already sourced, a biography, too short, or unfetchable.
    """
    if args.titles:
        return args.titles

    wanted = args.limit * 4
    print(f"Collecting candidates ({args.source})...")
    titles = candidates(
        args.source, wiki, limit=wanted, months=args.months, subject_slugs=subject_slugs
    )
    if titles:
        return titles

    print("  (no candidates from that source; falling back to the current top list)")
    return wiki.top_titles(limit=wanted)


def _write_reports(
    args,
    settings: Settings,
    accepted: list[dict],
    rejected: list[dict],
    skipped: int = 0,
    started: float | None = None,
) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {"accepted": accepted, "rejected": rejected, "committed": args.commit}

    json_report = args.out / f"ingest-{stamp}.json"
    json_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_report = args.out / f"ingest-{stamp}.md"
    md_report.write_text(
        render_markdown(payload, model=settings.model, generated_at=stamp), encoding="utf-8"
    )

    elapsed = time.monotonic() - started if started else 0.0
    tried = len(accepted) + len(rejected)
    rate = f"{100 * len(accepted) / tried:.0f}%" if tried else "n/a"

    print("=" * 72)
    print(f"  Accepted   {len(accepted)}")
    print(f"  Dropped    {len(rejected)}   (accept rate {rate} of {tried} articles tried)")
    print(f"  Skipped    {skipped}   (before any model call)")
    if elapsed:
        each = f", {_clock(elapsed / len(accepted))} each" if accepted else ""
        print(f"  Took       {_clock(elapsed)}{each}")
    print("=" * 72)
    print(f"  Read this  {md_report}")
    print(f"  Raw        {json_report}")
    print(
        "  Written to the database."
        if args.commit
        else "  Dry run -- nothing was written. Re-run with --commit."
    )
    return 0
