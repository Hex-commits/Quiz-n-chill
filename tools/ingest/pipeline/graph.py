"""The pipeline's control flow, and nothing else.

One article goes in; a Zuordnungsfrage that passed both gates comes out, or a
list of reasons it did not.

    START -> extract -> select -> check --(clean)--> review --(clean)--> END
                 |                  |                  |
                 |              (problems)         (problems)
                 |                  |                  |
                 +------------------+--> repair -------+
                 |                      (if attempts left, else END)
                 |
             (declined -- the article holds too little for any question)
                 |
                 +--> broaden --> back to extract with the neighbours attached
                                  (once per article, else END)

`extract` writes several drafts from one article and `select` says which are
worth playing -- it may keep more than one. The first goes on down the graph; the
rest come back out in `Outcome.spares`, and `run_all` puts each of those in at
`check` through the same conditional START edge.

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
an error rather than a silent no-op. `repairs` carries the `recent_repairs`
reducer: the repair node returns just the two new turns and LangGraph appends
them, which is why attempt three still sees what went wrong in attempts one and
two -- bounded, so `--attempts 10` cannot grow the prompt past the context.
"""

from __future__ import annotations

import time
from concurrent.futures import Executor
from typing import Annotated, Callable

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import GeneratedQuestion, Review
from ..sources.wikipedia import Article
from .chains import skipped_review
from ..domain.rules import MIN_PAIRS
from ..domain.validate import only_needs_more_pairs
from .augment import merge
from .broaden import MAX_ROUNDS as MAX_BROADENINGS
from .vet import MAX_ROUNDS
from .illustrate import flip, keep_illustrated
from .llm import explain as describe_failure

# How many rejected attempts stay in the extract conversation. Each one is a
# rejected answer plus the complaints about it, on top of a system prompt and
# 6000 characters of article -- so the transcript is the one part of that prompt
# that grows without a bound of its own. Two is what the default `--attempts 3`
# accumulates anyway; the bound is what keeps `--attempts 10` from quietly
# running the extract call out of context, where a truncated reply is reported as
# a schema mismatch and looks like the model's fault.
KEEP_REPAIRS = 2


def recent_repairs(
    existing: list[BaseMessage] | None, new: list[BaseMessage] | None
) -> list[BaseMessage]:
    """`add_messages`, with a sliding window over the last `KEEP_REPAIRS` tries.

    Whole attempts, never half of one: the window is a multiple of two, so the
    model is never shown complaints about an answer that has been dropped from
    the conversation.
    """
    return add_messages(existing or [], new or [])[-2 * KEEP_REPAIRS :]


