"""Topping up a question that is worth keeping but came up short.

No network and no model anywhere here: the finder is a stub and `find_pairs` is
a plain callable, which is the point of both being parameters.

What is under test is the judgement, not the plumbing -- when to go looking,
what may be added, and the two ways this step could quietly ruin a question:
adding a pair that collides with one already on the board, and adding one that
is a different kind of pairing from the rest. Both were observed rather than
imagined; the second came out of a live run.
"""

from __future__ import annotations

import pytest

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.domain.rules import MIN_PAIRS
from tools.ingest.domain.validate import only_needs_more_pairs, validate
from tools.ingest.pipeline.augment import (
    Augmentation,
    augment,
    fresh_pairs,
    merge,
    query_for,
    taken,
)
from tools.ingest.sources.protocols import Document

ARTICLE = Document(id="1", title="Flüsse Europas", url="https://example.test/a", text="…")


def other(title: str, text: str = "…") -> Document:
    return Document(id=title, title=title, url=f"https://example.test/{title}", text=text)


def question(*pairs: tuple[str, str], difficulty: str = "medium") -> GeneratedQuestion:
    return GeneratedQuestion(
        usable=True,
        subject_slug="geografie",
        slug="fluesse",
        title="Flüsse und ihre Länge",
        description="Ordne zu.",
        difficulty=difficulty,
        pairs=[GeneratedPair(label=label, answer=answer) for label, answer in pairs],
    )


SHORT = question(("Rhein", "1233 km"), ("Elbe", "1094 km"), ("Donau", "2857 km"))


class StubFinder:
    """A `RelatedDocuments` that hands back whatever it was constructed with."""

    def __init__(self, *documents: Document):
        self.documents = list(documents)
        self.queries: list[str] = []
        self.limits: list[int] = []

    def related(self, document, *, query: str, limit: int):
        self.queries.append(query)
        self.limits.append(limit)
        return [d for d in self.documents if d.title != document.title][:limit]


def yields(mapping: dict[str, list[tuple[str, str]]]):
    """A `find_pairs` that returns canned pairs per document title."""
    calls: list[tuple[str, int]] = []

    def find(document, needed: int):
        calls.append((document.title, needed))
        return [
            GeneratedPair(label=label, answer=answer)
            for label, answer in mapping.get(document.title, [])
        ]

    find.calls = calls  # type: ignore[attr-defined]
    return find


# -- when it should run at all -----------------------------------------------


def test_a_short_question_with_one_complaint_is_a_candidate():
    assert only_needs_more_pairs(SHORT, ["3 pairs, playable range is 10-14"])


def test_a_short_question_with_a_second_complaint_is_not():
    """Adding pairs cannot fix a duplicate answer, so searching would be spent
    on a question the repair loop still has to argue with."""
    assert not only_needs_more_pairs(SHORT, ["3 pairs, ...", "duplicate answer"])


def test_a_long_enough_question_is_not_a_candidate():
    full = question(*[(f"Fluss {n}", f"{n} km") for n in range(MIN_PAIRS)])
    assert not only_needs_more_pairs(full, ["something else"])


def test_the_predicate_does_not_read_the_complaint_text():
    """It is asked of the question, so rewording the validator's message -- which
    is tuned for the model and has been rewritten twice -- cannot silently turn
    the routing off."""
    assert only_needs_more_pairs(SHORT, ["anything at all"])


# -- the search --------------------------------------------------------------


def test_the_query_names_the_question_and_its_categories():
    query = query_for(SHORT)

    assert "Flüsse und ihre Länge" in query
    assert "Rhein" in query


def test_pairs_are_gathered_until_the_shortfall_is_covered():
    finder = StubFinder(other("Donau"), other("Weichsel"))
    find = yields({"Donau": [("Weser", "452 km"), ("Main", "527 km")]})

    result = augment(SHORT, ARTICLE, finder, find, needed=2)

    assert result.found
    assert [(p.label, p.answer) for p in result.pairs] == [
        ("Weser", "452 km"),
        ("Main", "527 km"),
    ]
    assert [d.title for d in result.documents] == ["Donau"]


