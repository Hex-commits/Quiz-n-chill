"""Tests for the pipeline's control flow.

Only the *model* is faked, never the chain. The real `ChatPromptTemplate`
renders, the real parser runs, the real `Extraction` and the real validator
decide -- so a broken prompt template or a mis-wired parser fails here. A test
that stubbed the whole step would pass with either of those broken.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from tools.ingest.pipeline.chains import (
    broaden_step,
    check_step,
    extract_step,
    repair_step,
    review_step,
)
from tools.ingest.pipeline.augment import Augmentation
from tools.ingest.pipeline.broaden import Broadening
from tools.ingest.pipeline.illustrate import Illustration
from tools.ingest.pipeline.vet import MAX_ROUNDS, Verdict
from tools.ingest.pipeline.graph import KEEP_REPAIRS, build_graph, run_article
from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.domain.rules import MIN_PAIRS
from tools.ingest.sources.protocols import Document
from tools.ingest.sources.wikipedia import Article

ARTICLE = Article(
    title="Testartikel",
    url="https://de.wikipedia.org/wiki/Test",
    summary="Zusammenfassung.",
    extract="Ein ausreichend langer Text." * 40,
)
SUBJECTS = [("geografie", "Geografie"), ("musik", "Musik")]
SUBJECT_SLUGS = {"geografie", "musik"}


def payload(**overrides) -> dict:
    base = {
        "usable": True,
        "reason": "",
        "subject_slug": "geografie",
        "slug": "test-frage",
        "title": "Testfrage",
        "description": "Ordne zu.",
        "difficulty": "medium",
        "pairs": [{"label": f"Kat{i}", "answer": f"Ant{i}"} for i in range(MIN_PAIRS)],
    }
    base.update(overrides)
    return base


def broken(**overrides) -> dict:
    """A payload the real validator rejects: one answer used twice."""
    bad = [{"label": f"Kat{i}", "answer": f"Ant{i}"} for i in range(MIN_PAIRS)]
    bad[1]["answer"] = bad[0]["answer"]
    return payload(pairs=bad, **overrides)


def verdict(**overrides) -> dict:
    base = {"ok": True, "problems": [], "misplaced_items": []}
    base.update(overrides)
    return base


class FakeChatModel(BaseChatModel):
    """Stands in for `ChatOllama`: replays queued replies, records its prompts.

    `with_structured_output` mirrors what the real one does -- constrain
    decoding to the schema, then parse the reply as JSON. Constrained decoding
    cannot be faked, so only the parser survives, which is the honest half: it
    means these tests never assume the model obeys the grammar.
    """

    replies: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    schemas: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        reply = self.replies.pop(0) if self.replies else {}
        if isinstance(reply, BaseException):
            raise reply
        message = AIMessage(json.dumps(reply, ensure_ascii=False))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def with_structured_output(self, schema, **kwargs):
        self.schemas.append(schema)
        return self | JsonOutputParser()


def fake_model(replies: list) -> FakeChatModel:
    """`replies` may hold dicts (JSON answers) or exceptions to raise."""
    return FakeChatModel(replies=list(replies))


def run(
    replies,
    *,
    reviews=None,
    taken_slugs=None,
    max_attempts=3,
    article=ARTICLE,
):
    generator = fake_model(replies)
    reviewer = fake_model(reviews) if reviews is not None else None
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS, taken_slugs=taken_slugs),
        review=review_step(reviewer) if reviewer else None,
        repair=repair_step(),
    )
    outcome = run_article(graph, article, SUBJECTS, max_attempts=max_attempts)
    return outcome, generator, reviewer



def test_a_good_first_answer_is_accepted_without_retrying():
    outcome, generator, _ = run([payload()])

    assert outcome.accepted, outcome.problems
    assert outcome.question.title == "Testfrage"
    assert len(generator.seen) == 1


def test_the_system_prompt_and_the_article_both_reach_the_model():
    _outcome, generator, _ = run([payload()])

    system, human = generator.seen[0]
    assert "Zuordnungsfragen" in system.content
    assert "Testartikel" in human.content


def test_the_prompt_lists_only_the_subjects_it_may_choose_from():
    _outcome, generator, _ = run([payload()])

    prompt = generator.seen[0][-1].content
    assert "geografie: Geografie" in prompt
    assert "musik: Musik" in prompt


def test_the_article_text_is_truncated_before_it_reaches_the_model():
    """A 9B model with an 8K context degrades badly on long inputs."""
    long_article = Article(
        title="Lang", url="https://example.test/lang", summary="s", extract="x" * 50_000
    )
    _outcome, generator, _ = run([payload()], article=long_article)

    assert len(generator.seen[0][-1].content) < 8000



def test_a_rejected_answer_is_retried_with_the_complaints_fed_back():
    """The first answer uses one answer twice, which the real validator catches."""
    outcome, generator, _ = run([broken(), payload(title="Zweiter Versuch")])

    assert outcome.accepted, outcome.problems
    assert outcome.question.title == "Zweiter Versuch"
    assert len(generator.seen) == 2

    conversation = generator.seen[1]
    assert conversation[-2].type == "ai"
    assert json.loads(conversation[-2].content)["title"] == "Testfrage"
    assert "appear more than once" in conversation[-1].content


def test_every_earlier_attempt_stays_in_the_conversation():
    """`add_messages` accumulates, so attempt three still sees attempts one and
    two -- otherwise the model reintroduces a fault it already fixed."""
    _outcome, generator, _ = run([broken(), broken(), payload()], max_attempts=3)

    assert len(generator.seen) == 3
    assert len(generator.seen[2]) == 6


def test_it_gives_up_after_max_attempts_and_reports_why():
    """One answer offered under two categories: the player who picks the second
    is marked wrong for being right."""
    outcome, generator, _ = run([broken(), broken(), broken()], max_attempts=3)

    assert not outcome.accepted
    assert any("appear more than once" in p for p in outcome.problems)
    assert len(generator.seen) == 3


def test_max_attempts_is_respected():
    _outcome, generator, _ = run([broken(), broken()], max_attempts=2)

    assert len(generator.seen) == 2



def test_the_model_declining_stops_immediately():
    """A refusal is a verdict, not a defect -- do not burn attempts on it."""
    outcome, generator, _ = run(
        [payload(usable=False, reason="Artikel enthält keine Paare."), payload()],
        max_attempts=3,
    )

    assert not outcome.question.usable
    assert outcome.problems == ["model declined: Artikel enthält keine Paare."]
    assert len(generator.seen) == 1


def test_a_transport_failure_is_reported_not_raised():
    outcome, _generator, _ = run([ConnectionError("connection refused")])

    assert not outcome.question.usable
    assert "Cannot reach Ollama" in outcome.problems[0]


def test_a_transport_failure_does_not_burn_the_remaining_attempts():
    """Ollama being down is not something a repair prompt can fix."""
    outcome, generator, _ = run(
        [ConnectionError("connection refused"), payload()], max_attempts=3
    )

    assert len(generator.seen) == 1
    assert outcome.problems



def test_a_taken_slug_is_moved_aside_rather_than_rejected():
    outcome, _generator, _ = run([payload(slug="test-frage")], taken_slugs={"test-frage"})

    assert outcome.accepted, outcome.problems
    assert outcome.question.slug == "test-frage-2"


def test_the_slug_is_normalised_before_it_is_judged():
    """German umlauts spelled out, not stripped: Flüsse -> fluesse."""
    outcome, _generator, _ = run([payload(slug="Flüsse Europas")])

    assert outcome.accepted, outcome.problems
    assert outcome.question.slug == "fluesse-europas"



def test_the_reviewer_only_sees_questions_that_passed_the_structural_gate():
    """Reviewing a malformed question spends a model call to learn nothing."""
    outcome, generator, reviewer = run(
        [broken(), payload()], reviews=[verdict()]
    )

    assert outcome.accepted, outcome.problems
    assert len(generator.seen) == 2
    assert len(reviewer.seen) == 1


def test_a_review_finding_goes_back_through_the_same_repair_edge():
    outcome, generator, _ = run(
        [payload(), payload(title="Repariert")],
        reviews=[
            verdict(ok=False, problems=["'F1' ist keine echte Antwort"], weak_fakes=["F1"]),
            verdict(),
        ],
    )

    assert outcome.accepted, outcome.problems
    assert outcome.question.title == "Repariert"
    assert "F1" in generator.seen[1][-1].content
    assert outcome.review is not None and outcome.review.ok


def test_a_reviewer_that_cannot_run_does_not_discard_the_question():
    """The structural gate already passed; a dead reviewer must not undo that."""
    outcome, _generator, _ = run([payload()], reviews=[ConnectionError("connection refused")])

    assert outcome.accepted
    assert outcome.review is not None and outcome.review.skipped


def test_the_reviewer_sees_the_article_and_the_question_but_not_the_transcript():
    """Fresh context is the point -- a model re-reading its own reasoning mostly
    agrees with itself."""
    _outcome, _generator, reviewer = run([payload()], reviews=[verdict()])

    system, human = reviewer.seen[0]
    assert len(reviewer.seen[0]) == 2
    assert "Testfrage" in human.content
    assert "Kat0 -> Ant0" in human.content
    assert "Zuordnungsfrage" in system.content
    assert "Verfügbare Themengebiete" not in human.content


def test_without_a_reviewer_the_review_node_is_not_in_the_graph():
    """`--no-review` should be the smaller graph, not the same graph routed
    around it."""
    stub = RunnableLambda(lambda _x: None)
    without = build_graph(extract=stub, check=stub, repair=stub)
    with_review = build_graph(extract=stub, check=stub, review=stub, repair=stub)

    assert "review" not in without.get_graph().nodes
    assert "review" in with_review.get_graph().nodes



def test_the_trace_records_every_node_that_ran():
    outcome, _generator, _ = run([payload()], reviews=[verdict()])

    assert [line.split()[0] for line in outcome.steps] == ["extract", "check", "review"]


def test_the_trace_names_the_gate_that_objected_and_what_it_said():
    """A dropped article is the case the trace exists for."""
    outcome, _generator, _ = run([broken(), broken()], max_attempts=2)

    trace = "\n".join(outcome.steps)
    assert "1 problem(s): these answers appear more than once" in trace
    assert "retrying, attempt 2" in trace
    assert outcome.attempts == 2
    assert all("s  " in line for line in outcome.steps)


def test_the_trace_summarises_what_was_extracted():
    outcome, _generator, _ = run([payload()])

    assert f"{MIN_PAIRS} pairs" in outcome.steps[0]


def test_on_step_reports_live():
    lines: list[tuple[str, str]] = []
    graph = build_graph(
        extract=extract_step(fake_model([payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        repair=repair_step(),
    )

    run_article(graph, ARTICLE, SUBJECTS, on_step=lambda node, line: lines.append((node, line)))

    assert [node for node, _ in lines] == ["extract", "check"]



def explainer(lines: dict[str, str]):
    """A stand-in for the explain step, which returns a plain dict."""
    return RunnableLambda(lambda _state: dict(lines))


def test_explanations_are_attached_to_an_accepted_question():
    generator = fake_model([payload()])
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        explain=explainer({"Ant0": "Weil A."}),
        repair=repair_step(),
    )

    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert outcome.accepted
    assert outcome.question.explanations == {"Ant0": "Weil A."}


def test_a_rejected_question_still_ends_cleanly_with_explain_enabled():
    """The `KeyError: '__end__'` regression: a clean question routes to
    `explain`, but a rejected one with no attempts left leaves the same branch
    for END, so END has to stay a declared target."""
    generator = fake_model([broken(), broken()])
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        explain=explainer({"Ant0": "unused"}),
        repair=repair_step(),
    )

    outcome = run_article(graph, ARTICLE, SUBJECTS, max_attempts=2)

    assert not outcome.accepted
    assert outcome.question.explanations == {}


def test_the_same_holds_when_the_reviewer_is_the_one_rejecting():
    broken_review = verdict(ok=False, bad_fakes=["F1"])
    graph = build_graph(
        extract=extract_step(fake_model([payload(), payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        review=review_step(fake_model([broken_review, broken_review])),
        explain=explainer({"Ant0": "unused"}),
        repair=repair_step(),
    )

    outcome = run_article(graph, ARTICLE, SUBJECTS, max_attempts=2)

    assert not outcome.accepted


def test_a_failing_explainer_never_costs_the_question():
    """It is decoration, not a gate."""
    def boom(_state):
        raise RuntimeError("no")

    graph = build_graph(
        extract=extract_step(fake_model([payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        explain=RunnableLambda(boom),
        repair=repair_step(),
    )

    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert outcome.accepted
    assert outcome.question.explanations == {}


def test_a_failing_explainer_says_why_in_the_trace():
    """It must not cost the question -- but it must not vanish either. A silent
    catch here hid a real bug: the step referenced a field the model no longer
    had, and every run quietly produced no explanations at all."""
    def boom(_state):
        raise RuntimeError("no such field")

    graph = build_graph(
        extract=extract_step(fake_model([payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        explain=RunnableLambda(boom),
        repair=repair_step(),
    )
    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert outcome.accepted
    assert any("no such field" in line for line in outcome.steps)

# -- reading the neighbours of an article that holds too little ----------
#
# The routing, not the searching -- `test_broaden.py` covers what comes back.
# What matters here is which declines get a second reading, that the neighbours
# actually reach the model, and that a search which finds nothing cannot put the
# graph in a loop.


class StubBroaden:
    """Stands in for `broaden_step`, recording what it was asked to skip."""

    def __init__(self, *documents: Document):
        self.documents = documents
        self.skips: list[set] = []

    def invoke(self, state, *args, **kwargs):
        self.skips.append(set(state.get("skip") or set()))
        return Broadening(
            documents=self.documents,
            detail=f"read {', '.join(d.title for d in self.documents)}"
            if self.documents
            else "no similar articles found",
        )


NEIGHBOUR = Document(
    id="2",
    title="Nachbarort",
    url="https://example.test/nachbarort",
    # Long enough to be worth reading: `broaden` drops stubs, and the real step
    # runs in `test_the_real_chain_reaches_the_searcher_and_the_prompt` below.
    text="Der Nachbarort hat 4000 Einwohner. " + "Weiterer Fließtext. " * 20,
)


def run_with_broaden(replies, broadener, *, max_attempts=3):
    generator = fake_model(replies)
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        broaden=broadener,
        repair=repair_step(),
    )
    outcome = run_article(graph, ARTICLE, SUBJECTS, max_attempts=max_attempts)
    return outcome, generator


def declined(reason: str = "Der Artikel handelt nur von einem Ding.") -> dict:
    return payload(usable=False, reason=reason)


def test_a_declined_article_is_read_again_with_similar_pages():
    """The behaviour the step exists for: a decline is a verdict on one article,
    and the class it belongs to has an article per member."""
    broadener = StubBroaden(NEIGHBOUR)

    outcome, generator = run_with_broaden([declined(), payload()], broadener)

    assert outcome.accepted, outcome.problems
    assert len(generator.seen) == 2
    assert outcome.widened_from == ["Nachbarort"]


def test_the_neighbours_actually_reach_the_model():
    """Without the text in the prompt the second call is the first call again,
    and the model declines a second time for the same reason."""
    outcome, generator = run_with_broaden([declined(), payload()], StubBroaden(NEIGHBOUR))

    second = generator.seen[1][-1].content
    assert "Der Nachbarort hat 4000 Einwohner." in second
    assert "Nachbarort" in second
    assert outcome.accepted


def test_the_first_pass_is_not_told_about_articles_it_does_not_have():
    """A permanent paragraph about further texts is one that invites the model to
    imagine them."""
    _outcome, generator = run_with_broaden([payload()], StubBroaden(NEIGHBOUR))

    assert "Weiterer Artikel" not in generator.seen[0][-1].content


def test_an_article_is_only_widened_once():
    """Declining a second time, with the neighbours in front of it, is an answer
    about the class rather than about the article."""
    broadener = StubBroaden(NEIGHBOUR)

    outcome, generator = run_with_broaden([declined(), declined()], broadener)

    assert len(broadener.skips) == 1
    assert len(generator.seen) == 2
    assert not outcome.accepted


def test_a_page_already_read_is_not_offered_again():
    broadener = StubBroaden(NEIGHBOUR)

    run_with_broaden([declined(), payload()], broadener)

    assert broadener.skips == [set()]


def test_finding_nothing_similar_drops_the_article_where_it_stood():
    """Re-asking a model that just said no, with nothing added, is a slow way of
    getting the same answer."""
    broadener = StubBroaden()

    outcome, generator = run_with_broaden([declined(), payload()], broadener)

    assert len(generator.seen) == 1
    assert not outcome.accepted
    assert outcome.problems == ["model declined: Der Artikel handelt nur von einem Ding."]


def test_a_failing_search_costs_the_article_and_nothing_else():
    class Broken:
        def invoke(self, state, *args, **kwargs):
            raise RuntimeError("search is down")

    outcome, generator = run_with_broaden([declined(), payload()], Broken())

    assert len(generator.seen) == 1
    assert not outcome.accepted
    assert any("search is down" in line for line in outcome.steps)


def test_a_transport_failure_is_not_something_more_reading_can_fix():
    """Ollama being down says nothing about how much the article holds."""
    broadener = StubBroaden(NEIGHBOUR)

    outcome, _generator = run_with_broaden(
        [ConnectionError("connection refused"), payload()], broadener
    )

    assert broadener.skips == []
    assert not outcome.accepted


def test_a_malformed_reply_goes_to_repair_rather_than_to_the_search():
    """A duplicated answer is a defect in the reply, not a shortage of material."""
    broadener = StubBroaden(NEIGHBOUR)

    outcome, generator = run_with_broaden([broken(), payload()], broadener)

    assert broadener.skips == []
    assert len(generator.seen) == 2
    assert outcome.accepted, outcome.problems


def test_the_widening_is_named_in_the_trace():
    outcome, _generator = run_with_broaden([declined(), payload()], StubBroaden(NEIGHBOUR))

    assert [line.split()[0] for line in outcome.steps] == [
        "extract",
        "broaden",
        "extract",
        "check",
    ]
    assert any("read Nachbarort" in line for line in outcome.steps)


def test_without_the_step_a_decline_is_still_the_end_of_the_article():
    stub = RunnableLambda(lambda _x: None)
    assert "broaden" not in build_graph(extract=stub, check=stub, repair=stub).get_graph().nodes


def test_the_real_chain_reaches_the_searcher_and_the_prompt():
    """The stub above proves the routing; this proves the wiring. Only the model
    and the network are faked -- the real `broaden_step` runs, so a step that
    asked the finder for the wrong thing or dropped the documents on the way to
    the prompt fails here."""

    class StubFinder:
        def __init__(self):
            self.queries: list[str] = []

        def related(self, document, *, query: str, limit: int):
            self.queries.append(query)
            return [NEIGHBOUR]

    finder = StubFinder()
    generator = fake_model([declined(), payload()])
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        broaden=broaden_step(finder),
        repair=repair_step(),
    )

    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert finder.queries == ["Testartikel"]
    assert "Der Nachbarort hat 4000 Einwohner." in generator.seen[1][-1].content
    assert outcome.accepted, outcome.problems
    assert outcome.widened_from == ["Nachbarort"]


# -- topping up a short question from other articles ---------------------
#
# The routing, not the searching -- `test_augment.py` covers what may be added.
# What matters here is which questions get sent looking, and that a search which
# finds nothing cannot put the graph in a loop.


class StubAugment:
    """Stands in for `augment_step`, recording what it was asked for."""

    def __init__(self, *pairs: tuple[str, str], documents=()):
        self.pairs = pairs
        self.documents = documents
        self.calls: list[int] = []

    def invoke(self, state, *args, **kwargs):
        self.calls.append(state["needed"])
        return Augmentation(
            pairs=tuple(
                GeneratedPair(label=label, answer=answer) for label, answer in self.pairs
            ),
            documents=tuple(self.documents),
            detail=f"{len(self.pairs)} pair(s) from elsewhere",
        )


def short(n: int, **overrides) -> dict:
    """A payload with `n` pairs -- fewer than the validator will accept."""
    return payload(
        pairs=[{"label": f"Kat{i}", "answer": f"Ant{i}"} for i in range(n)],
        **overrides,
    )


def run_with_augment(replies, augmenter, *, reviews=None, max_attempts=3):
    generator = fake_model(replies)
    reviewer = fake_model(reviews) if reviews is not None else None
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        review=review_step(reviewer) if reviewer else None,
        augment=augmenter,
        repair=repair_step(),
    )
    return run_article(graph, ARTICLE, SUBJECTS, max_attempts=max_attempts)


def test_a_short_medium_question_is_topped_up_and_accepted():
    missing = MIN_PAIRS - 8
    augmenter = StubAugment(*[(f"Extra{i}", f"Antwort{i}") for i in range(missing)])

    outcome = run_with_augment([short(8)], augmenter)

    assert augmenter.calls == [missing]
    assert outcome.accepted, outcome.problems
    assert len(outcome.question.pairs) == MIN_PAIRS


def test_an_easy_question_is_left_to_fail():
    """The step costs a search, several fetches and a model call each. That is
    worth paying for a question someone will find interesting."""
    augmenter = StubAugment(("Extra", "Antwort"))

    outcome = run_with_augment([short(8, difficulty="easy")] * 3, augmenter)

    assert augmenter.calls == []
    assert not outcome.accepted


def test_a_hard_question_is_topped_up_too():
    missing = MIN_PAIRS - 9
    augmenter = StubAugment(*[(f"Extra{i}", f"Antwort{i}") for i in range(missing)])

    outcome = run_with_augment([short(9, difficulty="hard")], augmenter)

    assert augmenter.calls == [missing]
    assert outcome.accepted, outcome.problems


def test_a_question_with_a_second_problem_is_not_sent_looking():
    """Adding pairs cannot fix a duplicated answer, so this one belongs in the
    repair loop instead."""
    duplicated = short(8)
    duplicated["pairs"][1]["answer"] = duplicated["pairs"][0]["answer"]
    augmenter = StubAugment(("Extra", "Antwort"))

    run_with_augment([duplicated] * 3, augmenter)

    assert augmenter.calls == []


def test_finding_nothing_does_not_loop():
    """`augment` routes back into `check`, so without the one-shot guard a
    question it cannot fix would bounce between them for ever."""
    augmenter = StubAugment()  # finds nothing

    outcome = run_with_augment([short(8)] * 3, augmenter)

    assert augmenter.calls == [MIN_PAIRS - 8]
    assert not outcome.accepted


def test_a_failing_search_costs_the_pairs_and_nothing_else():
    class Broken:
        def invoke(self, state, *args, **kwargs):
            raise RuntimeError("search is down")

    outcome = run_with_augment([short(8)] * 3, Broken())

    assert not outcome.accepted
    assert "augment" in " ".join(outcome.steps)


def test_the_reviewer_is_shown_the_articles_the_pairs_came_from():
    """Without them it judges every added pair against an article that never
    mentions it, and rejects the question this step exists to save."""
    borrowed = Document(
        id="2", title="Nachbarartikel", url="https://example.test/n", text="Belegtext hier."
    )
    missing = MIN_PAIRS - 8
    augmenter = StubAugment(
        *[(f"Extra{i}", f"Antwort{i}") for i in range(missing)], documents=[borrowed]
    )
    reviewer = fake_model([{"ok": True, "problems": [], "misplaced_items": []}])

    graph = build_graph(
        extract=extract_step(fake_model([short(8)]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        review=review_step(reviewer),
        augment=augmenter,
        repair=repair_step(),
    )
    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert outcome.accepted, outcome.problems
    sent = "".join(m.content for m in reviewer.seen[0])
    assert "Belegtext hier." in sent
    assert "Nachbarartikel" in sent
    assert outcome.borrowed_from == ["Nachbarartikel"]


def test_without_the_step_the_node_is_not_in_the_graph():
    stub = RunnableLambda(lambda state: [])
    assert "augment" not in build_graph(extract=stub, check=stub, repair=stub).get_graph().nodes


# -- rejecting a borrowed pair and going back for a better one ------------


class StubVet:
    """Rules on candidates by label, and records what it was shown."""

    def __init__(self, *accept: str):
        self.accept = accept
        self.seen: list[list[str]] = []

    def invoke(self, state, *args, **kwargs):
        candidates = list(state["candidates"])
        self.seen.append([c.label for c in candidates])
        kept = tuple(c for c in candidates if c.label in self.accept)
        rejected = tuple(c for c in candidates if c.label not in self.accept)
        return Verdict(kept, rejected, tuple((c.label, "different question") for c in rejected))


class RoundedAugment:
    """Yields a different batch of pairs on each pass, like a fresh search."""

    def __init__(self, *rounds: list[tuple[str, str]]):
        self.rounds = list(rounds)
        self.skips: list[set] = []

    def invoke(self, state, *args, **kwargs):
        self.skips.append(set(state.get("skip") or set()))
        batch = self.rounds.pop(0) if self.rounds else []
        n = len(self.skips)
        return Augmentation(
            pairs=tuple(GeneratedPair(label=a, answer=b) for a, b in batch),
            documents=(Document(id=str(n), title=f"Quelle {n}", url="u", text="t"),),
            detail=f"{len(batch)} from Quelle {n}",
        )


def run_vetted(replies, augmenter, vetter, *, max_attempts=3):
    graph = build_graph(
        extract=extract_step(fake_model(replies), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        augment=augmenter,
        vet=vetter,
        repair=repair_step(),
    )
    return run_article(graph, ARTICLE, SUBJECTS, max_attempts=max_attempts)


def test_a_rejected_pair_sends_the_question_back_for_a_new_search():
    """The behaviour the whole step exists for: a bad borrowing costs a search,
    not the question."""
    missing = MIN_PAIRS - 9
    augmenter = RoundedAugment([("Schlecht", "falsch")], [("Gut", "1 km")] * missing)
    vetter = StubVet("Gut")

    outcome = run_vetted([short(9)], augmenter, vetter)

    assert len(augmenter.skips) == 2, "should have searched twice"
    assert augmenter.skips[1] == {"Quelle 1"}, "second search must read somewhere new"
    assert vetter.seen == [["Schlecht"], ["Gut"]]
    assert outcome.accepted, outcome.problems


def test_only_the_vetted_pairs_reach_the_board():
    augmenter = RoundedAugment([("Gut", "1 km"), ("Schlecht", "falsch")])
    vetter = StubVet("Gut")

    outcome = run_vetted([short(MIN_PAIRS - 1)], augmenter, vetter)

    assert outcome.accepted, outcome.problems
    assert "Gut" in outcome.question.labels
    assert "Schlecht" not in outcome.question.labels


def test_the_search_gives_up_after_two_rounds():
    augmenter = RoundedAugment([("A", "x")], [("B", "y")], [("C", "z")])
    vetter = StubVet()  # rejects everything

    outcome = run_vetted([short(9)] * 3, augmenter, vetter)

    assert len(augmenter.skips) == MAX_ROUNDS
    assert not outcome.accepted


def test_without_vet_there_is_only_one_search():
    """Nothing rejects, so a second pass would only re-ask the same question."""
    augmenter = RoundedAugment([("A", "x")], [("B", "y")])

    run_vetted([short(9)] * 3, augmenter, None)

    assert len(augmenter.skips) == 1


# -- naming a picture question -------------------------------------------
#
# `reframe` is the one model output nothing downstream can check: it is prose a
# player reads, not data a validator sees, and it runs after both gates. So the
# model states which side is the photograph *before* it writes the instruction
# that depends on that, and a reply that skipped it does not get to rename the
# question.


class StubIllustrate:
    """Stands in for `illustrate_step`: pictures on the categories, no flip."""

    def __init__(self, flipped=False):
        self.flipped = flipped

    def invoke(self, state, *args, **kwargs):
        question = state["question"]
        labels = question.answers if self.flipped else question.labels
        return Illustration(
            images={label: object() for label in labels},
            flipped=self.flipped,
            detail="alle illustriert",
        )


def run_illustrated(reframe_reply, *, flipped=False):
    graph = build_graph(
        extract=extract_step(fake_model([payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        illustrate=StubIllustrate(flipped=flipped),
        reframe=RunnableLambda(lambda _state: reframe_reply),
        repair=repair_step(),
    )
    return run_article(graph, ARTICLE, SUBJECTS)


def named(**overrides) -> dict:
    base = {
        "shown": "eine Kategorie",
        "asked": "die Antwort",
        "title": "Bilderfrage",
        "description": "Was gehört zu diesem Bild?",
    }
    base.update(overrides)
    return base


def test_a_picture_question_is_renamed_for_the_board_it_became():
    outcome = run_illustrated(named())

    assert outcome.accepted, outcome.problems
    assert outcome.question.title == "Bilderfrage"
    assert outcome.question.description == "Was gehört zu diesem Bild?"


def test_the_direction_it_wrote_for_is_recorded_in_the_trace():
    """The only trace of a judgement no gate makes."""
    outcome = run_illustrated(named(shown="ein Fluss", asked="die Länge"))

    assert any("Bild = ein Fluss, gefragt = die Länge" in line for line in outcome.steps)


def test_a_rename_that_never_said_which_side_is_the_picture_is_not_used():
    """Without the direction stated first, the instruction is a coin toss -- and
    a stale title is a blemish where a backwards instruction is a broken game."""
    outcome = run_illustrated(named(shown="", asked=""))

    assert outcome.accepted, outcome.problems
    assert outcome.question.title == "Testfrage"
    assert any("did not say which side" in line for line in outcome.steps)


def test_a_failing_rename_costs_the_title_and_not_the_pictures():
    def boom(_state):
        raise RuntimeError("no")

    graph = build_graph(
        extract=extract_step(fake_model([payload()]), sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        illustrate=StubIllustrate(),
        reframe=RunnableLambda(boom),
        repair=repair_step(),
    )
    outcome = run_article(graph, ARTICLE, SUBJECTS)

    assert outcome.accepted
    assert outcome.is_picture
    assert outcome.question.title == "Testfrage"


# -- the repair transcript is bounded ------------------------------------


def test_the_transcript_keeps_whole_attempts_and_only_the_recent_ones():
    """It is the one part of the extract prompt that grows: a rejected answer
    plus its complaints, on top of a system prompt and 6000 characters of
    article. Unbounded, `--attempts 10` runs the call out of context and the
    truncated reply is reported as the model's fault."""
    _outcome, generator, _ = run([broken()] * 6, max_attempts=6)

    assert len(generator.seen) == 6
    # system + human + KEEP_REPAIRS whole (ai, human) attempts, and no more.
    assert len(generator.seen[-1]) == 2 + 2 * KEEP_REPAIRS
    # Whole attempts only: never a complaint about an answer that has been
    # dropped from the conversation.
    assert [m.type for m in generator.seen[-1][2:]] == ["ai", "human"] * KEEP_REPAIRS
