"""Grading rules for Zuordnungsfragen.

Dependency-free on purpose: no database, no HTTP, just sets and dicts. When the
rules grow -- partial credit, streak bonuses -- this is the only file that
changes, and it stays trivial to unit test.

A question is a one-to-one pairing, plus a couple of fakes: every answer either
belongs to exactly one category or belongs to none at all. So grading is a
single comparison either way -- `None == None` is a fake correctly spotted, and
needs no special case.

The one thing that comparison cannot express is the difference between "this is
a fake" and "I did not get to it". Both arrive as None, and only the caller
knows which it was, so it passes `assigned` explicitly rather than letting a
missing key stand for an answer.
"""

from uuid import UUID


def grade_item(
    *,
    assigned_category_id: UUID | None,
    correct_category_id: UUID | None,
) -> bool:
    """Is a single answer resolved correctly?

    Both sides are optional and mean the same thing on each: None as the
    correct value marks a fake, None as the assigned value is the player
    calling it one. So a fake spotted grades true, and a fake dropped into a
    category grades false, with no branch between them.
    """
    return assigned_category_id == correct_category_id


def score_assignments(
    *,
    correct_by_item: dict[UUID, UUID | None],
    assigned_by_item: dict[UUID, UUID | None],
) -> dict[UUID, bool]:
    """Grade every answer in the quiz.

    Iterates the answer key rather than the submission, so an answer the player
    never placed counts as wrong rather than being skipped, and an unknown item
    id in the submission cannot inflate the score.

    Membership, not `.get()`, is what decides whether an answer was given.
    Since fakes arrived the two stopped being the same question: a missing key
    and a key holding None both read as None, but one is the player saying
    "fake" and the other is them never touching it. Defaulting would hand a
    point to whoever submits an empty form on a board with fakes in it.
    """
    return {
        item_id: item_id in assigned_by_item
        and grade_item(
            assigned_category_id=assigned_by_item[item_id],
            correct_category_id=correct_category_id,
        )
        for item_id, correct_category_id in correct_by_item.items()
    }
