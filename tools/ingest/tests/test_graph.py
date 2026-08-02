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

from tools.ingest.pipeline.chains import check_step, extract_step, repair_step, review_step
from tools.ingest.pipeline.graph import build_graph, run_article
from tools.ingest.domain.models import GeneratedQuestion
from tools.ingest.domain.rules import MIN_PAIRS
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