class IngestState(BaseModel):
    """What travels between the nodes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    article: Article
    subjects: list[tuple[str, str]] = Field(default_factory=list)
    repairs: Annotated[list[BaseMessage], recent_repairs] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
    question: GeneratedQuestion | None = None
    # Every usable question `extract` wrote this attempt, and the ones `select`
    # judged worth keeping beyond the first. `run_all` puts each spare back
    # through the graph on its own.
    drafts: list[GeneratedQuestion] = Field(default_factory=list)
    spares: list[GeneratedQuestion] = Field(default_factory=list)
    select_detail: str = ""
    problems: list[str] = Field(default_factory=list)
    review: Review | None = None
    attempt: int = 1
    max_attempts: int = 3
    images: dict = Field(default_factory=dict)
    flipped: bool = False
    stop: bool = False
    # `extract` said the article gives no question at all -- as opposed to
    # stopping because the model could not be reached. Only the first is worth
    # reading the neighbours for, and only the question itself can tell them
    # apart: both end with an unusable question and a stop.
    declined: bool = False
    explain_error: str = ""
    illustrate_detail: str = ""
    illustrate_error: str = ""
    # The direction `reframe` said it was writing for, kept for the trace: it is
    # the only model output no gate downstream can check.
    reframe_detail: str = ""
    # How many `augment` passes this question has had. A rejection sends it
    # round again to look somewhere new, bounded by `vet.MAX_ROUNDS`. This is
    # also what stops `augment -> check -> augment` looping.
    augment_rounds: int = 0
    # Titles already read, so a second pass does not re-read them.
    read_titles: list = Field(default_factory=list)
    vet_detail: str = ""
    # Every article beyond the first that this question was written from --
    # `augment`'s borrowings and `broaden`'s neighbours together. Handed to
    # `review` and `explain`, which would otherwise judge or justify a pair
    # against an article that never mentions it.
    extra_sources: list = Field(default_factory=list)
    # The same articles, split by which step went and got them: they are worth
    # very different things to someone reading the report. A borrowed pair went
    # onto a finished board without `review` being able to say whether it belongs
    # there; a neighbour was simply more to read before the question existed.
    borrowed_titles: list = Field(default_factory=list)
    broadened_titles: list = Field(default_factory=list)
    augment_detail: str = ""
    augment_error: str = ""
    # How many times the article was widened with similar pages. One is the
    # bound (`broaden.MAX_ROUNDS`), and it is also what stops
    # `extract -> broaden -> extract` going round for ever.
    broaden_rounds: int = 0
    broaden_detail: str = ""
    broaden_error: str = ""
    # Borrowed pairs waiting on `vet`. Held off the question until judged, so a
    # rejected pair never has to be removed from a board it was on.
    candidates: list = Field(default_factory=list)


class Outcome(BaseModel):
    """The result of running one article through the graph."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    question: GeneratedQuestion
    problems: list[str] = Field(default_factory=list)
    review: Review | None = None
    steps: list[str] = Field(default_factory=list)
    attempts: int = 1
    seconds: float = 0.0
    images: dict = Field(default_factory=dict)
    flipped: bool = False
    # Titles of the articles that supplied extra pairs, for the report. Empty
    # for the overwhelming majority, which never needed topping up.
    borrowed_from: list = Field(default_factory=list)
    # Titles of the similar articles `broaden` read after this one was declined
    # for holding too little. Empty unless the article was declined and saved.
    widened_from: list = Field(default_factory=list)
    # The other questions `select` kept from the same article, still unchecked.
    # `run_all` runs each of these through the graph in turn; a caller using
    # `run_article` directly gets them here and may ignore them.
    spares: list[GeneratedQuestion] = Field(default_factory=list)
    # What `select` made of the batch, in words, for the report.
    select_detail: str = ""

    @property
    def accepted(self) -> bool:
        return not self.problems

    @property
    def is_picture(self) -> bool:
        return bool(self.images)


# Which difficulties are worth searching other articles for. `easy` is left
# out: the whole point of the step is to spend effort on questions that deserve
# it, and a thin easy question is not one.
AUGMENT_DIFFICULTIES = frozenset({"medium", "hard"})


