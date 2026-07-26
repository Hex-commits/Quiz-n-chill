"""Reading topics and grading assignments.

Services return Pydantic models and raise `AppError` subclasses. They never
import FastAPI, so they can be unit tested without a request context.

Nothing here writes a row about who played or how they did -- `check_assignment`
grades and returns, and that is the end of it.
"""

import random
from uuid import UUID

from app.db import get_client
from app.errors import ConflictError, NotFoundError
from app.schemas import (
    Assignment,
    Category,
    CheckResult,
    ItemPublic,
    ItemResult,
    ItemSolution,
    QuizCreate,
    QuizDetail,
    QuizSummary,
)
from app.services.scoring import score_assignments

QUIZ_COLUMNS = "id, slug, title, description, created_at"
CATEGORY_COLUMNS = "id, label, position"
ITEM_SOLUTION_COLUMNS = "id, label, position, category_id"


def list_quizzes() -> list[QuizSummary]:
    response = (
        get_client()
        .table("quizzes")
        .select(f"{QUIZ_COLUMNS}, categories(count), items(count)")
        .order("created_at")
        .execute()
    )
    return [
        QuizSummary(
            **{k: v for k, v in row.items() if k not in ("categories", "items")},
            category_count=_embedded_count(row, "categories"),
            item_count=_embedded_count(row, "items"),
        )
        for row in response.data
    ]


def get_quiz(quiz_ref: str) -> QuizDetail:
    """Player-facing payload: categories in order, items shuffled and answerless."""
    row = _fetch_quiz_row(quiz_ref)
    categories, items = _fetch_parts(UUID(row["id"]))

    shuffled = list(items)
    # Seeded items are stored grouped by category, so the stored order would
    # give the grouping away. Shuffle before it ever leaves the server.
    random.shuffle(shuffled)

    return QuizDetail(
        **row,
        categories=[Category(**c) for c in categories],
        items=[ItemPublic(id=item["id"], label=item["label"]) for item in shuffled],
    )


def get_quiz_solution(quiz_ref: str) -> tuple[dict, list[Category], list[ItemSolution]]:
    """Server-side view of a topic, including every item's category.

    Only for callers that need the answer key -- grading, and the lobby game
    loop. Never hand the result to a router that serves players.
    """
    row = _fetch_quiz_row(quiz_ref)
    categories, items = _fetch_parts(UUID(row["id"]))
    return row, [Category(**c) for c in categories], [ItemSolution(**i) for i in items]


def check_assignment(quiz_ref: str, assignments: list[Assignment]) -> CheckResult:
    """Grade a submitted assignment. Stateless -- nothing is persisted."""
    row = _fetch_quiz_row(quiz_ref)
    quiz_id = UUID(row["id"])
    categories, items = _fetch_parts(quiz_id)
    if not items:
        raise ConflictError("This topic has no items to grade.")

    valid_category_ids = {UUID(c["id"]) for c in categories}
    assigned_by_item: dict[UUID, UUID | None] = {}
    for assignment in assignments:
        if (
            assignment.category_id is not None
            and assignment.category_id not in valid_category_ids
        ):
            raise ConflictError(
                f"Category '{assignment.category_id}' does not belong to this topic."
            )
        assigned_by_item[assignment.item_id] = assignment.category_id

    solutions = [ItemSolution(**item) for item in items]
    correct_by_item = {item.id: item.category_id for item in solutions}
    verdicts = score_assignments(
        correct_by_item=correct_by_item,
        assigned_by_item=assigned_by_item,
    )

    results = [
        ItemResult(
            item_id=item.id,
            label=item.label,
            assigned_category_id=assigned_by_item.get(item.id),
            correct_category_id=item.category_id,
            is_fake=item.category_id is None,
            is_correct=verdicts[item.id],
        )
        for item in solutions
    ]

    return CheckResult(
        quiz_id=quiz_id,
        score=sum(1 for result in results if result.is_correct),
        max_score=len(results),
        results=results,
    )


def create_quiz(payload: QuizCreate) -> QuizSummary:
    existing = (
        get_client().table("quizzes").select("id").eq("slug", payload.slug).limit(1).execute()
    )
    if existing.data:
        raise ConflictError(f"A topic with slug '{payload.slug}' already exists.")

    response = get_client().table("quizzes").insert(payload.model_dump(mode="json")).execute()
    return QuizSummary(**response.data[0])


def _fetch_quiz_row(quiz_ref: str) -> dict:
    query = get_client().table("quizzes").select(QUIZ_COLUMNS)
    query = query.eq("id", quiz_ref) if _looks_like_uuid(quiz_ref) else query.eq("slug", quiz_ref)

    response = query.limit(1).execute()
    if not response.data:
        raise NotFoundError(f"No topic found for '{quiz_ref}'.")
    return response.data[0]


def _fetch_parts(quiz_id: UUID) -> tuple[list[dict], list[dict]]:
    categories = (
        get_client()
        .table("categories")
        .select(CATEGORY_COLUMNS)
        .eq("quiz_id", str(quiz_id))
        .order("position")
        .execute()
    ).data
    items = (
        get_client()
        .table("items")
        .select(ITEM_SOLUTION_COLUMNS)
        .eq("quiz_id", str(quiz_id))
        .order("position")
        .execute()
    ).data
    return categories, items


def _embedded_count(row: dict, key: str) -> int:
    counts = row.get(key) or []
    return counts[0]["count"] if counts else 0


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
