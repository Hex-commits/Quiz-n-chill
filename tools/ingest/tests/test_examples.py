"""Tests for the few-shot exemplars the prompts teach style with.

Two jobs, and the first matters more than it looks: the exemplars claim to be
questions from `supabase/seed.sql`, and a claim like that rots quietly. An
exemplar edited by hand still renders, still reads well, and teaches a style
nothing in the pool actually uses -- so the seed is read back here and compared
word for word.

The second job is that the examples must obey the rules they sit next to in the
prompt. An example that breaks one is worse than no example: shown a rule and a
counter-example of it, a small model follows the example.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.ingest.domain.models import MAX_EXPLANATION_CHARS
from tools.ingest.domain.rules import DIFFICULTIES, MAX_ITEM_WORDS, MIN_PAIRS
from tools.ingest.domain.validate import SLUG_RE, slugify
from tools.ingest.pipeline.examples import (
    EXAMPLES,
    EXPLANATION_EXAMPLES,
    render_explanations,
    render_questions,
)

SEED = Path(__file__).resolve().parents[3] / "supabase" / "seed.sql"

MAX_TITLE_WORDS = 3
MAX_DESCRIPTION_WORDS = 8
MAX_EXPLANATION_WORDS = 12


@pytest.fixture(scope="module")
def seed() -> str:
    return SEED.read_text(encoding="utf-8")


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_every_exemplar_is_a_question_from_the_seed(example, seed):
    """The whole authority of these examples is that someone wrote them by hand
    and the game was played with them. Invent one and that is gone."""
    assert f"'{example.slug}'" in seed
    assert f"'{example.title}'" in seed
    assert f"'{example.description}'" in seed
    assert f"'{example.subject_slug}'" in seed


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_every_exemplar_pair_is_a_pairing_from_the_seed(example, seed):
    for label, answer in example.pairs:
        assert f'["{label}", "{answer}", ' in seed


@pytest.mark.parametrize(
    "pair", EXPLANATION_EXAMPLES, ids=lambda pair: f"{pair.label}-{pair.answer}"
)
def test_every_explanation_exemplar_is_a_line_from_the_seed(pair, seed):
    assert f'["{pair.label}", "{pair.answer}", "{pair.why}"]' in seed



@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_the_slug_is_exactly_the_slugified_title(example):
    """The rule the prompt states -- 'the title, lowercased, hyphenated, umlauts
    spelled out' -- is `slugify` applied to the title, and nothing else. No
    article name, no `-zuordnung` suffix."""
    assert example.slug == slugify(example.title)
    assert SLUG_RE.match(example.slug)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_the_title_is_short_and_is_not_a_question(example):
    assert len(example.title.split()) <= MAX_TITLE_WORDS
    assert "?" not in example.title
    assert ":" not in example.title


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_the_description_is_one_short_question(example):
    assert example.description.endswith("?")
    assert example.description.count("?") == 1
    assert len(example.description.split()) <= MAX_DESCRIPTION_WORDS


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_the_description_gives_nothing_away(example):
    """It names the *kind* of thing being matched, never a term on the board --
    'Welche Stadt ist die Hauptstadt des Landes?', not '... von Deutschland?'."""
    words = {re.sub(r"\W", "", word).casefold() for word in example.description.split()}
    on_the_board = {
        re.sub(r"\W", "", word).casefold()
        for label, answer in example.pairs
        for word in f"{label} {answer}".split()
    }

    assert not words & on_the_board


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.slug)
def test_the_exemplar_pairs_would_survive_the_validator(example):
    """Everything the structural gate checks, checked on the examples too --
    except the count, which they deliberately do not demonstrate."""
    labels = [label for label, _ in example.pairs]
    answers = [answer for _, answer in example.pairs]

    assert example.difficulty in DIFFICULTIES
    assert len(set(labels)) == len(labels)
    assert len(set(answers)) == len(answers)
    assert not {answer.casefold() for answer in answers} & {label.casefold() for label in labels}
    assert all(len(answer.split()) <= MAX_ITEM_WORDS for answer in answers)


@pytest.mark.parametrize(
    "pair", EXPLANATION_EXAMPLES, ids=lambda pair: f"{pair.label}-{pair.answer}"
)
def test_every_explanation_exemplar_fits_what_the_explain_step_may_emit(pair):
    assert len(pair.why) <= MAX_EXPLANATION_CHARS
    assert len(pair.why.split()) <= MAX_EXPLANATION_WORDS
    assert pair.why.endswith(".")
    assert not pair.why.lower().startswith(("weil", "richtig", "diese antwort"))



def test_the_examples_never_appear_to_endorse_their_own_pair_count():
    """The seed's boards are shorter than this pipeline's floor. An example
    showing seven pairs beside a rule demanding ten teaches the seven, so every
    block is cut short and says so."""
    rendered = render_questions()

    assert all(len(example.pairs) < MIN_PAIRS for example in EXAMPLES)
    assert rendered.count("gekürzt") == len(EXAMPLES)
    assert str(MIN_PAIRS) in rendered


def test_the_examples_cover_the_range_they_are_meant_to_calibrate():
    """Four examples of one difficulty in one subject calibrate nothing. Spread
    is the reason there is more than one."""
    assert {example.difficulty for example in EXAMPLES} == set(DIFFICULTIES)
    assert len({example.subject_slug for example in EXAMPLES}) == len(EXAMPLES)


def test_both_title_shapes_are_shown():
    """'X & Y' and a plain plural are both house style; showing only one turns
    the other into a mistake."""
    joined = [example.title for example in EXAMPLES if "&" in example.title]

    assert joined
    assert len(joined) < len(EXAMPLES)


def test_the_explanation_examples_are_written_as_the_step_will_see_them():
    """The explain prompt hands the model `label -> answer` lines. The examples
    use that same shape, so nothing has to be translated across."""
    rendered = render_explanations()

    for pair in EXPLANATION_EXAMPLES:
        assert f"{pair.label} -> {pair.answer}" in rendered
        assert f"{pair.answer}: {pair.why}" in rendered
