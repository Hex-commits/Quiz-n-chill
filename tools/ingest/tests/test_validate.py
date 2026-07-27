"""Tests for the structural gate.

A question is a one-to-one pairing: every category holds exactly one answer and
every answer belongs to exactly one category. Most of what is checked here is
that promise, because breaking it is what makes a question unanswerable rather
than merely untidy.
"""

import pytest

from tools.ingest.domain.models import GeneratedPair, GeneratedQuestion
from tools.ingest.domain.validate import slugify, validate

SUBJECTS = {"geografie", "musik"}

CAPITALS = [
    ("Deutschland", "Berlin"),
    ("Frankreich", "Paris"),
    ("Italien", "Rom"),
    ("Spanien", "Madrid"),
    ("Portugal", "Lissabon"),
    ("Österreich", "Wien"),
]


def question(**overrides) -> GeneratedQuestion:
    """A valid question: six clean pairs."""
    base = dict(
        usable=True,
        subject_slug="geografie",
        slug="hauptstaedte-europas",
        title="Hauptstädte Europas",
        description="Ordne jede Hauptstadt ihrem Land zu.",
        difficulty="medium",
        pairs=[GeneratedPair(label=label, answer=answer) for label, answer in CAPITALS],
    )
    base.update(overrides)
    return GeneratedQuestion(**base)


def pairs(*items) -> list[GeneratedPair]:
    return [GeneratedPair(label=label, answer=answer) for label, answer in items]


def check(**overrides) -> list[str]:
    return validate(question(**overrides), subject_slugs=SUBJECTS)


def test_a_well_formed_question_passes():
    assert check() == []


def test_the_model_declining_is_reported_not_silently_dropped():
    problems = validate(
        GeneratedQuestion(usable=False, reason="Artikel enthält keine Paare."),
        subject_slugs=SUBJECTS,
    )
    assert problems == ["model declined: Artikel enthält keine Paare."]


def test_an_invented_subject_is_rejected():
    assert any("unknown subject_slug" in p for p in check(subject_slug="astrologie"))


def test_an_invented_difficulty_is_rejected():
    assert any("difficulty" in p for p in check(difficulty="unmöglich"))


@pytest.mark.parametrize("slug", ["Flüsse Europas", "fluesse_europas", "-leading", ""])
def test_non_url_safe_slugs_are_rejected(slug):
    assert any("not url-safe" in p for p in check(slug=slug))


# -- the pairing itself --------------------------------------------------


def test_a_repeated_category_is_rejected_and_named():
    """The rule the whole design turns on: `19. Jahrhundert` cannot hold two
    answers, so it cannot appear twice."""
    problems = check(pairs=pairs(
        ("18. Jahrhundert", "Französische Revolution"),
        ("19. Jahrhundert", "Deutsche Reichsgründung"),
        ("19. Jahrhundert", "Wiener Kongress"),
        ("20. Jahrhundert", "Mondlandung"),
        ("21. Jahrhundert", "Brexit"),
        ("17. Jahrhundert", "Dreissigjaehriger Krieg"),
    ))
    complaint = next(p for p in problems if "categories appear more than once" in p)

    assert "19. Jahrhundert" in complaint
    assert "only once" in complaint


def test_a_repeated_answer_is_rejected_and_named():
    problems = check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("Frankreich", "Berlin"),
        ("Italien", "Rom"),
        ("Spanien", "Madrid"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    ))
    complaint = next(p for p in problems if "answers appear more than once" in p)

    assert "Berlin" in complaint
    assert "exactly one category" in complaint


def test_repeats_are_matched_case_insensitively_but_echoed_as_written():
    problems = check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("Frankreich", "berlin"),
        ("Italien", "Rom"),
        ("Spanien", "Madrid"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    ))

    assert any("'Berlin'" in p for p in problems)


def test_a_term_used_as_both_category_and_answer_is_rejected():
    problems = check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("Frankreich", "Paris"),
        ("Italien", "Rom"),
        ("Berlin", "Brandenburger Tor"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    ))

    assert any("both a category and an answer" in p for p in problems)


# -- size ----------------------------------------------------------------


def test_too_few_pairs_is_rejected_and_offers_the_way_out():
    """Five pairs is not a small question; the right answer is to decline the
    article, and the complaint has to say so."""
    problems = check(pairs=pairs(*CAPITALS[:5]))
    complaint = next(p for p in problems if "playable range" in p)

    assert "6-10" in complaint
    assert "usable to false" in complaint


def test_too_many_pairs_is_rejected():
    many = [(f"Land {i}", f"Stadt {i}") for i in range(11)]

    assert any("playable range" in p for p in check(pairs=pairs(*many)))


def test_ten_pairs_is_the_ceiling_and_is_allowed():
    ten = [(f"Land {i}", f"Stadt {i}") for i in range(10)]

    assert check(pairs=pairs(*ten)) == []


# -- answers -------------------------------------------------------------


def test_an_answer_longer_than_four_words_is_rejected():
    problems = check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("Frankreich", "Paris"),
        ("Italien", "Rom"),
        ("Gesundheit", "Geringeres Risiko für kardiovaskuläre Erkrankungen"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    ))
    complaint = next(p for p in problems if "longer than" in p)

    assert "kardiovaskuläre" in complaint
    assert "drop that pair" in complaint


def test_an_empty_answer_is_rejected():
    assert any("no answer" in p for p in check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("Frankreich", "  "),
        ("Italien", "Rom"),
        ("Spanien", "Madrid"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    )))


def test_an_empty_category_name_is_rejected():
    assert any("no name" in p for p in check(pairs=pairs(
        ("Deutschland", "Berlin"),
        ("", "Paris"),
        ("Italien", "Rom"),
        ("Spanien", "Madrid"),
        ("Portugal", "Lissabon"),
        ("Österreich", "Wien"),
    )))


# -- slugs ---------------------------------------------------------------


def test_umlauts_are_spelled_out_not_stripped():
    """German convention: Flüsse -> fluesse, not flusse."""
    assert slugify("Flüsse Europas") == "fluesse-europas"
    assert slugify("Straße") == "strasse"
    assert slugify("Öl & Größe") == "oel-groesse"
