"""Tests for the reviewer's verdict handling.

The model call itself is a link in `review_step` and is covered in
`test_graph.py`. What is left here is the part with judgement in it: turning a
verdict into complaints the repair loop can act on.

With a one-to-one pairing there is only one content defect left -- an answer
beside a category it does not belong to, including the case where it belongs to
*two* categories on the board and the pairing is therefore not unique.
"""

from __future__ import annotations

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.pipeline.chains import as_review, skipped_review

QUESTION = GeneratedQuestion(
    usable=True,
    subject_slug="naturwissenschaft",
    slug="photosynthese",
    title="Photosynthese",
    difficulty="medium",
    pairs=[
        GeneratedPair(label="Farbstoffe", answer="Chlorophyll"),
        GeneratedPair(label="Anorganische Stoffe", answer="Wasser"),
        GeneratedPair(label="Produkte", answer="Sauerstoff"),
    ],
)


def verdict(**overrides) -> dict:
    base = {"ok": True, "problems": [], "misplaced_items": []}
    base.update(overrides)
    return base


def test_a_clean_question_passes():
    review = as_review(verdict())

    assert review.ok
    assert review.problems == []


def test_a_misplaced_answer_is_reported():
    review = as_review(
        verdict(
            ok=False,
            problems=["'Wasser' passt auch zu 'Reduktionsmittel'."],
            misplaced_items=["Wasser"],
        ),
        QUESTION,
    )

    assert not review.ok
    assert review.misplaced_items == ["Wasser"]
    assert "Wasser" in review.problems[0]


def test_findings_override_a_contradictory_ok_flag():
    """A model that lists faults but still says ok:true is contradicting itself."""
    review = as_review(verdict(ok=True, misplaced_items=["Wasser"]), QUESTION)

    assert not review.ok
    assert "Wasser" in review.problems[0]


def test_a_rejection_with_no_detail_still_yields_a_usable_complaint():
    review = as_review(verdict(ok=False))

    assert not review.ok
    assert review.problems


def test_junk_entries_are_dropped():
    review = as_review(verdict(ok=False, misplaced_items=["Wasser", "", "   "]), QUESTION)

    assert review.misplaced_items == ["Wasser"]



def test_a_finding_naming_something_not_on_the_board_is_discarded():
    """A small model sometimes reports a category name, or a term from the
    article that never became an answer. Neither is repairable."""
    review = as_review(
        verdict(
            ok=False,
            problems=["'Kohlenstoffdioxid' ist falsch zugeordnet"],
            misplaced_items=["Kohlenstoffdioxid"],
        ),
        QUESTION,
    )

    assert review.ok
    assert review.misplaced_items == []
    assert review.problems == []


def test_a_category_name_reported_as_misplaced_is_discarded():
    review = as_review(verdict(ok=False, misplaced_items=["Farbstoffe"]), QUESTION)

    assert review.ok
    assert review.misplaced_items == []


def test_a_mixed_verdict_keeps_only_the_finding_that_can_be_true():
    review = as_review(
        verdict(ok=False, misplaced_items=["Wasser", "Kohlenstoffdioxid"]), QUESTION
    )

    assert review.misplaced_items == ["Wasser"]
    assert not review.ok


def test_without_the_question_every_finding_is_taken_at_face_value():
    """The guard needs the question; with none to check against, the verdict
    stands as given rather than being silently trusted or dropped."""
    review = as_review(verdict(ok=False, misplaced_items=["Irgendwas"]))

    assert review.misplaced_items == ["Irgendwas"]
    assert not review.ok


def test_a_reviewer_that_could_not_run_does_not_discard_the_question():
    """A reviewer that errors must not throw away work that already passed the
    structural checks -- but the report has to say it went unchecked."""
    review = skipped_review("Cannot reach Ollama")

    assert review.ok
    assert review.skipped
    assert "Cannot reach Ollama" in review.problems[0]
