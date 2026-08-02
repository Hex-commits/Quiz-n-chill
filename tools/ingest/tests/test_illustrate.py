"""Deciding whether a question becomes a picture question.

Two things under test, and both encode a bug or a measurement rather than a
reading of the docs.

`_current_value` came out of a dry run whose board read "London -> Römisches
Kaiserreich". Wikidata keeps history and lists it first.

The orientation rule came from measuring the existing question set: image
coverage sits on whichever side happens to be a concrete thing, and that is not
reliably the side the model called "answer". The replay at the bottom is that
measurement, frozen.

No network anywhere here: the provider is a stub, which is the point of it being
a protocol.
"""

from __future__ import annotations

import pytest

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.pipeline.illustrate import flip, illustrate, keep_illustrated
from tools.ingest.sources.protocols import Document, Image
from tools.ingest.sources.wikimedia_images import (
    _current_value,
    _strip_html,
    commons_url,
)

DOC = Document(id="1", title="Testartikel", url="https://example.test/a", text="…")


class StubImages:
    """An `ImageProvider` that illustrates exactly the labels it was given."""

    def __init__(self, *illustratable: str):
        self.have = set(illustratable)
        self.asked: list[list[str]] = []

    def images_for(self, labels, *, document):
        self.asked.append(list(labels))
        return {
            label: Image(file=f"{label}.jpg", licence="CC BY-SA 4.0")
            for label in labels
            if label in self.have
        }


def question(*pairs: tuple[str, str]) -> GeneratedQuestion:
    return GeneratedQuestion(
        usable=True,
        subject_slug="naturwissenschaft",
        slug="elemente",
        title="Elemente und Symbole",
        description="Ordne zu.",
        pairs=[GeneratedPair(label=label, answer=answer) for label, answer in pairs],
    )


ELEMENTS = question(("Eisen", "Fe"), ("Sauerstoff", "O"), ("Gold", "Au"))



def test_pictures_on_the_categories_are_used_as_they_are():
    """Where the pictures have to end up: a category is the board, so a
    photographic category is the thing being asked about."""
    decision = illustrate(ELEMENTS, DOC, StubImages("Eisen", "Sauerstoff", "Gold"), min_pairs=3)

    assert decision.is_picture
    assert not decision.flipped
    assert set(decision.images) == {"Eisen", "Sauerstoff", "Gold"}


def test_pictures_on_the_answers_flip_the_pairing():
    """The measured case. `automarken-laender` has photographs of the countries
    and none of the marques, so a pipeline that only ever looked at the category
    side would throw it away. Flipping brings them round to the board."""
    decision = illustrate(ELEMENTS, DOC, StubImages("Fe", "O", "Au"), min_pairs=3)

    assert decision.is_picture
    assert decision.flipped
    assert set(decision.images) == {"Fe", "O", "Au"}


def test_the_category_side_is_preferred_when_both_would_work():
    """No reason to turn the question round when the pictures are already where
    they belong, and a flip costs a model call to rename it."""
    both = StubImages("Fe", "O", "Au", "Eisen", "Sauerstoff", "Gold")

    decision = illustrate(ELEMENTS, DOC, both, min_pairs=3)

    assert not decision.flipped
    assert set(decision.images) == {"Eisen", "Sauerstoff", "Gold"}


def test_a_fully_covered_category_side_costs_only_one_lookup():
    """The reason it is checked first."""
    provider = StubImages("Eisen", "Sauerstoff", "Gold")

    illustrate(ELEMENTS, DOC, provider, min_pairs=3)

    assert len(provider.asked) == 1


def test_partial_coverage_leaves_it_a_text_question():
    """A board of eight photographs and two words makes the words trivial, and
    a label that failed to resolve is one we could not identify -- pairing a
    picture with it is exactly the mistake worth refusing."""
    decision = illustrate(ELEMENTS, DOC, StubImages("Fe", "O"), min_pairs=3)

    assert not decision.is_picture
    assert "2/3" in decision.detail


def test_no_pictures_anywhere_is_not_a_failure():
    decision = illustrate(ELEMENTS, DOC, StubImages(), min_pairs=3)

    assert not decision.is_picture
    assert decision.images == {}


def test_a_question_with_no_pairs_is_handled():
    assert not illustrate(question(), DOC, StubImages(), min_pairs=3).is_picture



def test_flipping_reverses_every_pair():
    flipped = flip(ELEMENTS)

    assert flipped.labels == ["Fe", "O", "Au"]
    assert flipped.answers == ["Eisen", "Sauerstoff", "Gold"]


def test_flipping_drops_explanations():
    """"Hauptstadt Deutschlands seit 1990" explains why Berlin belongs to
    Germany, not why Germany belongs to Berlin. `explain` runs after the flip."""
    with_reasons = ELEMENTS.model_copy(update={"explanations": {"Fe": "Ordnungszahl 26."}})

    assert flip(with_reasons).explanations == {}


def test_a_flipped_question_is_still_a_valid_pairing():
    """Why flipping is safe: every rule the validator enforces is symmetric."""
    from tools.ingest.domain.validate import validate

    flipped = flip(ELEMENTS)
    problems = [p for p in validate(flipped, subject_slugs={"naturwissenschaft"})
                if "playable range" not in p]

    assert problems == []


