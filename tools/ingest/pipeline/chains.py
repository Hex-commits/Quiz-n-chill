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

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from ..domain.models import (
    REFRAME_SCHEMA,
    REVIEW_SCHEMA,
    Extraction,
    GeneratedQuestion,
    Review,
    explanation_schema,
    question_schema,
)
from ..domain.validate import slugify, validate
from .illustrate import Illustration, illustrate
from .llm import structured
from .prompts import EXPLAIN, EXTRACT, REFRAME, REPAIR, REVIEW

# A 9B model with an 8K context degrades badly on long inputs, and the lead
# section carries the factual pairings anyway.
MAX_ARTICLE_CHARS = 6000


# -- extract -------------------------------------------------------------


def extract_step(model, subject_slugs: list[str], *, max_chars: int = MAX_ARTICLE_CHARS) -> Runnable:
    """`{article, subjects, repairs}` -> `Extraction`.

    Built once per run: the schema depends only on which subjects exist, which
    does not change mid-batch.
    """

    def prepare(state: dict) -> dict:
        article = state["article"]
        return {
            "title": article.title,
            "text": article.text[:max_chars],
            "subjects": "\n".join(f"- {slug}: {name}" for slug, name in state["subjects"]),
            "repairs": state.get("repairs") or [],
        }

    return (
        RunnableLambda(prepare)
        | EXTRACT
        | structured(model, question_schema(subject_slugs))
        | RunnableLambda(_as_extraction)
    ).with_config(run_name="extract")


def _as_extraction(raw: object) -> Extraction:
    """Parse the reply without letting a bad one raise.

    Constrained decoding should make this unreachable, but a response truncated
    by a full context window still lands here, and it is repairable -- so it
    comes back as an `Extraction` carrying the reason, not an exception.
    """
    if not isinstance(raw, dict):
        return Extraction(error=f"model returned {type(raw).__name__}, expected an object")
    try:
        return Extraction(raw=raw, question=GeneratedQuestion.model_validate(raw))
    except Exception as exc:  # noqa: BLE001 - reported to the repair loop, not raised
        return Extraction(raw=raw, error=f"schema mismatch: {exc}")


# -- check ---------------------------------------------------------------


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


# -- review --------------------------------------------------------------


def review_step(model, *, max_chars: int = MAX_ARTICLE_CHARS) -> Runnable:
    """`{article, question}` -> `Review`."""

    def prepare(state: dict) -> dict:
        return {
            "text": state["article"].text[:max_chars],
            "title": state["question"].title,
            "pairs": _render_pairs(state["question"]),
        }

    verdict = RunnableLambda(prepare) | REVIEW | structured(model, REVIEW_SCHEMA)

    # The question is carried alongside the verdict so the findings can be
    # checked against it -- see `as_review`.
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
        # A finding has to name an answer that is actually on the board. A small
        # model will occasionally report a category name, or a term from the
        # article that never made it into the question; neither is something the
        # repair loop could act on.
        on_the_board = {answer.casefold() for answer in question.answers}
        wrongly_flagged = [item for item in misplaced if item.casefold() not in on_the_board]
        misplaced = [item for item in misplaced if item.casefold() in on_the_board]

        # A dropped finding usually has a matching sentence in `problems`, and
        # leaving that behind would block the question just as effectively as
        # the finding did. Matching by name is crude, but the alternative is
        # trusting prose we have already decided is wrong.
        if wrongly_flagged:
            problems = [
                problem
                for problem in problems
                if not any(item in problem for item in wrongly_flagged)
            ]

    survived = bool(problems or misplaced)

    # The reviewer named specifics and every one of them turned out to be
    # impossible of this question. There is no complaint left to repair against,
    # so the rejection had no substance and the question passes. This is
    # distinct from a bare `ok: false` with nothing named, below, which stays a
    # rejection -- one is a critic that was wrong, the other is a critic that
    # would not say.
    if was_specific and not survived:
        return Review(ok=True)

    # A model that lists faults but still says `ok: true` is contradicting
    # itself; trust the specifics over the summary flag.
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


# -- explain -------------------------------------------------------------


def explain_step(model, *, max_chars: int = MAX_ARTICLE_CHARS) -> Runnable:
    """`{article, question}` -> `{answer: one short line}`.

    Runs last, only on a question that already passed both gates, because an
    explanation for an answer that is about to be repaired is a wasted call.

    Its output is decoration, never a verdict: nothing here can reject a
    question. That is why it is not a third gate.
    """

    def prepare(state: dict) -> dict:
        return {
            "text": state["article"].text[:max_chars],
            "title": state["question"].title,
            "pairs": _render_pairs(state["question"]),
        }

    def bind(state: dict) -> Runnable:
        # The grammar enumerates this question's own answers, so the model
        # cannot explain something that is not on the board.
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


# -- illustrate ----------------------------------------------------------


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


# -- repair --------------------------------------------------------------


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
