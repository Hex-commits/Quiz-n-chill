"""Tests for the prompt templates themselves.

Small, but they catch a whole class of silent breakage: a template that renders
without its variables filled still produces a *plausible* prompt, and the model
answers it. The failure shows up as poor questions, not as an error.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tools.ingest.domain.models import GeneratedQuestion, question_schema
from tools.ingest.domain.validate import validate
from tools.ingest.pipeline.prompts import EXTRACT, REPAIR, REVIEW
from tools.ingest.domain import rules


def extract_input(**overrides) -> dict:
    base = {
        "title": "Kaffee",
        "text": "...",
        "subjects": "- geografie: Geografie",
        "drafts": 2,
    }
    base.update(overrides)
    return base


def test_the_extract_prompt_declares_exactly_what_it_needs():
    assert set(EXTRACT.input_variables) == {"title", "text", "subjects", "drafts"}


def test_a_missing_variable_is_an_error_not_a_half_filled_prompt():
    with pytest.raises(KeyError):
        EXTRACT.invoke({"title": "Kaffee", "text": "..."})


def test_the_repair_placeholder_is_empty_on_the_first_attempt():
    messages = EXTRACT.invoke(extract_input()).to_messages()

    assert [m.type for m in messages] == ["system", "human"]


def test_repair_turns_are_appended_after_the_article():
    """Order matters: the article has to come first, or the complaints refer to
    something the model has not been shown yet."""
    messages = EXTRACT.invoke(
        extract_input(
            repairs=[AIMessage('{"usable": true}'), HumanMessage("Zu viele Fakes.")]
        )
    ).to_messages()

    assert [m.type for m in messages] == ["system", "human", "ai", "human"]
    assert "Kaffee" in messages[1].content
    assert "Zu viele Fakes." in messages[3].content


def test_the_review_prompt_takes_no_transcript():
    """Fresh context is the design -- there is deliberately no placeholder for
    the generator's conversation."""
    assert set(REVIEW.input_variables) == {"text", "title", "pairs"}


def test_both_system_prompts_state_the_one_to_one_rule():
    """It is the rule the whole design turns on, and both ends need it: a
    generator that groups two answers under one category and a reviewer that
    accepts it produce the same unplayable question."""
    for template in (EXTRACT, REVIEW):
        system = template.messages[0].prompt.template
        assert "genau eine" in system.lower()


def test_the_extract_prompt_shows_the_repeated_category_mistake():
    """Told the rule abstractly, a small model still groups. The worked example
    of what NOT to do is what stops it."""
    system = EXTRACT.messages[0].prompt.template

    assert "19. Jahrhundert" in system
    assert "FALSCH" in system


def test_the_repair_prompt_asks_for_removal_rather_than_invention():
    """Told only to 'fix it', a small model replaces a wrong pair with an
    invented one, which is worse than declining the article."""
    rendered = REPAIR.format(problems="- answers appear more than once")

    assert "answers appear more than once" in rendered
    assert "lieber ganz weg" in rendered
    assert "usable" in rendered  # the way out when a fix drops it below six


# -- the grammar handed to Ollama ----------------------------------------


@pytest.mark.parametrize("key", ["usable", "pairs", "difficulty", "subject_slug"])
def test_the_schema_covers_every_field(key):
    assert key in question_schema(["geografie"])["properties"]


def test_every_field_is_required_in_the_schema():
    """Pydantic's own schema omits defaulted fields from `required`, and a 9B
    model then happily returns `subject_slug: ""`. This is that regression."""
    schema = question_schema(["geografie"])

    assert set(schema["required"]) == set(schema["properties"])
    assert "subject_slug" in schema["required"]
    assert "title" in schema["required"]


def test_the_grammar_restricts_subject_and_difficulty_to_valid_values():
    """Anything the grammar can enforce should be impossible to emit, not
    merely rejected afterwards."""
    schema = question_schema(["musik", "geografie"])

    assert schema["properties"]["subject_slug"]["enum"] == ["geografie", "musik"]
    assert schema["properties"]["difficulty"]["enum"] == ["easy", "medium", "hard"]


def test_the_grammar_holds_the_ceiling_but_not_the_floor():
    """A ceiling needs no escape hatch; a floor does.

    `MIN_PAIRS` was in the grammar, and Ollama enforces it -- which made a short
    reply unrepresentable, so a model with too little material could not take the
    way out the prompt offers it and padded the board by repeating itself
    instead. Measured on glm4:9b with a four-fact article: with the floor,
    `usable: true` and up to eight of twelve answers duplicated; without it, four
    clean pairs every time. On a rich article the floor bought nothing.

    So the floor is the validator's alone -- which is also what gives `augment` a
    short question to top up.
    """
    pairs = question_schema(["geografie"])["properties"]["pairs"]

    assert "minItems" not in pairs
    assert pairs["maxItems"] == rules.MAX_PAIRS


def test_the_validator_is_the_one_holding_the_floor():
    short = GeneratedQuestion.model_validate({
        "usable": True,
        "subject_slug": "geografie",
        "slug": "kurz",
        "title": "Kurz",
        "difficulty": "medium",
        "pairs": [{"label": f"K{i}", "answer": f"A{i}"} for i in range(4)],
    })

    problems = validate(short, subject_slugs={"geografie"})

    assert len(problems) == 1, problems
    assert f"playable range is {rules.MIN_PAIRS}" in problems[0]


def test_the_grammar_makes_a_grouped_category_unrepresentable():
    """The strongest form of the rule: a pair holds one `answer` string, so
    "two answers under one category" cannot be emitted at all -- it is not
    rejected afterwards, it has no shape in the grammar."""
    pair = question_schema(["geografie"])["properties"]["pairs"]["items"]

    assert pair["properties"]["answer"]["type"] == "string"
    assert set(pair["required"]) == {"label", "answer"}
    assert pair["additionalProperties"] is False


def test_the_extract_prompt_pins_down_which_side_is_which():
    """glm4 reversed the roles on its first real run -- `"Steadfast and Loyal"
    -> "Motto"` instead of `"Motto" -> "Steadfast and Loyal"` -- which reads as
    a question with the answers already given away."""
    system = EXTRACT.messages[0].prompt.template

    assert "Rollen vertauscht" in system
    assert "label" in system and "answer" in system


def test_the_extract_prompt_rejects_single_subject_questions():
    """A question comparing several like things is the format; a list of one
    thing's attributes is not, and the model produced several of those."""
    system = EXTRACT.messages[0].prompt.template

    assert "MEHRERE gleichartige Dinge" in system
