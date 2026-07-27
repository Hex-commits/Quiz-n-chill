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
    Source,
    Subject,
)
from app.services.scoring import score_assignments

# Two column sets on purpose. `QUIZ_COLUMNS` is what a player may see while
# playing; the source lives only in `QUIZ_SOLUTION_COLUMNS`, alongside the answer
# key, because a link to the source article is a link to the answers.
QUIZ_COLUMNS = "id, slug, title, description, difficulty, created_at"
QUIZ_SOLUTION_COLUMNS = f"{QUIZ_COLUMNS}, source_url, source_title"
QUIZ_WITH_SUBJECT = f"{QUIZ_COLUMNS}, subjects(slug, name)"
SUBJECT_COLUMNS = "id, slug, name, description, position"
CATEGORY_COLUMNS = "id, label, position"
# `explanation` gives the answer away, exactly like `source_url`, so it lives
# only in the solution column list -- never in what `get_quiz` serves.
ITEM_SOLUTION_COLUMNS = "id, label, position, category_id, explanation"


def list_subjects() -> list[Subject]:
    response = (
        get_client()
        .table("subjects")
        .select(f"{SUBJECT_COLUMNS}, quizzes(count)")
        .order("position")
        .execute()
    )
    return [
        Subject(
            **{k: v for k, v in row.items() if k != "quizzes"},
            quiz_count=_embedded_count(row, "quizzes"),
        )
        for row in response.data
    ]


def list_quizzes(subject_slugs: list[str] | None = None) -> list[QuizSummary]:
    # PostgREST filters on an embedded resource by nulling the embed out, not by
    # dropping the parent row -- so a plain `subjects.slug=in.(...)` returns every
    # quiz with `subjects: null`. The `!inner` hint makes it a real inner join.
    embed = "subjects!inner(slug, name)" if subject_slugs else "subjects(slug, name)"
    query = (
        get_client()
        .table("quizzes")
        .select(f"{QUIZ_COLUMNS}, {embed}, categories(count), items(count)")
    )
    if subject_slugs:
        query = query.in_("subjects.slug", subject_slugs)

    response = query.order("created_at").execute()
    return [_to_summary(row) for row in response.data]


def pools_by_subject(subject_slugs: list[str]) -> dict[str, list[str]]:
    """Available question slugs per subject, for the balanced draw.

    Subjects that exist but hold no questions are dropped; a subject slug that
    does not exist at all is reported, because silently playing a shorter game
    than the host asked for is worse than an error.
    """
    response = (
        get_client()
        .table("subjects")
        .select("slug, quizzes(slug)")
        .in_("slug", subject_slugs)
        .execute()
    )

    found = {row["slug"] for row in response.data}
    missing = [slug for slug in subject_slugs if slug not in found]
    if missing:
        raise NotFoundError(f"Unknown subject(s): {', '.join(sorted(missing))}.")

    pools = {
        row["slug"]: [quiz["slug"] for quiz in (row.get("quizzes") or [])]
        for row in response.data
    }
    return {slug: quizzes for slug, quizzes in pools.items() if quizzes}


def _to_summary(row: dict) -> QuizSummary:
    subject = row.get("subjects") or {}
    return QuizSummary(
        **{k: v for k, v in row.items() if k not in ("categories", "items", "subjects")},
        subject_slug=subject.get("slug"),
        subject_name=subject.get("name"),
        category_count=_embedded_count(row, "categories"),
        item_count=_embedded_count(row, "items"),
    )


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
    row = _fetch_quiz_row(quiz_ref, with_source=True)
    categories, items = _fetch_parts(UUID(row["id"]))
    return row, [Category(**c) for c in categories], [ItemSolution(**i) for i in items]


def source_of(row: dict) -> Source | None:
    """Build a `Source` from a solution row, or None when the question has none."""
    url = row.get("source_url")
    return Source(url=url, title=row.get("source_title")) if url else None


def check_assignment(quiz_ref: str, assignments: list[Assignment]) -> CheckResult:
    """Grade a submitted assignment. Stateless -- nothing is persisted."""
    row = _fetch_quiz_row(quiz_ref, with_source=True)
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
            is_correct=verdicts[item.id],
            explanation=item.explanation,
        )
        for item in solutions
    ]

    return CheckResult(
        quiz_id=quiz_id,
        score=sum(1 for result in results if result.is_correct),
        max_score=len(results),
        difficulty=row["difficulty"],
        source=source_of(row),
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


def _fetch_quiz_row(quiz_ref: str, *, with_source: bool = False) -> dict:
    """Fetch one quiz row. `with_source` is opt-in so the default is the safe one."""
    columns = QUIZ_SOLUTION_COLUMNS if with_source else QUIZ_COLUMNS
    query = get_client().table("quizzes").select(columns)
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