def build_graph(
    *,
    extract: Runnable,
    check: Runnable,
    select: Runnable | None = None,
    review: Runnable | None = None,
    broaden: Runnable | None = None,
    augment: Runnable | None = None,
    vet: Runnable | None = None,
    illustrate: Runnable | None = None,
    reframe: Runnable | None = None,
    explain: Runnable | None = None,
    repair: Runnable,
):
    """Wire the steps together. Compiled once per run and reused per article.

    With `review=None` the review node is left out of the graph entirely rather
    than added and routed around, so a `--no-review` run *is* the smaller graph
    instead of merely behaving like one.

    The entry edge is conditional. A state that already carries a question skips
    `extract` and starts at `check` -- which is how `run_all` puts a question
    `select` kept but did not put first through the rest of the pipeline, without
    a second graph or a second copy of the gates.

    `broaden` is the one edge that leads *backwards* out of a verdict. A decline
    used to be the end of the article; with the step wired it buys one more
    reading, with a couple of similar pages attached to what `extract` sees. It
    is bounded to a single round and it cannot rescue anything on its own -- the
    second pass faces the same gates as the first.

    `illustrate` is where a clean question goes; `explain` is where it goes after
    that. Both are terminal decorations with one outgoing edge and no say in
    whether the question survives.

    END stays in every target list even when `explain` is present. A clean
    question routes to `explain`, but a rejected one with no attempts left goes
    straight to END from the same branch -- leave END out and LangGraph raises
    `KeyError: '__end__'` on exactly that path.
    """

    def extract_node(state: IngestState) -> dict:
        try:
            result = extract.invoke(
                {
                    "article": state.article,
                    "subjects": state.subjects,
                    "repairs": state.repairs,
                    # Empty on the first pass at every article. On the second
                    # pass at one this step already declined, these are the
                    # similar pages `broaden` went and read -- the material the
                    # decline said was missing.
                    "extras": state.extra_sources,
                }
            )
        except Exception as exc:  # noqa: BLE001 - a dead model is not repairable
            reason = describe_failure(exc)
            return {
                "question": GeneratedQuestion(usable=False, reason=reason),
                "problems": [reason],
                "stop": True,
            }

        if not result.questions:
            return {"raw": result.raw, "problems": [result.error]}

        # One reply, several drafts. The unusable ones are the model declining an
        # angle, which is the right answer for that angle and says nothing about
        # the others -- so they are dropped here and only a reply where *every*
        # draft declined counts as a refusal of the article.
        drafts = [question for question in result.questions if question.usable]
        if not drafts:
            declined = result.questions[0]
            return {
                "raw": result.raw,
                "question": declined,
                "problems": [f"model declined: {declined.reason or 'no reason given'}"],
                "stop": True,
                "declined": True,
            }

        # `question` is set to the first draft here as well as in `select`, so a
        # run without the select step behaves exactly as it did when extract
        # returned one question.
        return {
            "raw": result.raw,
            "drafts": drafts,
            "question": drafts[0],
            "problems": [],
        }

    def select_node(state: IngestState) -> dict:
        """Choose which of this attempt's drafts are worth a board. Never repairs.

        The step exists because one article usually holds more than one question
        and the drafts are not equally worth playing -- the model is asked which
        teach the player something, and may keep several or none. Keeping none is
        a verdict on the article, like `usable: false`, so it stops rather than
        going round the repair loop: the drafts were well-formed, they were just
        not interesting, and asking the same model again gets the same answer.
        """
        try:
            kept = select.invoke({"article": state.article, "questions": state.drafts})
        except Exception as exc:  # noqa: BLE001 - a dead judge must not cost the batch
            # Falls through with the first draft, which is what a run without
            # this step would have produced anyway.
            return {"select_detail": f"kept 1 of {len(state.drafts)} -- {describe_failure(exc)}"}

        if not kept.questions:
            return {
                "select_detail": kept.detail,
                "problems": [f"none of {len(state.drafts)} drafts kept: {kept.detail}"],
                "stop": True,
            }

        return {
            "question": kept.questions[0],
            "spares": list(kept.questions[1:]),
            "select_detail": kept.detail,
        }

    def check_node(state: IngestState) -> dict:
        return {"problems": check.invoke(state.question)}

    def review_node(state: IngestState) -> dict:
        try:
            verdict = review.invoke(
                {
                    "article": state.article,
                    "question": state.question,
                    # Empty unless `augment` borrowed pairs or `broaden` widened
                    # the material. Without these the reviewer cannot see the
                    # text such a pair came from and rejects every one of them.
                    "extras": state.extra_sources,
                }
            )
        except Exception as exc:  # noqa: BLE001 - must not discard a passing question
            verdict = skipped_review(describe_failure(exc))
        return {"review": verdict, "problems": [] if verdict.ok else verdict.problems}

    def broaden_node(state: IngestState) -> dict:
        """Read a couple of similar pages before the article is given up.

        Reached only when `extract` declined outright -- the article holds one
        thing, and a question needs several of them. The neighbours join the
        material and the article goes back through `extract` unchanged
        otherwise: nothing here writes a pair, and everything the second pass
        produces faces exactly the same gates as a first pass would.

        The decline is undone only when there is genuinely something new to
        read. A search that finds nothing leaves `stop` standing, and
        `after_broaden` takes the article out at END -- re-asking a model that
        just said no, with nothing added, is a slow way of getting the same
        answer.
        """
        rounds = state.broaden_rounds + 1
        try:
            found = broaden.invoke(
                {
                    "document": state.article,
                    # Never the same neighbour twice, and never one `augment`
                    # already borrowed from.
                    "skip": set(state.read_titles),
                }
            )
        except Exception as exc:  # noqa: BLE001 - a failed search costs the article, not the batch
            return {"broaden_rounds": rounds, "broaden_error": describe_failure(exc)}

        if not found.found:
            return {"broaden_rounds": rounds, "broaden_detail": found.detail}

        titles = [doc.title for doc in found.documents]
        return {
            "broaden_rounds": rounds,
            # The verdict was on the article alone, and that is no longer what
            # is being read. The declined draft goes with it: it is the model
            # saying "nothing here", not a question.
            "stop": False,
            "declined": False,
            "problems": [],
            "question": None,
            "extra_sources": [*state.extra_sources, *found.documents],
            "read_titles": [*state.read_titles, *titles],
            "broadened_titles": [*state.broadened_titles, *titles],
            "broaden_detail": found.detail,
        }

    def augment_node(state: IngestState) -> dict:
        """Look for the missing pairs in other articles. Never rejects.

        Reached only from `check`, and only when the pair count is the single
        thing wrong. Whatever happens the question goes back to `check`, so a
        search that finds nothing costs the article a couple of fetches and
        leaves it exactly as it was.
        """
        needed = MIN_PAIRS - len(state.question.pairs)
        rounds = state.augment_rounds + 1
        try:
            found = augment.invoke(
                {
                    "question": state.question,
                    "document": state.article,
                    "needed": needed,
                    # A second pass must look somewhere new, or a rejection just
                    # buys the same article's pairs back.
                    "skip": set(state.read_titles),
                }
            )
        except Exception as exc:  # noqa: BLE001 - a failed search must not lose the question
            return {"augment_rounds": rounds, "augment_error": describe_failure(exc)}

        if not found.found:
            return {"augment_rounds": rounds, "augment_detail": found.detail}

        titles = [doc.title for doc in found.documents]
        return {
            # Held rather than merged: `vet` rules on them first, and a pair
            # that never reaches the board cannot need removing from it.
            "candidates": list(found.pairs),
            "question": state.question if vet is not None else merge(state.question, found),
            "augment_rounds": rounds,
            "read_titles": [*state.read_titles, *titles],
            "extra_sources": [*state.extra_sources, *found.documents],
            "borrowed_titles": [*state.borrowed_titles, *titles],
            "augment_detail": found.detail,
        }

    def vet_node(state: IngestState) -> dict:
        """Rule on the borrowed pairs, one at a time. Keeps what belongs.

        A rejection is not fatal to the question -- `after_check` sends it back
        to `augment` to read somewhere it has not been, which is the whole point
        of separating finding from judging.
        """
        if not state.candidates:
            return {"vet_detail": "nothing to judge"}
        try:
            verdict = vet.invoke(
                {"question": state.question, "candidates": state.candidates}
            )
        except Exception as exc:  # noqa: BLE001
            # Nothing admitted: the step exists to be the thing that says no, and
            # a judge that could not answer has not said yes.
            return {"candidates": [], "vet_detail": f"none -- {describe_failure(exc)}"}

        return {
            "question": state.question.model_copy(
                update={"pairs": [*state.question.pairs, *verdict.kept]}
            ),
            "candidates": [],
            "vet_detail": verdict.detail,
        }

    def illustrate_node(state: IngestState) -> dict:
        """Decide whether this becomes a picture question. Never rejects.

        A lookup failure is treated exactly like "no pictures found": the
        question is already correct and already past both gates, so a Wikidata
        outage must cost it its illustrations and nothing else.

        The title is renamed for *every* picture question, not only flipped
        ones. The model wrote "Ordne jedem Land seine Hauptstadt zu" for a board
        of words; played with photographs the player is not reading a capital,
        they are looking at one, and the instruction has to say so. A flip
        additionally makes the old title describe the wrong direction. Failing
        to rename is not worth losing the pictures over -- a stale title is a
        blemish, a lost board is not.
        """
        try:
            decision = illustrate.invoke(
                {"question": state.question, "document": state.article}
            )
        except Exception as exc:  # noqa: BLE001 - decoration must not fail a question
            return {"images": {}, "illustrate_error": describe_failure(exc)}

        if not decision.is_picture:
            return {"images": {}, "illustrate_detail": decision.detail}

        question = state.question
        if decision.flipped:
            question = flip(question)
        question = keep_illustrated(question, decision)

        detail = ""
        if reframe is not None:
            try:
                renamed = reframe.invoke({"question": question})
                # `shown` and `asked` are the model's own statement of which side
                # is the photograph, written before the instruction that depends
                # on it. Kept for the trace and the report because this is the
                # one model output no gate downstream can check: it is prose a
                # player reads, not data a validator sees. A reply that skipped
                # them is one that renamed without establishing the direction, so
                # the question keeps the title it already had -- which is stale
                # for a flip, and honest either way.
                shown = (renamed.get("shown") or "").strip()
                asked = (renamed.get("asked") or "").strip()
                if shown and asked:
                    question = question.model_copy(
                        update={
                            "title": renamed["title"],
                            "description": renamed["description"],
                        }
                    )
                    detail = f"Bild = {shown}, gefragt = {asked}"
                else:
                    detail = "kept the old title -- reframe did not say which side is the picture"
            except Exception as exc:  # noqa: BLE001 - see above
                detail = f"kept the old title -- {describe_failure(exc)}"

        return {
            "question": question,
            "images": {label: image for label, image in decision.images.items()},
            "flipped": decision.flipped,
            "illustrate_detail": decision.detail,
            "reframe_detail": detail,
        }

    def explain_node(state: IngestState) -> dict:
        """One short line per answer. Never a gate.

        A question that reached here has already passed everything that decides
        whether it is correct, so a failure to explain it costs the explanations
        and nothing else.
        """
        try:
            lines = explain.invoke(
                {
                    "article": state.article,
                    "question": state.question,
                    # Same reason `review` gets them: the evidence for a pair
                    # taken from elsewhere is in the article it came from, not
                    # in this one.
                    "extras": state.extra_sources,
                }
            )
        except Exception as exc:  # noqa: BLE001 - decoration must not fail a question
            return {"explain_error": describe_failure(exc)}
        return {"question": state.question.model_copy(update={"explanations": lines})}

    def repair_node(state: IngestState) -> dict:
        return {
            "repairs": repair.invoke({"raw": state.raw, "problems": state.problems}),
            "attempt": state.attempt + 1,
        }

    def retry_or_stop(state: IngestState) -> str:
        return "repair" if state.attempt < state.max_attempts else END

    def first_node(state: IngestState) -> str:
        """`extract`, unless the caller supplied the question already.

        A pre-seeded question is a spare from `select`: written, not yet checked.
        It enters at the first gate, which is exactly what a freshly extracted
        one does.
        """
        return "extract" if state.question is None else "check"

    def worth_widening(state: IngestState) -> bool:
        """Whether a declined article gets a second reading with its neighbours.

        Only a *decline* qualifies, never a transport failure and never a
        malformed reply: those two say nothing about how much the article holds,
        and the second is what the repair loop is for.

        Ungated otherwise, unlike `augment` -- there is no question yet to be
        good or bad, so there is nothing to spend the search in proportion to.
        The bound is `MAX_BROADENINGS`, and it is what stops
        `extract -> broaden -> extract` from looping.
        """
        return broaden is not None and state.broaden_rounds < MAX_BROADENINGS

    def after_extract(state: IngestState) -> str:
        if state.declined and worth_widening(state):
            return "broaden"
        if state.stop:
            return END
        if state.problems:
            return retry_or_stop(state)
        return "select" if select is not None else "check"

    def after_broaden(state: IngestState) -> str:
        """Back to `extract` with more to read, or out with the original verdict.

        `stop` is the flag the node clears when it found something, so this reads
        as "was the decline overturned" rather than reaching back into what the
        search returned.
        """
        return END if state.stop else "extract"

    def after_select(state: IngestState) -> str:
        return END if state.stop else "check"

    def done(state: IngestState) -> str:
        """Where a question goes once nothing can reject it any more."""
        if illustrate is not None:
            return "illustrate"
        return "explain" if explain is not None else END

    def worth_topping_up(state: IngestState) -> bool:
        """Whether to go looking for the missing pairs elsewhere.

        Three conditions, and each rules out a way of wasting the search:

        * The pair count is the *only* complaint. Adding pairs cannot fix a
          duplicate answer or a bad slug, and a question with several problems
          is one the repair loop should be arguing with instead.
        * It has not been tried already, or `augment -> check -> augment` never
          terminates.
        * The question is worth the money. Searching costs a search, several
          fetches and a model call each; `easy` questions are left to fail,
          which is the one place the pipeline spends in proportion to how good
          the thing already is.
        """
        return (
            augment is not None
            and state.augment_rounds < (MAX_ROUNDS if vet is not None else 1)
            and state.question is not None
            and state.question.difficulty in AUGMENT_DIFFICULTIES
            and only_needs_more_pairs(state.question, state.problems)
        )

    def after_check(state: IngestState) -> str:
        if state.problems:
            return "augment" if worth_topping_up(state) else retry_or_stop(state)
        return "review" if review is not None else done(state)

    def after_review(state: IngestState) -> str:
        return done(state) if not state.problems else retry_or_stop(state)

    builder = StateGraph(IngestState)
    builder.add_node("extract", extract_node)
    builder.add_node("check", check_node)
    builder.add_node("repair", repair_node)

    builder.add_conditional_edges(START, first_node, ["extract", "check"])
    builder.add_edge("repair", "extract")

    # Straight back into `extract`, with the neighbours added to what it reads.
    # `broaden_rounds` is what stops the two looping.
    widens = []
    if broaden is not None:
        builder.add_node("broaden", broaden_node)
        builder.add_conditional_edges("broaden", after_broaden, ["extract", END])
        widens = ["broaden"]

    if select is not None:
        builder.add_node("select", select_node)
        builder.add_conditional_edges(
            "extract", after_extract, ["select", "repair", *widens, END]
        )
        builder.add_conditional_edges("select", after_select, ["check", END])
    else:
        builder.add_conditional_edges(
            "extract", after_extract, ["check", "repair", *widens, END]
        )

    exits = []
    if explain is not None:
        builder.add_node("explain", explain_node)
        builder.add_edge("explain", END)
    if illustrate is not None:
        builder.add_node("illustrate", illustrate_node)
        builder.add_edge("illustrate", "explain" if explain is not None else END)
        exits = ["illustrate"]
    elif explain is not None:
        exits = ["explain"]

    # Straight back into `check`: everything it adds is subject to exactly the
    # same structural rules, and `augment_rounds` is what stops the two looping.
    tops_up = []
    if augment is not None:
        builder.add_node("augment", augment_node)
        tops_up = ["augment"]
        if vet is not None:
            # Found, then judged, then re-checked. `after_check` is what sends a
            # question whose borrowings were rejected round for another search.
            builder.add_node("vet", vet_node)
            builder.add_edge("augment", "vet")
            builder.add_edge("vet", "check")
        else:
            builder.add_edge("augment", "check")

    if review is not None:
        builder.add_node("review", review_node)
        builder.add_conditional_edges(
            "check", after_check, ["review", "repair", *tops_up, *exits, END]
        )
        builder.add_conditional_edges("review", after_review, ["repair", *exits, END])
    else:
        builder.add_conditional_edges(
            "check", after_check, ["repair", *tops_up, *exits, END]
        )

    return builder.compile()


