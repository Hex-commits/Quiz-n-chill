"""Grading rules for Zuordnungsfragen.

Dependency-free on purpose: no database, no HTTP, just sets and dicts. When the
rules grow -- partial credit, streak bonuses -- this is the only file that
changes, and it stays trivial to unit test.

A question is a one-to-one pairing: every answer belongs to exactly one
category. So grading is a single comparison, and leaving an answer unplaced is
simply wrong -- there is no longer any case where *not* placing something is the
correct move.
"""

from uuid import UUID


def grade_item(
    *,
    assigned_category_id: UUID | None,
    correct_category_id: UUID,
) -> bool:
    """Is a single answer paired with the right category?

    `assigned_category_id` stays optional because a player can submit before
    placing everything; an unplaced answer is `None` and therefore wrong.
    """
    return assigned_category_id == correct_category_id


def score_assignments(
    *,
    correct_by_item: dict[UUID, UUID],
    assigned_by_item: dict[UUID, UUID | None],
) -> dict[UUID, bool]:
    """Grade every answer in the quiz.

    Iterates the answer key rather than the submission, so an answer the player
    never placed counts as wrong rather than being skipped, and an unknown item
    id in the submission cannot inflate the score.
    """
    return {
        item_id: grade_item(
            assigned_category_id=assigned_by_item.get(item_id),
            correct_category_id=correct_category_id,
        )
        for item_id, correct_category_id in correct_by_item.items()
    }
