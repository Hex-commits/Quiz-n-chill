"""Tests for the explain step.

It is the one step in the graph that is decoration rather than judgement: it
can improve a question but never reject one. Most of what is worth testing is
that failing does no harm.

The source text it is shown is shared with `review`, which is the point: a
borrowed pair's evidence is in the article it came from, and a step asked to
judge or describe it without that text has nothing to read. `review` was given
the neighbours and `explain` was not, so it answered from its own knowledge
instead.
"""

from __future__ import annotations

from tools.ingest.domain.models import (
    MAX_EXPLANATION_CHARS,
    GeneratedPair,
    GeneratedQuestion,
    explanation_schema,
)
from tools.ingest.pipeline.chains import (
    EXTRA_SOURCE_CHARS,
    MAX_EXTRA_SOURCES,
    as_explanations,
    source_text,
)
from tools.ingest.sources.protocols import Document
from tools.ingest.sources.wikipedia import Article

QUESTION = GeneratedQuestion(
    usable=True,
    subject_slug="geografie",
    slug="hauptstaedte",
    title="Hauptstädte",
    difficulty="easy",
    pairs=[
        GeneratedPair(label="Deutschland", answer="Berlin"),
        GeneratedPair(label="Frankreich", answer="Paris"),
        GeneratedPair(label="Portugal", answer="Lissabon"),
    ],
)


def test_every_answer_can_be_explained():
    lines = as_explanations({"explanations": [
        {"answer": "Berlin", "why": "Hauptstadt Deutschlands seit 1990."},
        {"answer": "Paris", "why": "Hauptstadt Frankreichs."},
        {"answer": "Lissabon", "why": "Hauptstadt Portugals."},
    ]}, QUESTION)

    assert set(lines) == {"Berlin", "Paris", "Lissabon"}
    assert "Portugals" in lines["Lissabon"]


def test_an_answer_that_is_not_on_the_board_is_dropped():
    """Constrained decoding should prevent it; this is the backstop, because a
    stray label would otherwise be stored against nothing."""
    lines = as_explanations({"explanations": [
        {"answer": "Madrid", "why": "Steht gar nicht zur Wahl."},
        {"answer": "Berlin", "why": "Hauptstadt Deutschlands."},
    ]}, QUESTION)

    assert set(lines) == {"Berlin"}


def test_the_first_line_for_an_answer_wins():
    lines = as_explanations({"explanations": [
        {"answer": "Berlin", "why": "Erste."},
        {"answer": "Berlin", "why": "Zweite."},
    ]}, QUESTION)

    assert lines["Berlin"] == "Erste."


def test_matching_ignores_case_but_stores_the_boards_spelling():
    lines = as_explanations(
        {"explanations": [{"answer": "berlin", "why": "Hauptstadt."}]}, QUESTION
    )

    assert "Berlin" in lines


def test_whitespace_is_collapsed_so_it_reads_as_one_line():
    lines = as_explanations(
        {"explanations": [{"answer": "Berlin", "why": "Hauptstadt\n\n  Deutschlands."}]},
        QUESTION,
    )

    assert lines["Berlin"] == "Hauptstadt Deutschlands."


def test_an_empty_reason_is_not_stored():
    lines = as_explanations(
        {"explanations": [{"answer": "Berlin", "why": "   "}]}, QUESTION
    )

    assert lines == {}


def test_a_missing_or_malformed_reply_yields_nothing_rather_than_raising():
    assert as_explanations({}, QUESTION) == {}
    assert as_explanations({"explanations": None}, QUESTION) == {}
    assert as_explanations({"explanations": ["not a dict"]}, QUESTION) == {}


def test_a_partial_reply_keeps_what_it_got():
    """Explaining six of eight answers is better than explaining none."""
    lines = as_explanations(
        {"explanations": [{"answer": "Berlin", "why": "Hauptstadt Deutschlands."}]},
        QUESTION,
    )

    assert set(lines) == {"Berlin"}



def test_the_grammar_only_admits_answers_from_this_board():
    schema = explanation_schema(QUESTION.all_items)
    answer = schema["properties"]["explanations"]["items"]["properties"]["answer"]

    assert answer["enum"] == ["Berlin", "Lissabon", "Paris"]


def test_the_grammar_caps_the_length_so_it_fits_at_a_glance():
    """A prompt asking for brevity is a suggestion; a maxLength is not."""
    schema = explanation_schema(QUESTION.all_items)
    why = schema["properties"]["explanations"]["items"]["properties"]["why"]

    assert why["maxLength"] == MAX_EXPLANATION_CHARS
    assert MAX_EXPLANATION_CHARS <= 160


def article(text: str) -> Article:
    return Article(title="Haupt", url="https://example.test/h", summary="s", extract=text)


def neighbour(index: int, text: str = "Belegtext.") -> Document:
    return Document(id=str(index), title=f"Nachbar {index}", url="u", text=text)


def test_the_article_alone_is_the_common_case():
    text = source_text({"article": article("Nur der Artikel.")})

    assert text == article("Nur der Artikel.").text
    assert "Zusätzlicher Quelltext" not in text


def test_a_borrowed_pair_brings_the_text_that_supports_it():
    text = source_text(
        {"article": article("Der Artikel."), "extras": [neighbour(1, "Die Donau ist 2857 km lang.")]}
    )

    assert "Der Artikel." in text
    assert "Nachbar 1" in text
    assert "Die Donau ist 2857 km lang." in text


def test_each_neighbour_is_capped_so_one_cannot_crowd_out_the_article():
    text = source_text({"article": article("Kurz."), "extras": [neighbour(1, "x" * 50_000)]})

    assert len(text) < EXTRA_SOURCE_CHARS + 200


def test_the_neighbours_are_counted_as_well_as_capped():
    """Two augment rounds of four articles each is 24k characters of neighbours
    on top of the article, which does not fit in an 8k context however carefully
    each one is trimmed."""
    text = source_text(
        {"article": article("Kurz."), "extras": [neighbour(i) for i in range(1, 6)]}
    )

    assert "Nachbar 1" in text
    assert "Nachbar 3" not in text
    assert text.count("Zusätzlicher Quelltext") == MAX_EXTRA_SOURCES
