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
from .domain.models import DEFAULT_DRAFTS
from .pipeline.chains import (
    augment_step,
    vet_step,
    check_step,
    explain_step,
    extract_step,
    illustrate_step,
    reframe_step,
    repair_step,
    review_step,
    select_step,
)
from .pipeline.graph import build_graph, run_all
from .pipeline.llm import JUDGE_TEMPERATURE, LLMError, available_models, chat_model
from .sources.strategies import STRATEGIES, candidates
from .sources.wikipedia import WikipediaClient, WikipediaError, WikipediaRelated

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

# An article shorter than this has no room for a set of clean pairings.
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
        "--drafts",
        type=int,
        default=DEFAULT_DRAFTS,
        help=(
            f"Questions to draft per article before choosing. Default {DEFAULT_DRAFTS}. "
            "One article usually holds more than one good question; a second pass "
            "then keeps the ones worth playing, and may keep several."
        ),
    )
    parser.add_argument(
        "--no-select",
        action="store_true",
        help=(
            "Skip the pass that chooses between the drafts. The first draft is "
            "used, as it was before the step existed."
        ),
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
        "--no-augment",
        action="store_true",
        help=(
            "Skip the pass that looks for missing pairs in other articles. "
            "A medium or hard question that is short then simply fails."
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
        help=argparse.SUPPRESS,  # kept so older commands still run; now the default
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

    # The first thing that actually touches the network. A mistyped or
    # unreachable URL surfaces here, and it is the most likely thing to be wrong
    # now that it is configurable -- so it gets a message rather than a
    # traceback from three libraries down.
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

    # Fail here rather than after fetching a dozen articles.
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

    selecting = not args.no_select and args.drafts > 1
    steps_on = [
        f"extract x{args.drafts}" if args.drafts > 1 else "extract",
        *(["select"] if selecting else []),
        "check",
        *([] if args.no_augment else ["augment?"]),
        *(["vet"] if settings.vet and not args.no_augment else []),
        *([] if args.no_review else ["review"]),
        *([] if args.no_pictures else ["illustrate"]),
        *([] if args.no_explain else ["explain"]),
    ]
    print("=" * 72)
    print(f"  Model      {settings.model}  via {settings.ollama_url}  [{_processor(settings.ollama_url)}]")
    # Said out loud because it is no longer a flag anyone typed: a setting that
    # lives in `.env` is one you can forget is on, and this one costs a model
    # call per borrowed pair.
    judged_by = "same model" if settings.judge_model == settings.model else settings.judge_model
    if selecting:
        # Said out loud, because "may only sort" and "may drop the article" are
        # very different steps and the difference is a setting, not a flag.
        powers = (
            "may reject the batch"
            if settings.judge_model != settings.model
            else "advisory -- set INGEST_JUDGE_MODEL to let it reject"
        )
        print(f"  Selecting  {args.drafts} drafts, judged by {judged_by}, {powers}")
    if settings.vet and not args.no_augment:
        print(f"  Vetting    on  (INGEST_VET)  judged by {judged_by}")
    elif not args.no_augment:
        # Said out loud because nothing else will. `review` cannot tell whether a
        # borrowed pair belongs to this question -- it judges pairs, and that is a
        # property of the board -- so with vetting off the report is the only
        # place a drifted pair gets caught. See `pipeline/augment.py`.
        print("  Vetting    off  (INGEST_VET)  borrowed pairs are unjudged -- read the report")
    # Said out loud, because a run aimed at a hosted project from this machine
    # looks exactly like a local one until the rows are already there.
    where = "" if is_local(settings.supabase_url) else "   [REMOTE PROJECT]"
    print(f"  Supabase   {settings.supabase_url}{where}")
    print(f"  Source     {args.source}" + (f", {args.months} months" if args.source in ("mixed", "evergreen", "lists") else ""))
    print(f"  Pipeline   {' -> '.join(steps_on)}   ({args.attempts} attempts per article)")
    print(f"  Workers    {args.workers}")
    print(f"  Mode       {'COMMIT -- questions will be written' if args.commit else 'dry run -- nothing is written'}")
    print("=" * 72)

    # Past pageview counts never change, so the cache next to the reports makes
    # the evergreen scan free on every run after the first.
    #
    # Built before the graph because `augment` searches through it: the step
    # that looks for missing pairs in other articles needs the same client, the
    # same pacing and the same rate-limit backoff as the main run.
    wiki = WikipediaClient(lang=args.lang, cache_dir=args.out / ".cache")

    # One model, one graph, reused for every article -- nothing in either is
    # article-specific, and rebuilding them per article would only re-derive the
    # same JSON Schema.
    model = chat_model(base_url=settings.ollama_url, model=settings.model)
    # Same weights, no sampling. Every step that *judges* rather than writes runs
    # on this one: a reviewer whose verdict moves between runs is not a gate, and
    # the temperature the generator needs is there to stop it repeating a rejected
    # answer -- a reason that applies to `extract` and to nothing else.
    decider = chat_model(
        base_url=settings.ollama_url, model=settings.model, temperature=JUDGE_TEMPERATURE
    )
    # The vet judge is its own model on top of that: it is the judgement that most
    # needs a stronger one, and paying for that on every extract call would not be
    # worth it.
    judge = (
        decider
        if settings.judge_model == settings.model
        else chat_model(
            base_url=settings.ollama_url,
            model=settings.judge_model,
            temperature=JUDGE_TEMPERATURE,
        )
    )
    pipeline = build_graph(
        extract=extract_step(model, sorted(subject_slugs), drafts=args.drafts),
        check=check_step(subject_slugs=subject_slugs, taken_slugs=taken_slugs),
        # On the judge rather than the run's model: choosing between drafts is
        # taste, and a 9B model asked "is this good?" is measured at noise -- see
        # the note in `prompts.py`. `INGEST_JUDGE_MODEL` already exists for
        # exactly this and falls back to the run's model. Whether that judge may
        # throw a whole batch away depends on whether it is one somebody chose.
        select=(
            select_step(judge, may_reject=settings.judge_model != settings.model)
            if selecting
            else None
        ),
        review=None if args.no_review else review_step(decider),
        augment=None if args.no_augment else augment_step(model, WikipediaRelated(wiki)),
        vet=vet_step(judge) if settings.vet and not args.no_augment else None,
        illustrate=None if args.no_pictures else illustrate_step(WikimediaImages()),
        reframe=None if args.no_pictures else reframe_step(model),
        explain=None if args.no_explain else explain_step(model),
        repair=repair_step(),
    )

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
            # Re-running is additive, not duplicating.
            return _Attempt(article.title, skip="already sourced")
        if len(article.text) < MIN_ARTICLE_CHARS:
            return _Attempt(article.title, skip=f"only {len(article.text)} chars")
        # Before the model, because this is the skip that saves real time.
        if article.is_biography and not args.include_people:
            return _Attempt(article.title, skip="biography")

        if not args.quiet:
            lines.append(f"{len(article.text):,} chars from {article.url}")

        outcomes = run_all(
            pipeline,
            article,
            known_subjects,
            max_attempts=args.attempts,
            on_step=None if args.quiet else (lambda _node, line: lines.append(line)),
        )
        return _Attempt(article.title, article=article, outcomes=outcomes, lines=lines)

    queue = deque(titles)
    done_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        in_flight: dict = {}
        while queue or in_flight:
            # Only keep work in flight while more questions are still wanted.
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

                article = attempt.article
                # One article can yield more than one question: `select` keeps
                # every draft worth playing, and each was put through the gates on
                # its own.
                for outcome in attempt.outcomes:
                    question = outcome.question
                    record = {
                        "article": {"title": article.title, "url": article.url},
                        "question": question.model_dump(),
                        "problems": outcome.problems,
                        "review": outcome.review.model_dump() if outcome.review else None,
                        "steps": outcome.steps,
                        # Keyed by category label, so the report can put each picture
                        # beside the pairing it belongs to.
                        "images": {
                            label: asdict(image) for label, image in outcome.images.items()
                        },
                        "flipped": outcome.flipped,
                        # Which articles pairs were borrowed from. In the record
                        # because with `INGEST_VET` off nothing judged whether they
                        # belong, and the report is where that gets caught.
                        "borrowed_from": outcome.borrowed_from,
                        "vetted": settings.vet and not args.no_augment,
                        "select_detail": outcome.select_detail,
                    }

                    if outcome.problems:
                        rejected.append(record)
                        print(
                            f"         DROPPED  {outcome.seconds:.0f}s  {outcome.problems[0][:100]}"
                        )
                        continue

                    # Writing happens here, on one thread, rather than in the
                    # worker: the Supabase client is shared and the ordered
                    # insert-with-rollback is not worth making concurrent.
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

                # A running tally after every article, so a long run never
                # leaves you guessing how far along it is or how it is going.
                print(f"         {_progress(accepted, rejected, skipped, args.limit, run_started)}\n")

            if len(accepted) >= args.limit and not in_flight:
                break

    return _write_reports(args, settings, accepted, rejected, skipped, run_started)


@dataclass
class _Attempt:
    """One article's fate, with its output held back until it can be printed.

    `outcomes` is a list because `select` may keep more than one question from the
    same article, and each of them went through the gates separately.
    """

    title: str
    article: object | None = None
    outcomes: list = field(default_factory=list)
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
        except (AttributeError, ValueError):  # not a real console; already fine
            pass


def _short(title: str, width: int = 44) -> str:
    return title if len(title) <= width else title[: width - 1] + "…"


def _progress(accepted, rejected, skipped, limit, started) -> str:
    """One line of where the run stands, and what it is on course for."""
    done = len(accepted)
    elapsed = time.monotonic() - started
    parts = [f"{done}/{limit} accepted", f"{len(rejected)} dropped", f"{skipped} skipped"]

    if done and done < limit:
        # Rate per accepted question is the only honest basis for an estimate:
        # the skips are nearly free and the drops are not.
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

    # Every source was unreachable. Today's list is worse material, but it beats
    # doing nothing.
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

    # JSON is the machine record; Markdown is the one a person actually reads to
    # answer "is each fake really a fake?", which nothing automatic can.
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
