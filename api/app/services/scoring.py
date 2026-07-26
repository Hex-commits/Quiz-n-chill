"""Grading rules for Zuordnungsfragen.

Dependency-free on purpose: no database, no HTTP, just sets and dicts. When the
rules grow -- partial credit, penalties for mislabelling a real item as fake,
bonus points for spotting every fake -- this is the only file that changes, and
it stays trivial to unit test.
"""

from uuid import UUID


def grade_item(
    *,
    assigned_category_id: UUID | None,
    correct_category_id: UUID | None,
) -> bool:
    """Is a single item assigned correctly?

    Both values are `None` for a fake the player correctly left unassigned, so
    the comparison handles fakes without a special case: declaring an item fake
    and it actually being fake is just `None == None`.
    """
    return assigned_category_id == correct_category_id


def score_assignments(
    *,
    correct_by_item: dict[UUID, UUID | None],
    assigned_by_item: dict[UUID, UUID | None],
) -> dict[UUID, bool]:
    """Grade every item in the quiz.

    Iterates the answer key rather than the submission, so an item the player
    never touched counts as unassigned (and is only right if it was a fake), and
    an unknown item id in the submission cannot inflate the score.
    """
    return {
        item_id: grade_item(
            assigned_category_id=assigned_by_item.get(item_id),
            correct_category_id=correct_category_id,
        )
        for item_id, correct_category_id in correct_by_item.items()
    }
