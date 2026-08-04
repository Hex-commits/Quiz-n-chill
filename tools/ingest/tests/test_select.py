"""Tests for drafting several questions per article and choosing between them.

The unit under test is the *routing plus the real chain*, as in `test_graph.py`:
only the model is faked, so the real `SELECT` template renders, the real grammar
is built and the real parser reads the reply. A test that stubbed `select_step`
would pass with a broken prompt.

What matters here is the shape of the decision, not the taste of it:

* a batch reaches `select` whole, with every board in the prompt;
* keeping several means several questions come out, each through its own gates;
* keeping none stops the article rather than repairing it;
* a judge that cannot answer must not cost the article the drafts it has.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from tools.ingest.domain.models import (
    GeneratedQuestion,
    questions_schema,
    selection_schema,
)
from tools.ingest.pipeline.chains import (
    check_step,
    extract_step,
    repair_step,
    review_step,
    select_step,
)
from tools.ingest.pipeline.graph import build_graph, run_all, run_article

from tools.ingest.tests.test_graph import (
    ARTICLE,
    SUBJECT_SLUGS,
    SUBJECTS,
    broken,
    fake_model,
    payload,
    verdict,
)


def batch(*questions: dict) -> dict:
    """The reply shape the extract grammar actually asks for."""
    return {"questions": list(questions)}


def choice(*keep: int, why: str = "beide fragen echtes Wissen ab") -> dict:
    return {"verdict": why, "keep": [str(index) for index in keep]}


def two_drafts() -> dict:
    return batch(
        payload(slug="fluesse", title="Flüsse und ihre Länge"),
        payload(slug="hauptstaedte", title="Länder und ihre Hauptstädte"),
    )


def build(
    extract_replies,
    select_replies,
    *,
    reviews=None,
    max_attempts=3,
    drafts=2,
    may_reject=True,
):
    generator = fake_model(extract_replies)
    chooser = fake_model(select_replies) if select_replies is not None else None
    reviewer = fake_model(reviews) if reviews is not None else None
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS), drafts=drafts),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        select=select_step(chooser, may_reject=may_reject) if chooser else None,
        review=review_step(reviewer) if reviewer else None,
        repair=repair_step(),
    )
    outcomes = run_all(graph, ARTICLE, SUBJECTS, max_attempts=max_attempts)
    return outcomes, generator, chooser


# -- the batch -----------------------------------------------------------


def test_one_call_returns_several_drafts():
    outcomes, generator, _ = build([two_drafts()], [choice(1)])

    assert len(generator.seen) == 1, "one extract call, not one per draft"
    assert outcomes[0].accepted, outcomes[0].problems
    assert outcomes[0].question.title == "Flüsse und ihre Länge"


def test_the_whole_board_of_every_draft_reaches_the_chooser():
    """Whether a question is trivial cannot be judged from its title -- the
    model's own summary of what it wrote is exactly what is not evidence."""
    _outcomes, _generator, chooser = build([two_drafts()], [choice(1, 2)])

    prompt = chooser.seen[0][-1].content
    assert "1. Flüsse und ihre Länge" in prompt
    assert "2. Länder und ihre Hauptstädte" in prompt
    assert "Kat0 -> Ant0" in prompt


def test_a_single_draft_is_not_sent_to_the_chooser():
    """There is nothing to choose between, and both gates are still ahead."""
    _outcomes, _generator, chooser = build([batch(payload())], [choice(1)])

    assert chooser.seen == []


# -- keeping more than one -----------------------------------------------


def test_keeping_two_drafts_yields_two_questions():
    outcomes, _generator, _ = build([two_drafts()], [choice(1, 2)])

    assert len(outcomes) == 2
    assert all(outcome.accepted for outcome in outcomes), [o.problems for o in outcomes]
    assert [outcome.question.slug for outcome in outcomes] == ["fluesse", "hauptstaedte"]


def test_a_kept_spare_goes_through_the_same_gates():
    """It is written on the strength of passing the gates, not of being chosen."""
    reviews = [verdict(), verdict()]
    outcomes, _generator, _ = build([two_drafts()], [choice(1, 2)], reviews=reviews)

    assert len(outcomes) == 2
    assert all(outcome.review is not None and outcome.review.ok for outcome in outcomes)
    # Each ran its own trace, and the spare skipped extract and select.
    assert [line.split()[0] for line in outcomes[1].steps] == ["check", "review"]


def test_a_spare_that_fails_a_gate_is_dropped_rather_than_repaired():
    """The repair edge leads back to `extract`, which would regenerate the batch
    and throw the spare away -- so a spare gets one attempt and no more."""
    drafts = batch(payload(slug="gut"), broken(slug="kaputt"))
    outcomes, generator, _ = build([drafts], [choice(1, 2)])

    assert len(generator.seen) == 1, "the spare must not re-extract"
    assert outcomes[0].accepted
    assert not outcomes[1].accepted
    assert any("appear more than once" in problem for problem in outcomes[1].problems)


def test_two_drafts_from_one_article_cannot_collide_on_a_slug():
    outcomes, _generator, _ = build(
        [batch(payload(slug="gleich"), payload(slug="gleich"))], [choice(1, 2)]
    )

    assert [outcome.question.slug for outcome in outcomes] == ["gleich", "gleich-2"]


# -- keeping none --------------------------------------------------------