def test_reading_stops_as_soon_as_there_is_enough():
    """Each article is a fetch and a model call, so the common case -- a
    two-pair shortfall covered by the first neighbour -- must not pay for four."""
    finder = StubFinder(other("Donau"), other("Weichsel"), other("Loire"))
    find = yields({
        "Donau": [("Weser", "452 km")],
        "Weichsel": [("Main", "527 km")],
        "Loire": [("Ems", "371 km")],
    })

    augment(SHORT, ARTICLE, finder, find, needed=2)

    assert find.calls == [("Donau", 2), ("Weichsel", 1)]


def test_it_asks_only_for_what_is_still_missing():
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": []})

    augment(SHORT, ARTICLE, finder, find, needed=3)

    assert find.calls == [("Donau", 3)]


def test_no_related_articles_is_not_a_failure():
    result = augment(SHORT, ARTICLE, StubFinder(), yields({}), needed=2)

    assert not result.found
    assert "no related articles" in result.detail


def test_articles_that_yield_nothing_are_not_credited():
    finder = StubFinder(other("Donau"), other("Weichsel"))
    find = yields({"Weichsel": [("Weser", "452 km")]})

    result = augment(SHORT, ARTICLE, finder, find, needed=1)

    assert [d.title for d in result.documents] == ["Weichsel"]


def test_nothing_needed_costs_no_search():
    finder = StubFinder(other("Donau"))

    result = augment(SHORT, ARTICLE, finder, yields({}), needed=0)

    assert not result.found
    assert finder.queries == []


# -- what may be added -------------------------------------------------------


def test_a_pair_naming_something_already_on_the_board_is_dropped():
    """The failure that would make this step counterproductive: `validate` would
    catch the duplicate afterwards, but as a rejection -- taking the good pairs
    down with it."""
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": [("Rhein", "1233 km"), ("Weser", "452 km")]})

    result = augment(SHORT, ARTICLE, finder, find, needed=2)

    assert [p.label for p in result.pairs] == ["Weser"]


def test_a_pair_colliding_with_an_existing_answer_is_dropped():
    """A Zuordnung is one-to-one in both directions, so a new *category* that is
    already an answer breaks it just as surely as a duplicate label."""
    board = question(("Rhein", "Bodensee"), ("Elbe", "Riesengebirge"))
    finder = StubFinder(other("Seen"))
    find = yields({"Seen": [("Bodensee", "Alpenrhein")]})

    result = augment(board, ARTICLE, finder, find, needed=2)

    assert not result.found


def test_repeats_within_one_batch_are_dropped():
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": [("Weser", "452 km"), ("Weser", "452 km")]})

    result = augment(SHORT, ARTICLE, finder, find, needed=2)

    assert len(result.pairs) == 1


def test_a_self_referential_pair_is_dropped():
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": [("Weser", "Weser")]})

    assert not augment(SHORT, ARTICLE, finder, find, needed=1).found


def test_never_more_than_asked_for():
    """The grammar bounds this too, but a finder that over-delivers must not push
    the question past MAX_PAIRS and fail the check it was called to satisfy."""
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": [(f"Fluss {n}", f"{n} km") for n in range(9)]})

    result = augment(SHORT, ARTICLE, finder, find, needed=2)

    assert len(result.pairs) == 2


def test_taken_covers_both_sides_of_every_pair():
    assert taken(SHORT) == {"rhein", "1233 km", "elbe", "1094 km", "donau", "2857 km"}


def test_fresh_pairs_is_case_insensitive():
    kept = fresh_pairs(SHORT, [GeneratedPair(label="RHEIN", answer="999 km")])

    assert kept == []


# -- merging back ------------------------------------------------------------


def test_merging_appends_and_leaves_the_original_pairs_first():
    extra = Augmentation(pairs=(GeneratedPair(label="Weser", answer="452 km"),))

    merged = merge(SHORT, extra)

    assert merged.labels == ["Rhein", "Elbe", "Donau", "Weser"]


def test_merging_nothing_returns_the_question_unchanged():
    assert merge(SHORT, Augmentation()) is SHORT


def test_a_topped_up_question_passes_the_validator():
    """The whole point: what comes out has to satisfy the same check that sent
    it here in the first place."""
    board = question(*[(f"Fluss {n}", f"{n} km") for n in range(MIN_PAIRS - 2)])
    finder = StubFinder(other("Donau"))
    find = yields({"Donau": [("Weser", "452 km"), ("Main", "527 km")]})

    topped = merge(board, augment(board, ARTICLE, finder, find, needed=2))

    assert len(topped.pairs) == MIN_PAIRS
    assert validate(topped, subject_slugs={"geografie"}) == []