def run_all(
    graph,
    article: Article,
    subjects: list[tuple[str, str]],
    *,
    max_attempts: int = 3,
    on_step: Callable[[str, str], None] | None = None,
    executor: Executor | None = None,
) -> list[Outcome]:
    """Run one article, and then every question `select` kept beyond the first.

    One article can hold several questions worth playing, and `select` is what
    says which. The spares go back through the *same* compiled graph with the
    question pre-seeded, so they pass the same gates, get the same pictures and
    the same explanations -- rather than being written on the strength of having
    been chosen.

    A spare gets one attempt, not `max_attempts`. The repair edge leads back to
    `extract`, which would regenerate the whole batch and throw the spare away;
    a spare that fails a gate is simply dropped, and there is another article.

    **`executor` runs the spares concurrently.** They are genuinely independent
    -- each is a finished question entering at `check`, and no spare reads
    anything another writes -- so with several drafts kept, running them in turn
    leaves the card idle between one spare's review and the next one's. It must
    be a *different* pool from the one that runs articles: this call blocks until
    the spares finish, so a shared pool would let articles occupy every thread
    and wait on work that can never be scheduled.

    Sequential when `executor` is None, which is what the tests and any caller
    using `run_all` directly get.
    """
    first = run_article(
        graph, article, subjects, max_attempts=max_attempts, on_step=on_step
    )
    if not first.spares:
        return [first]

    def run_spare(spare: GeneratedQuestion, *, live: bool) -> Outcome:
        return run_article(
            graph,
            article,
            subjects,
            max_attempts=1,
            question=spare,
            # Silent when concurrent. `on_step` is a live feed into one buffer,
            # and several spares writing to it interleave mid-question into
            # something nobody can read. The lines are replayed below instead,
            # one spare at a time, from the `steps` every Outcome already carries.
            on_step=on_step if live else None,
        )

    if executor is None:
        return [first] + [run_spare(spare, live=True) for spare in first.spares]

    rest = list(executor.map(lambda spare: run_spare(spare, live=False), first.spares))
    if on_step:
        for outcome in rest:
            for line in outcome.steps:
                on_step(line.split(" ", 1)[0], line)
    return [first, *rest]


