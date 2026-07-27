"""The pipeline's control flow, and nothing else.

One article goes in; a Zuordnungsfrage that passed both gates comes out, or a
list of reasons it did not.

    START -> extract -> check --(clean)--> review --(clean)--> END
                 |         |                  |
                 |     (problems)         (problems)
                 |         |                  |
                 +---------+--> repair -------+
                               (if attempts left, else END)

Every node here is four lines: run one step from `chains.py`, return what
changed. No prompts, no schemas, no parsing -- those belong to the step. What
this module owns is the part that was genuinely hard to read as a loop: which
step runs next, and why.

Why a graph rather than a linear chain. The interesting behaviour is not "call
the model, parse the answer" -- it is *what happens when the answer is wrong*.
Both gates feed the same repair edge, repair loops back into extract, and the
attempt budget decides whether that edge exists at all. Written as a `for` loop
that logic was spread across a counter, two `if`s and an early `return`; as
edges it is the thing you read.

The state is a Pydantic model, so a node returning a key that does not exist is
an error rather than a silent no-op. `repairs` carries an `add_messages`
reducer: the repair node returns just the two new turns and LangGraph appends
them, which is why attempt three still sees what went wrong in attempts one and
two.
"""

from __future__ import annotations

import time
from typing import Annotated, Callable

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import GeneratedQuestion, Review
from ..sources.wikipedia import Article
from .chains import skipped_review
# Aliased: `explain` is also the name of a node and of this module's
# build_graph parameter, and the shadowing is silent until it bites.
from .llm import explain as describe_failure


class IngestState(BaseModel):
    """What travels between the nodes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    article: Article
    subjects: list[tuple[str, str]] = Field(default_factory=list)
    repairs: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
    question: GeneratedQuestion | None = None
    problems: list[str] = Field(default_factory=list)
    review: Review | None = None
    attempt: int = 1
    max_attempts: int = 3
    # Set when there is nothing left to repair -- the model declined, or the
    # transport failed. A verdict, not a defect: retrying only wastes calls.
    stop: bool = False
    # Why the explain step produced nothing, if it failed. Recorded rather
    # than swallowed: the step is allowed to fail without costing the
    # question, but a silent failure hid a genuine bug once already.
    explain_error: str = ""


class Outcome(BaseModel):
    """The result of running one article through the graph."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    question: GeneratedQuestion
    problems: list[str] = Field(default_factory=list)
    review: Review | None = None
    steps: list[str] = Field(default_factory=list)
    attempts: int = 1
    seconds: float = 0.0

    @property
    def accepted(self) -> bool:
        return not self.problems


def build_graph(
    *,
    extract: Runnable,
    check: Runnable,
    review: Runnable | None = None,
    explain: Runnable | None = None,
    repair: Runnable,
):
    """Wire the steps together. Compiled once per run and reused per article.

    With `review=None` the review node is left out of the graph entirely rather
    than added and routed around, so a `--no-review` run *is* the smaller graph
    instead of merely behaving like one.
    """

    def extract_node(state: IngestState) -> dict:
        try:
            result = extract.invoke(
                {"article": state.article, "subjects": state.subjects, "repairs": state.repairs}
            )
        except Exception as exc:  # noqa: BLE001 - a dead model is not repairable
            reason = describe_failure(exc)
            return {
                "question": GeneratedQuestion(usable=False, reason=reason),
                "problems": [reason],
                "stop": True,
            }

        if result.question is None:
            return {"raw": result.raw, "problems": [result.error]}

        if not result.question.usable:
            reason = result.question.reason or "no reason given"
            return {
                "raw": result.raw,
                "question": result.question,
                "problems": [f"model declined: {reason}"],
                "stop": True,
            }

        return {"raw": result.raw, "question": result.question, "problems": []}

    def check_node(state: IngestState) -> dict:
        return {"problems": check.invoke(state.question)}

    def review_node(state: IngestState) -> dict:
        try:
            verdict = review.invoke({"article": state.article, "question": state.question})
        except Exception as exc:  # noqa: BLE001 - must not discard a passing question
            verdict = skipped_review(describe_failure(exc))
        return {"review": verdict, "problems": [] if verdict.ok else verdict.problems}

    def explain_node(state: IngestState) -> dict:
        """One short line per answer. Never a gate.

        A question that reached here has already passed everything that decides
        whether it is correct, so a failure to explain it costs the explanations
        and nothing else.
        """
        try:
            lines = explain.invoke({"article": state.article, "question": state.question})
        except Exception as exc:  # noqa: BLE001 - decoration must not fail a question
            return {"explain_error": describe_failure(exc)}
        return {"question": state.question.model_copy(update={"explanations": lines})}

    def repair_node(state: IngestState) -> dict:
        return {
            "repairs": repair.invoke({"raw": state.raw, "problems": state.problems}),
            "attempt": state.attempt + 1,
        }

    # -- routing: the three "what now" decisions, each answered in one place --

    def retry_or_stop(state: IngestState) -> str:
        return "repair" if state.attempt < state.max_attempts else END

    def after_extract(state: IngestState) -> str:
        if state.stop:
            return END
        return "check" if not state.problems else retry_or_stop(state)

    def done(state: IngestState) -> str:
        """Where a question goes once nothing can reject it any more."""
        return "explain" if explain is not None else END

    def after_check(state: IngestState) -> str:
        if state.problems:
            return retry_or_stop(state)
        return "review" if review is not None else done(state)

    def after_review(state: IngestState) -> str:
        return done(state) if not state.problems else retry_or_stop(state)

    builder = StateGraph(IngestState)
    builder.add_node("extract", extract_node)
    builder.add_node("check", check_node)
    builder.add_node("repair", repair_node)

    builder.add_edge(START, "extract")
    builder.add_conditional_edges("extract", after_extract, ["check", "repair", END])
    builder.add_edge("repair", "extract")

    # `explain` is a terminal decoration, so it has one outgoing edge and no say
    # in whether the question survives.
    #
    # END stays in every target list even when `explain` is present. A clean
    # question routes to `explain`, but a rejected one with no attempts left
    # goes straight to END from the same branch -- leave END out and LangGraph
    # raises `KeyError: '__end__'` on exactly that path.
    exits = ["explain"] if explain is not None else []
    if explain is not None:
        builder.add_node("explain", explain_node)
        builder.add_edge("explain", END)

    if review is not None:
        builder.add_node("review", review_node)
        builder.add_conditional_edges("check", after_check, ["review", "repair", *exits, END])
        builder.add_conditional_edges("review", after_review, ["repair", *exits, END])
    else:
        builder.add_conditional_edges("check", after_check, ["repair", *exits, END])

    return builder.compile()