def test_keeping_nothing_stops_the_article_without_repairing():
    """Well-formed and boring is a verdict on the article, like `usable: false`.
    Asking the same model again gets the same drafts.

    Only a judge trusted to say no gets to do this -- see below."""
    outcomes, generator, _ = build(
        [two_drafts()], [choice(why="beide sind Schulstoff")], max_attempts=3
    )

    assert len(outcomes) == 1
    assert not outcomes[0].accepted
    assert "none of 2 drafts kept" in outcomes[0].problems[0]
    assert "Schulstoff" in outcomes[0].problems[0]
    assert len(generator.seen) == 1, "a boring batch must not burn the attempts"


def test_an_untrusted_judge_may_sort_but_not_condemn():
    """Rejecting a batch is the most valuable thing this step does and the most
    damaging thing a bad judge does with it. Measured on glm4:9b: one run kept
    both drafts including a two-pair board with one answer used twice, the next
    kept none under a verdict saying some of them asked real questions. The
    second reading costs an article, so an unproven judge does not get it."""
    outcomes, _generator, _ = build(
        [two_drafts()], [choice(why="alles Schulstoff")], may_reject=False
    )

    assert len(outcomes) == 1
    assert outcomes[0].accepted, outcomes[0].problems
    assert outcomes[0].question.slug == "fluesse"
    assert "not trusted to" in outcomes[0].select_detail


def test_an_untrusted_judge_still_chooses_between_the_drafts():
    """It is advisory about rejection, not about ordering."""
    outcomes, _generator, _ = build([two_drafts()], [choice(2)], may_reject=False)

    assert [outcome.question.slug for outcome in outcomes] == ["hauptstaedte"]


def test_a_chooser_that_cannot_run_costs_the_choice_and_nothing_else():
    outcomes, _generator, _ = build([two_drafts()], [ConnectionError("refused")])

    assert len(outcomes) == 1
    assert outcomes[0].accepted, outcomes[0].problems
    assert outcomes[0].question.slug == "fluesse"
    assert "Cannot reach Ollama" in outcomes[0].select_detail


def test_a_draft_naming_a_number_that_is_not_in_the_batch_is_ignored():
    """The enum makes it unemittable; this is the reply where decoding did not
    hold."""
    outcomes, _generator, _ = build([two_drafts()], [{"verdict": "ok", "keep": ["1", "7"]}])

    assert len(outcomes) == 1
    assert outcomes[0].question.slug == "fluesse"


# -- declining -----------------------------------------------------------


def test_one_unusable_draft_does_not_condemn_the_others():
    """`usable: false` is the model declining one angle, and says nothing about
    the next."""
    drafts = batch(payload(usable=False, reason="nichts zu holen"), payload(slug="gut"))
    outcomes, _generator, chooser = build([drafts], [choice(1)])

    assert outcomes[0].accepted, outcomes[0].problems
    assert outcomes[0].question.slug == "gut"
    assert chooser.seen == [], "one usable draft is not a choice"


def test_a_batch_where_every_draft_declined_stops_immediately():
    outcomes, generator, _ = build(
        [batch(payload(usable=False, reason="keine Paare"))], [choice(1)], max_attempts=3
    )

    assert outcomes[0].problems == ["model declined: keine Paare"]
    assert len(generator.seen) == 1


# -- back compatibility ---------------------------------------------------


def test_a_bare_question_object_is_read_as_a_batch_of_one():
    """A model that answers with the question itself instead of the envelope has
    still given a usable answer."""
    outcomes, _generator, _ = build([payload(slug="nackt")], [choice(1)])

    assert outcomes[0].accepted, outcomes[0].problems
    assert outcomes[0].question.slug == "nackt"


def test_without_the_step_the_node_is_not_in_the_graph():
    stub = RunnableLambda(lambda _state: None)
    assert "select" not in build_graph(extract=stub, check=stub, repair=stub).get_graph().nodes


def test_a_preseeded_question_skips_extract_entirely():
    """The mechanism behind `run_all`: `first_node` sends a question that already
    exists to the first gate."""
    generator = fake_model([])
    graph = build_graph(
        extract=extract_step(generator, sorted(SUBJECT_SLUGS)),
        check=check_step(subject_slugs=SUBJECT_SLUGS),
        repair=repair_step(),
    )

    outcome = run_article(
        graph,
        ARTICLE,
        SUBJECTS,
        question=GeneratedQuestion.model_validate(payload(slug="fertig")),
    )

    assert outcome.accepted, outcome.problems
    assert generator.seen == []
    assert [line.split()[0] for line in outcome.steps] == ["check"]


# -- the grammars ---------------------------------------------------------


def test_the_batch_grammar_bounds_how_many_drafts_may_be_written():
    schema = questions_schema(["geografie"], 3)["properties"]["questions"]

    assert schema["maxItems"] == 3
    # One, not three: an article that supports a single question must be able to
    # say so rather than pad the batch.
    assert schema["minItems"] == 1


def test_the_batch_grammar_still_constrains_each_draft():
    draft = questions_schema(["geografie"], 2)["properties"]["questions"]["items"]

    assert set(draft["required"]) == set(draft["properties"])
    assert draft["properties"]["subject_slug"]["enum"] == ["geografie"]


def test_the_selection_grammar_names_only_drafts_that_exist():
    schema = selection_schema(2)

    assert schema["properties"]["keep"]["items"]["enum"] == ["1", "2"]
    # Empty is a legitimate answer, or the step could not reject a whole batch.
    assert schema["properties"]["keep"]["minItems"] == 0


def test_the_selection_grammar_asks_for_the_reasoning_first():
    """Ordered decoding: name what the drafts are worth before saying which to
    keep, or the field is a coin toss the sentence afterwards rationalises."""
    assert list(selection_schema(2)["properties"]) == ["verdict", "keep"]