def run_article(
    graph,
    article: Article,
    subjects: list[tuple[str, str]],
    *,
    max_attempts: int = 3,
    question: GeneratedQuestion | None = None,
    on_step: Callable[[str, str], None] | None = None,
) -> Outcome:
    """Run one article and record what each node did.

    With `question` given, `extract` and `select` are skipped and that question
    enters at the first gate -- see `first_node` in `build_graph`.

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
        article=article, subjects=subjects, max_attempts=max_attempts, question=question
    )
    steps: list[str] = []

    config = {"recursion_limit": max_attempts * 6 + 10}

    pending: str | None = None

    started = time.monotonic()
    last = started

    for mode, chunk in graph.stream(state, config=config, stream_mode=["updates", "values"]):
        if mode == "updates":
            pending = next(iter(chunk), None)
            continue

        state = IngestState.model_validate(chunk)
        if pending is None:
            continue

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
        images=dict(state.images),
        flipped=state.flipped,
        borrowed_from=list(state.borrowed_titles),
        widened_from=list(state.broadened_titles),
        spares=list(state.spares),
        select_detail=state.select_detail,
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
        drafts = f"{len(state.drafts)} drafts, " if len(state.drafts) > 1 else ""
        return f"{drafts}{len(question.pairs)} pairs"

    if node == "select":
        return state.select_detail or "kept the first draft"

    if node == "check":
        return "ok" if not problems else f"{len(problems)} problem(s): {problems[0]}"

    if node == "review":
        if state.review is not None and state.review.skipped:
            return "skipped (reviewer unavailable)"
        return "ok" if not problems else f"{len(problems)} problem(s): {problems[0]}"

    if node == "illustrate":
        if state.illustrate_error:
            return f"none -- {state.illustrate_error}"
        if not state.images:
            return state.illustrate_detail or "stays a text question"
        kind = "flipped, " if state.flipped else ""
        named = f" ({state.reframe_detail})" if state.reframe_detail else ""
        return f"{kind}{len(state.images)} categories illustrated{named}"

    if node == "broaden":
        if state.broaden_error:
            return f"none -- {state.broaden_error}"
        return state.broaden_detail or "found nothing similar"

    if node == "augment":
        if state.augment_error:
            return f"none -- {state.augment_error}"
        return state.augment_detail or "found nothing to add"

    if node == "vet":
        return state.vet_detail or "nothing to judge"

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
