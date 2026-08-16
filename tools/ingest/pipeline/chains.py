"""The pipeline's steps, one LCEL chain each.

Every step is a single `Runnable` that takes domain objects in and gives domain
objects back -- an `Extraction`, a list of complaints, a `Review`. The prompt
formatting, the model call and the parsing are links in that one chain rather
than three things a caller has to remember to do in order:

    prepare | prompt | model | parse

`graph.py` decides which step runs when and never touches a prompt or a schema;
this module knows how to run one step and nothing about what comes next. Each
chain carries a `run_name`, so a stream event or a callback says "extract"
rather than "RunnableSequence".
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from ..domain.models import (
    DEFAULT_DRAFTS,
    REFRAME_SCHEMA,
    REVIEW_SCHEMA,
    VET_SCHEMA,
    Extraction,
    GeneratedPair,
    GeneratedQuestion,
    Review,
    explanation_schema,
    more_pairs_schema,
    questions_schema,
    selection_schema,
)
from ..domain.validate import slugify, validate
from .augment import MAX_DOCUMENTS, Augmentation, augment
from .broaden import MAX_NEIGHBOURS, Broadening, broaden
from .vet import Verdict, vet
from .illustrate import Illustration, illustrate
from .llm import structured
from .prompts import (
    AUGMENT,
    EXPLAIN,
    EXTRACT,
    NEIGHBOUR_ARTICLE,
    NEIGHBOURS_NOTE,
    REFRAME,
    REPAIR,
    REVIEW,
    SELECT,
    VET,
)

MAX_ARTICLE_CHARS = 6000

# How much of each borrowed article a step is shown. Smaller than the article's
# own budget on purpose: it only has to contain the sentence a pair was taken
# from, and three neighbours at full length would push the article the question
# is about out of the model's attention entirely.
EXTRA_SOURCE_CHARS = 3_000

# And how many of them. `augment` may read four articles per round over two
# rounds, so without a count the per-document cap still allows 24k characters of
# neighbours on top of the article.
MAX_EXTRA_SOURCES = 2



def neighbours(extras: list | None) -> str:
    """The articles `broaden` fetched, as a block for the extract prompt.

    Empty string when there are none, which is the case for every article that
    was not declined -- the note explaining what the further texts are for only
    appears when there are further texts.

    Capped exactly as `source_text` caps them and for the same reason: this block
    sits on top of the article's own 6000 characters, and the question still has
    to be written by a model that has read all of it.
    """
    extras = list(extras or [])[:MAX_EXTRA_SOURCES]
    if not extras:
        return ""
    blocks = "".join(
        NEIGHBOUR_ARTICLE.format(title=extra.title, text=extra.text[:EXTRA_SOURCE_CHARS])
        for extra in extras
    )
    return f"\n{NEIGHBOURS_NOTE}{blocks}\n"


def extract_step(
    model,
    subject_slugs: list[str],
    *,
    drafts: int = DEFAULT_DRAFTS,
    max_chars: int = MAX_ARTICLE_CHARS,
) -> Runnable:
    """`{article, subjects, repairs}` -> `Extraction` holding up to `drafts` questions.

    Built once per run: the schema depends only on which subjects exist and how
    many drafts were asked for, neither of which changes mid-batch.
    """

    def prepare(state: dict) -> dict:
        article = state["article"]
        return {
            "title": article.title,
            "text": article.text[:max_chars],
            # Empty on all but the second pass at an article `extract` already
            # declined -- see `neighbours` below.
            "extras": neighbours(state.get("extras")),
            "subjects": "\n".join(f"- {slug}: {name}" for slug, name in state["subjects"]),
            "drafts": drafts,
            "repairs": state.get("repairs") or [],
        }

    return (
        RunnableLambda(prepare)
        | EXTRACT
        | structured(model, questions_schema(subject_slugs, drafts))
        | RunnableLambda(_as_extraction)
    ).with_config(run_name="extract")


def _as_extraction(raw: object) -> Extraction:
    """Parse the reply without letting a bad one raise.

    Constrained decoding should make this unreachable, but a response truncated
    by a full context window still lands here, and it is repairable -- so it
    comes back as an `Extraction` carrying the reason, not an exception.

    A bare question object is accepted as a batch of one. The grammar asks for
    `{"questions": [...]}`, but a model that answers with the object itself has
    given a usable answer and there is nothing to gain by failing it.
    """
    if not isinstance(raw, dict):
        return Extraction(error=f"model returned {type(raw).__name__}, expected an object")
    batch = raw.get("questions") if "questions" in raw else [raw]
    if not isinstance(batch, list) or not batch:
        return Extraction(raw=raw, error="model returned no questions")
    try:
        return Extraction(
            raw=raw,
            questions=[GeneratedQuestion.model_validate(entry) for entry in batch],
        )
    except Exception as exc:  # noqa: BLE001 - reported to the repair loop, not raised
        return Extraction(raw=raw, error=f"schema mismatch: {exc}")


@dataclass(frozen=True)
class Selection:
    """Which drafts `select` kept, and what it said about the batch."""

    questions: tuple[GeneratedQuestion, ...] = ()
    detail: str = ""


def select_step(model, *, may_reject: bool = False) -> Runnable:
    """`{article, questions}` -> `Selection`.

    Runs before both gates, on drafts nothing has checked yet, because the
    judgement is not about correctness -- it is whether answering the question
    teaches the player anything, and that is worth knowing before paying for a
    review of it.

    A single draft is returned unjudged. There is nothing to choose between, and
    `check` and `review` are still ahead of it either way.

    **`may_reject` is what an empty selection is allowed to mean.** Rejecting a
    whole batch is the most valuable thing this step can do and the most damaging
    thing a bad judge can do with it -- measured on `glm4:9b`, one run kept both
    drafts of `Periodensystem` including a two-pair board with one answer used
    twice, and the next kept *none* of `Kaffee` under a verdict that said in the
    same sentence that some of them asked real questions. The second reading costs
    an article outright.

    So with `may_reject` false the step chooses but cannot condemn: an empty
    selection is read as no opinion and the first draft goes through, where `check`
    and `review` are waiting for it either way. `cli.py` turns it on when
    `INGEST_JUDGE_MODEL` names a judge other than the run's own model -- a judge
    somebody chose gets to say no, an unproven one only gets to sort.

    The `keep` labels are filtered on the way back in. The enum makes an
    out-of-range label impossible to emit; the filter is for the reply that
    arrives without constrained decoding having held.
    """

    def run(state: dict) -> Selection:
        drafts: list[GeneratedQuestion] = list(state["questions"])
        if len(drafts) < 2:
            return Selection(tuple(drafts), detail="one draft, nothing to choose")

        reply = structured(model, selection_schema(len(drafts))).invoke(
            SELECT.format_messages(
                title=state["article"].title, drafts=_render_drafts(drafts)
            )
        )

        picked = [
            drafts[int(label) - 1]
            for label in dict.fromkeys(reply.get("keep") or [])
            if str(label).isdigit() and 1 <= int(label) <= len(drafts)
        ]
        verdict = " ".join(str(reply.get("verdict") or "").split())
        if not picked and not may_reject:
            return Selection(
                (drafts[0],),
                detail=f"kept 1/{len(drafts)} -- judge kept none, not trusted to: {verdict}"[:200],
            )
        return Selection(
            tuple(picked),
            detail=f"kept {len(picked)}/{len(drafts)} -- {verdict}"[:200],
        )

    return RunnableLambda(run).with_config(run_name="select")


def _render_drafts(drafts: list[GeneratedQuestion]) -> str:
    """The batch as the select prompt sees it: numbered, with the whole board.

    The full pairing rather than a title, because the title is the model's own
    summary of what it wrote and the question of whether a board is trivial can
    only be answered by looking at the pairs.
    """
    blocks = []
    for index, question in enumerate(drafts, start=1):
        blocks.append(
            f"{index}. {question.title} [{question.difficulty}]\n{_render_pairs(question)}"
        )
    return "\n\n".join(blocks)



def check_step(*, subject_slugs: set[str], taken_slugs: set[str] | None = None) -> Runnable:
    """`GeneratedQuestion` -> list of complaints. Pure, local, instant.

    Slug hygiene happens here rather than at write time, so the validator judges
    the slug we would actually store instead of the model's raw suggestion.

    The slug is **reserved** as it is assigned, under a lock, because articles
    are processed concurrently: two workers that both derive `periodensystem`
    would otherwise each find it free and both keep it, and only the second
    insert would fail -- losing a question to a race that is invisible until it
    happens. Reserving costs a wasted suffix when the question is later
    rejected, which is the cheaper mistake.
    """
    taken = taken_slugs if taken_slugs is not None else set()
    reserving = threading.Lock()

    def check(question: GeneratedQuestion) -> list[str]:
        if question.slug:
            with reserving:
                question.slug = slugify(question.slug)
                if question.slug in taken:
                    question.slug = _free_slug(question.slug, taken)
                taken.add(question.slug)
        return validate(question, subject_slugs=subject_slugs)

    return RunnableLambda(check).with_config(run_name="check")


def _free_slug(slug: str, taken: set[str]) -> str:
    for suffix in range(2, 100):
        candidate = f"{slug}-{suffix}"
        if candidate not in taken:
            return candidate
    return f"{slug}-x"


def _render_pairs(question: GeneratedQuestion) -> str:
    """The pairing as the model sees it in the review and explain prompts."""
    rendered = "\n".join(f"- {pair.label} -> {pair.answer}" for pair in question.pairs)
    return rendered or "- (keine)"



def source_text(state: dict, *, max_chars: int = MAX_ARTICLE_CHARS) -> str:
    """The article, plus the neighbours `augment` borrowed pairs from.

    `extras` are the other articles a pair may have come from. Any step asked to
    judge or describe a pair needs the text that supports it: without these the
    reviewer rejects every borrowed pair as unsupported, and the explainer
    invents a reason for one instead of reading it.

    Appended after the article rather than merged into it, each one separately
    capped, and *counted* -- two augment rounds of four documents each would
    otherwise put 30k characters in front of a model with an 8k context, and the
    per-document cap alone does not stop that.
    """
    text = state["article"].text[:max_chars]
    for extra in (state.get("extras") or [])[:MAX_EXTRA_SOURCES]:
        text += (
            f"\n\n--- Zusätzlicher Quelltext: {extra.title} ---\n"
            f"{extra.text[:EXTRA_SOURCE_CHARS]}"
        )
    return text


def review_step(model, *, max_chars: int = MAX_ARTICLE_CHARS) -> Runnable:
    """`{article, question, extras}` -> `Review`."""

    def prepare(state: dict) -> dict:
        return {
            "text": source_text(state, max_chars=max_chars),
            "title": state["question"].title,
            "pairs": _render_pairs(state["question"]),
        }

    verdict = RunnableLambda(prepare) | REVIEW | structured(model, REVIEW_SCHEMA)

    return (
        RunnablePassthrough.assign(verdict=verdict)
        | RunnableLambda(lambda state: as_review(state["verdict"], state["question"]))
    ).with_config(run_name="review")


def as_review(raw: dict, question: GeneratedQuestion | None = None) -> Review:
    """Turn the model's verdict into complaints the repair loop can act on.

    The reviewer is a small model too, and its output gets the same treatment as
    the generator's: checked, not trusted. `question` is what makes that
    possible -- with it, findings that cannot be true of this question are
    dropped rather than sent round the repair loop forever.
    """
    misplaced = _clean(raw.get("misplaced_items"))
    problems = _clean(raw.get("problems"))
    was_specific = bool(misplaced or problems)

    if question is not None:
        on_the_board = {answer.casefold() for answer in question.answers}
        wrongly_flagged = [item for item in misplaced if item.casefold() not in on_the_board]
        misplaced = [item for item in misplaced if item.casefold() in on_the_board]

        if wrongly_flagged:
            problems = [
                problem
                for problem in problems
                if not any(item in problem for item in wrongly_flagged)
            ]

    survived = bool(problems or misplaced)

    if was_specific and not survived:
        return Review(ok=True)

    ok = bool(raw.get("ok")) and not survived

    if not ok and not problems:
        problems = [
            f"'{item}' does not belong to the category it is paired with" for item in misplaced
        ] or ["the reviewer rejected the question without saying why"]

    return Review(ok=ok, problems=problems, misplaced_items=misplaced)


def skipped_review(reason: str) -> Review:
    """The reviewer could not run at all.

    Reads as `ok` so a dead reviewer cannot discard a question that already
    passed the structural gate -- but `skipped` makes the report say it went
    unchecked rather than imply it passed.
    """
    return Review(ok=True, problems=[f"review skipped: {reason}"], skipped=True)


def _clean(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def vet_step(model) -> Runnable:
    """`{question, candidates}` -> `Verdict`.

    One model call per candidate. `model` is separate from the run's model on
    purpose -- this judgement is the one that most needs a stronger one, and
    `INGEST_JUDGE_MODEL` is how it gets it without doubling the cost of extract.
    """

    def run(state: dict) -> Verdict:
        question = state["question"]
        board = _render_pairs(question)
        decide = structured(model, VET_SCHEMA)

        def judge(_question, candidate) -> tuple[bool, str]:
            reply = decide.invoke(
                VET.format_messages(
                    board=board,
                    candidate=f"{candidate.label} -> {candidate.answer}",
                )
            )
            why = (reply.get("answers_it") or "").strip()
            return bool(reply.get("fits")), why or "asks a different question"

        return vet(question, list(state["candidates"]), judge)

    return RunnableLambda(run).with_config(run_name="vet")


def augment_step(
    model,
    finder,
    *,
    max_documents: int = MAX_DOCUMENTS,
    max_chars: int = MAX_ARTICLE_CHARS,
) -> Runnable:
    """`{question, document, needed}` -> `Augmentation`.

    Wires a model into `augment`, which holds the decision and knows nothing
    about prompts. One model call per article read, and reading stops as soon as
    the shortfall is covered.

    `finder` is a `RelatedDocuments`; nothing here knows it is Wikipedia.
    """

    def run(state: dict) -> Augmentation:
        question = state["question"]

        def find_pairs(document, needed: int) -> list[GeneratedPair]:
            reply = structured(model, more_pairs_schema(needed)).invoke(
                AUGMENT.format_messages(
                    title=question.title,
                    pairs=_render_pairs(question),
                    source_title=document.title,
                    text=document.text[:max_chars],
                    needed=needed,
                )
            )
            return [
                GeneratedPair(label=pair["label"], answer=pair["answer"])
                for pair in (reply.get("pairs") or [])
            ]

        return augment(
            question,
            state["document"],
            finder,
            find_pairs,
            needed=state["needed"],
            max_documents=max_documents,
        )

    return RunnableLambda(run).with_config(run_name="augment")


def broaden_step(finder, *, max_neighbours: int = MAX_NEIGHBOURS) -> Runnable:
    """`{document, skip}` -> `Broadening`. No model call.

    The cheapest step in the pipeline: a search and at most `max_neighbours`
    fetches. What it buys is the *next* extract call, which is the most expensive
    one -- so the graph, not this chain, decides when the trade is worth making.

    `finder` is a `RelatedDocuments`, the same protocol `augment` searches
    through; nothing here knows it is Wikipedia.
    """

    def run(state: dict) -> Broadening:
        return broaden(
            state["document"],
            finder,
            max_neighbours=max_neighbours,
            skip=state.get("skip"),
        )

    return RunnableLambda(run).with_config(run_name="broaden")


def explain_step(model, *, max_chars: int = MAX_ARTICLE_CHARS) -> Runnable:
    """`{article, question, extras}` -> `{answer: one short line}`.

    Runs last, only on a question that already passed both gates, because an
    explanation for an answer that is about to be repaired is a wasted call.

    Its output is decoration, never a verdict: nothing here can reject a
    question. That is why it is not a third gate.

    Gets `extras` for the same reason `review` does: asked to justify a borrowed
    pair without the article it came from, the model has nothing to read and
    answers from its own knowledge instead.
    """

    def prepare(state: dict) -> dict:
        return {
            "text": source_text(state, max_chars=max_chars),
            "title": state["question"].title,
            "pairs": _render_pairs(state["question"]),
        }

    def bind(state: dict) -> Runnable:
        return structured(model, explanation_schema(state["question"].all_items))

    return (
        RunnablePassthrough.assign(
            raw=lambda state: (RunnableLambda(prepare) | EXPLAIN | bind(state)).invoke(state)
        )
        | RunnableLambda(lambda state: as_explanations(state["raw"], state["question"]))
    ).with_config(run_name="explain")


def as_explanations(raw: dict, question: GeneratedQuestion) -> dict[str, str]:
    """Keep the lines that name a real answer, drop anything else.

    Constrained decoding should make a stray label impossible, but a duplicate
    is still possible -- first one wins.
    """
    known = {item.casefold(): item for item in question.all_items}
    out: dict[str, str] = {}

    for entry in raw.get("explanations", []) or []:
        if not isinstance(entry, dict):
            continue
        label = known.get(str(entry.get("answer", "")).strip().casefold())
        why = " ".join(str(entry.get("why", "")).split())
        if label and why and label not in out:
            out[label] = why
    return out



def illustrate_step(provider) -> Runnable:
    """`{question, document}` -> `Illustration`. No model call.

    The only step that reaches an `ImageProvider`, and the only one that decides
    what *kind* of question this is. It never rejects: a question with no usable
    pictures simply stays a text question, which is why it sits after both gates
    rather than beside them.
    """

    def decide(state: dict) -> Illustration:
        return illustrate(state["question"], state["document"], provider)

    return RunnableLambda(decide).with_config(run_name="illustrate")


def reframe_step(model) -> Runnable:
    """`{question}` -> `{title, description}` for a flipped pairing.

    Runs only on a flip, which is why it is the cheapest model call in the
    pipeline by frequency. The pairs go in already reversed and come back
    untouched -- nothing reads a pair out of this reply, so the model cannot
    change the question by answering it badly, only name it badly.
    """

    def prepare(state: dict) -> dict:
        return {
            "pairs": _render_pairs(state["question"]),
            "title": state["question"].title,
        }

    return (
        RunnableLambda(prepare) | REFRAME | structured(model, REFRAME_SCHEMA)
    ).with_config(run_name="reframe")



def repair_step() -> Runnable:
    """`{raw, problems}` -> the two messages that reopen the conversation.

    The rejected answer goes back in as an assistant turn. Without it the model
    is being asked to fix something it can no longer see, and it tends to start
    over and reintroduce the same fault.
    """

    def turn(state: dict) -> list[BaseMessage]:
        import json

        problems = "\n".join(f"- {problem}" for problem in state["problems"])
        return [
            AIMessage(json.dumps(state.get("raw") or {}, ensure_ascii=False)),
            HumanMessage(REPAIR.format(problems=problems)),
        ]

    return RunnableLambda(turn).with_config(run_name="repair")
