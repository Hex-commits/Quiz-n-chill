"""An explanation must not reach a player before they have answered.

It says *why* an answer belongs where it does, so it gives the answer away as
surely as `category_id` would. The rule is the one already applied to
`quizzes.source_url`: absent while playing, present once graded.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas import Category, ItemPublic, ItemResult, ItemSolution, RoundView


def test_the_player_facing_item_has_nowhere_to_put_an_explanation():
    """Structural, not a filter: `ItemPublic` has no such field, so no query
    change or careless `**row` can leak one through it."""
    assert "explanation" not in ItemPublic.model_fields
    assert "category_id" not in ItemPublic.model_fields


def test_the_solution_view_carries_it():
    item = ItemSolution(
        id=uuid4(), label="Berlin", position=1, category_id=uuid4(),
        explanation="Hauptstadt Deutschlands seit 1990.",
    )

    assert item.explanation == "Hauptstadt Deutschlands seit 1990."


def test_an_item_without_an_explanation_is_still_valid():
    """Everything seeded or generated before the explain step exists has none,
    and that must render as nothing rather than fail."""
    item = ItemSolution(id=uuid4(), label="Berlin", position=1, category_id=uuid4())

    assert item.explanation is None


def test_the_graded_result_carries_it():
    portugal = uuid4()
    result = ItemResult(
        item_id=uuid4(), label="Lissabon", assigned_category_id=portugal,
        correct_category_id=portugal, is_correct=True,
        explanation="Hauptstadt Portugals seit 1255.",
    )

    assert "Portugal" in result.explanation


def test_a_graded_result_can_say_the_answer_belonged_nowhere():
    """`correct_category_id` is optional again, and null is a real verdict:
    the answer was a fake, and the player who said so was right."""
    result = ItemResult(
        item_id=uuid4(), label="Lissabon", assigned_category_id=None,
        correct_category_id=None, is_correct=True, explanation=None,
    )

    assert result.correct_category_id is None


def test_a_round_in_progress_serialises_without_any_explanation():
    """The end-to-end guard: whatever a player is sent mid-round, the word must
    not appear in it."""
    view = RoundView(
        quiz_id=uuid4(), slug="hauptstaedte", title="Hauptstädte",
        description=None, difficulty="easy",
        categories=[Category(id=uuid4(), label="Deutschland", position=1)],
        remaining_items=[ItemPublic(id=uuid4(), label="Berlin")],
        solved_items=[],
    )

    assert "explanation" not in view.model_dump_json()
