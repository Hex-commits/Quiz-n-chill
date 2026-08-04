"""Rejecting borrowed pairs, and going back for better ones.

The judge is a stub here. What is under test is what happens around a verdict --
which pairs survive, what a broken judge does, and whether a rejection actually
sends the question somewhere new rather than back to the same article.
"""

from __future__ import annotations

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.pipeline.augment import augment
from tools.ingest.pipeline.vet import MAX_ROUNDS, Verdict, vet
from tools.ingest.sources.protocols import Document

BOARD = GeneratedQuestion(
    usable=True,
    subject_slug="geografie",
    slug="fluesse",
    title="Flüsse und ihre Länge",
    description="Ordne zu.",
    difficulty="medium",
    pairs=[
        GeneratedPair(label="Rhein", answer="1233 km"),
        GeneratedPair(label="Elbe", answer="1094 km"),
        GeneratedPair(label="Donau", answer="2857 km"),
    ],
)

GOOD = GeneratedPair(label="Inn", answer="517 km")
BAD = GeneratedPair(label="Donau-Main-Wasserscheide", answer="Süddeutschland")


def judge_by_label(*accept: str):
    """A judge that accepts exactly the labels it was given."""

    def judge(question, candidate):
        return candidate.label in accept, "asks a different question"

    return judge


# -- the verdict -------------------------------------------------------------


def test_a_pair_that_fits_is_kept():
    verdict = vet(BOARD, [GOOD], judge_by_label("Inn"))

    assert verdict.kept == (GOOD,)
    assert not verdict.rejected_any


def test_a_pair_that_does_not_fit_is_rejected_with_a_reason():
    verdict = vet(BOARD, [GOOD, BAD], judge_by_label("Inn"))

    assert verdict.kept == (GOOD,)
    assert verdict.rejected == (BAD,)
    assert verdict.reasons[0][0].startswith("Donau-Main-Wasserscheide")


def test_a_broken_judge_admits_nothing():
    """The step exists to be the thing that says no. A judge that could not
    answer has not said yes, and passing everything through on error would make
    a broken judge indistinguishable from an approving one."""

    def explode(question, candidate):
        raise RuntimeError("model is down")

    verdict = vet(BOARD, [GOOD, BAD], explode)

    assert verdict.kept == ()
    assert len(verdict.rejected) == 2
    assert "unavailable" in verdict.reasons[0][1]


def test_candidates_are_judged_against_the_board_not_each_other():
    """One that slipped through must not become the precedent that admits the
    next, so every call sees the original question."""
    seen = []

    def judge(question, candidate):
        seen.append(len(question.pairs))
        return True, ""

    vet(BOARD, [GOOD, BAD], judge)

    assert seen == [3, 3]


def test_nothing_to_judge_is_not_a_failure():
    assert vet(BOARD, [], judge_by_label()).kept == ()


# -- going back for better ones ----------------------------------------------


def doc(title: str) -> Document:
    return Document(id=title, title=title, url=f"https://example.test/{title}", text="…")


class Finder:
    def __init__(self, *documents: Document):
        self.documents = list(documents)

    def related(self, document, *, query, limit):
        return self.documents[:limit]


def test_a_second_pass_reads_somewhere_new():
    """The point of a rejection. Without `skip` the next search re-reads the
    article whose pairs were just thrown out and buys them straight back."""
    finder = Finder(doc("Erste Liste"), doc("Zweite Liste"))
    asked: list[str] = []

    def find_pairs(document, needed):
        asked.append(document.title)
        return [GeneratedPair(label=f"X{needed}", answer=f"{needed} km")]

    augment(BOARD, doc("Rhein"), finder, find_pairs, needed=1, skip={"Erste Liste"})

    assert asked == ["Zweite Liste"]


def test_running_out_of_unread_articles_says_so():
    finder = Finder(doc("Erste Liste"))

    result = augment(
        BOARD, doc("Rhein"), finder, lambda d, n: [], needed=1, skip={"Erste Liste"}
    )

    assert not result.found
    assert "unread" in result.detail


def test_skipping_is_case_insensitive():
    finder = Finder(doc("Erste Liste"))

    result = augment(
        BOARD, doc("Rhein"), finder, lambda d, n: [], needed=1, skip={"erste liste"}
    )

    assert "unread" in result.detail


def test_more_articles_are_requested_to_cover_the_skipped_ones():
    """The skipped ones would otherwise eat the budget and the second pass would
    come back empty on a source that had plenty left."""
    limits: list[int] = []

    class Recording(Finder):
        def related(self, document, *, query, limit):
            limits.append(limit)
            return []

    augment(BOARD, doc("Rhein"), Recording(), lambda d, n: [], needed=1,
            max_documents=4, skip={"a", "b"})

    assert limits == [6]


def test_two_rounds_is_the_ceiling():
    """A third pass is reading the fourth-best article for the same shortfall,
    which is not saving a question so much as forcing one."""
    assert MAX_ROUNDS == 2