MEASURED = [
    (
        "automarken-laender",
        [("Audi", "Deutschland"), ("Fiat", "Italien"), ("Volvo", "Schweden")],
        {"Deutschland", "Italien", "Schweden"},
        True,
    ),
    (
        "chemische-elemente",
        [("Eisen", "Fe"), ("Sauerstoff", "O"), ("Gold", "Au")],
        {"Eisen", "Sauerstoff", "Gold"},
        False,
    ),
    (
        "bauwerke-baustile",
        [("Kölner Dom", "Gotik"), ("Petersdom", "Barock"), ("Parthenon", "Antike")],
        {"Kölner Dom", "Petersdom", "Parthenon"},
        False,
    ),
    (
        "gemaelde-maler",
        [("Mona Lisa", "Leonardo da Vinci"), ("Guernica", "Pablo Picasso")],
        {"Leonardo da Vinci", "Pablo Picasso"},
        True,
    ),
]


@pytest.mark.parametrize("name,pairs,illustrated,expect_flip", MEASURED)
def test_orientation_matches_what_was_measured(name, pairs, illustrated, expect_flip):
    decision = illustrate(question(*pairs), DOC, StubImages(*illustrated), min_pairs=len(pairs))

    assert decision.is_picture, f"{name} should be a picture question"
    assert decision.flipped is expect_flip, name


def test_a_board_keeps_only_the_pairs_that_have_a_picture():
    """A fourteen-pair question with twelve pictures is a good twelve-pair
    picture question. Refusing it throws away the two commonest shapes: a list
    entry with no photograph, and a name the resolver could not place."""
    big = question(*[(f"Stadt {n}", f"Land {n}") for n in range(12)])
    have = [f"Stadt {n}" for n in range(10)]

    decision = illustrate(big, DOC, StubImages(*have), min_pairs=10)
    trimmed = keep_illustrated(big, decision)

    assert decision.is_picture
    assert not decision.flipped
    assert decision.dropped == ("Stadt 10", "Stadt 11")
    assert trimmed.labels == have
    assert len(trimmed.pairs) == 10


def test_a_board_that_would_fall_below_the_floor_stays_text():
    big = question(*[(f"Stadt {n}", f"Land {n}") for n in range(12)])

    decision = illustrate(big, DOC, StubImages(*[f"Stadt {n}" for n in range(9)]), min_pairs=10)

    assert not decision.is_picture
    assert "needs 10" in decision.detail


def test_a_fully_covered_board_is_not_copied():
    """Nothing to trim, so the question comes back as it went in."""
    decision = illustrate(ELEMENTS, DOC, StubImages("Eisen", "Sauerstoff", "Gold"), min_pairs=3)

    assert keep_illustrated(ELEMENTS, decision) is ELEMENTS


def test_a_flipped_board_is_trimmed_against_its_new_categories():
    """`keep_illustrated` runs on the already-flipped question, so the pairs it
    keeps are the ones whose *new* category resolved."""
    big = question(*[(f"Land {n}", f"Stadt {n}") for n in range(12)])
    have = [f"Stadt {n}" for n in range(10)]

    decision = illustrate(big, DOC, StubImages(*have), min_pairs=10)
    trimmed = keep_illustrated(flip(big), decision)

    assert decision.flipped
    assert trimmed.labels == have
    assert trimmed.answers == [f"Land {n}" for n in range(10)]



def claim(value: str, *, rank: str = "normal", ended: bool = False) -> dict:
    return {
        "rank": rank,
        "mainsnak": {"datavalue": {"value": {"id": value}}},
        **({"qualifiers": {"P582": [{}]}} if ended else {}),
    }


def test_a_statement_that_has_ended_is_not_the_answer():
    """The bug this exists for. London's `P17` lists the Roman Empire, Berlin's
    the Margraviate of Brandenburg -- correct history, and ahead of the modern
    country in the order the API returns."""
    assert _current_value([claim("Q2277", ended=True), claim("Q145")]) == {"id": "Q145"}


def test_a_preferred_statement_wins():
    assert _current_value([claim("Q1"), claim("Q2", rank="preferred")]) == {"id": "Q2"}


def test_a_deprecated_statement_is_never_used():
    assert _current_value([claim("Q1", rank="deprecated"), claim("Q2")]) == {"id": "Q2"}


def test_an_entity_with_only_historical_statements_yields_nothing():
    assert _current_value([claim("Q2277", ended=True)]) is None


def test_no_statements_at_all():
    assert _current_value([]) is None
    assert _current_value(None) is None



def test_a_credit_survives_the_html_it_arrives_in():
    raw = '<a href="//commons.wikimedia.org/wiki/User:X" title="User:X">Jemand</a>'

    assert _strip_html(raw) == "Jemand"


def test_a_commons_url_is_built_from_a_bare_file_name():
    """Thumbnails live at a hash-derived path that cannot be computed from the
    name, which is why the name is what gets stored."""
    url = commons_url("Cityscape Berlin.jpg", width=480)

    assert url.endswith("Special:FilePath/Cityscape_Berlin.jpg?width=480")