def run_article(
    graph,
    article: Article,
    subjects: list[tuple[str, str]],
    *,
    max_attempts: int = 3,
    on_step: Callable[[str, str], None] | None = None,
) -> Outcome:
    """Run one article and record what each node did.

    Streamed rather than invoked, because the per-node updates are the whole
    debuggability argument for the graph: `steps` becomes a plain-language
    account of the run -- what was extracted, what each gate said, how many
    repairs it took. It goes into the report and can be printed live with
    `--trace`, and unlike a hosted trace it stays on this machine.

    The state read here is LangGraph's own, never a copy reassembled from the
    updates: reapplying them would mean reimplementing the reducers, and a
    second implementation of `add_messages` is one that can drift.
    """
    state = IngestState(
        article=article, subjects=subjects, max_attempts=max_attempts
    )
    steps: list[str] = []

    # `repair -> extract` is two supersteps per attempt plus the gates, so the
    # default limit of 25 would cap out around five attempts. Scale it with the
    # budget the caller actually asked for.
    config = {"recursion_limit": max_attempts * 6 + 10}

    # Two stream modes at once, because neither is enough alone: `updates` says
    # which node ran but only what it changed, `values` carries the whole state
    # but not whose work it was. Together they remove any need to re-apply the
    # updates here -- LangGraph stays the single place that knows how state is
    # merged, reducers included.
    #
    # They arrive interleaved as (mode, chunk), the node name just ahead of the
    # state it produced, after one opening `values` for the initial state.
    pending: str | None = None

    # Timed per node, because "which step is slow" is the first question anyone
    # asks of a long run, and the two model calls dominate by orders of
    # magnitude over the free local check.
    started = time.monotonic()
    last = started

    for mode, chunk in graph.stream(state, config=config, stream_mode=["updates", "values"]):
        if mode == "updates":
            # One node per superstep: nothing in this graph runs in parallel.
            pending = next(iter(chunk), None)
            continue

        state = IngestState.model_validate(chunk)
        if pending is None:
            continue  # the opening state, before any node has run

        now = time.monotonic()
        line = f"{pending:<9}{now - last:>6.1f}s  {_describe(pending, state)}"
        last = now
        steps.append(line)
        if on_step:
            on_step(pending, line)
        pending = None

    return Outcome(
        question=state.question or GeneratedQuestion(usable=False, reason="no attempt made"),
        problems=list(state.problems),
        review=state.review,
        steps=steps,
        attempts=state.attempt,
        seconds=time.monotonic() - started,
    )


def _describe(node: str, state: IngestState) -> str:
    """One line per node, written for someone reading a failed run."""
    problems = state.problems

    if node == "extract":
        question = state.question
        if state.stop or question is None or not question.usable:
            return problems[0] if problems else "no question"
        if problems:
            return problems[0]
        return f"{len(question.pairs)} pairs"

    if node == "check":
        return "ok" if not problems else f"{len(problems)} problem(s): {problems[0]}"

    if node == "review":
        if state.review is not None and state.review.skipped:
            return "skipped (reviewer unavailable)"
        return "ok" if not problems else f"{len(problems)} problem(s): {problems[0]}"

    if node == "explain":
        if state.explain_error:
            return f"none -- {state.explain_error}"
        question = state.question
        written = len(question.explanations) if question else 0
        total = len(question.all_items) if question else 0
        return f"{written}/{total} answers explained"

    if node == "repair":
        return f"retrying, attempt {state.attempt}"

    return ""
