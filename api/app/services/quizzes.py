"""Reading topics and grading assignments.

Services return Pydantic models and raise `AppError` subclasses. They never
import FastAPI, so they can be unit tested without a request context.

Nothing here writes a row about who played or how they did -- `check_assignment`
grades and returns, and that is the end of it.
"""

import random
from collections import Counter
from uuid import UUID

from app.db import get_client
from app.errors import ConflictError, NotFoundError
from app.schemas import (
    Assignment,
    Category,
    CategoryKind,
    CheckResult,
    Difficulty,
    ImagePublic,
    ImageSource,
    ItemPublic,
    ItemResult,
    ItemSolution,
    QuizCreate,
    QuizDetail,
    QuizSummary,
    Source,
    Subject,
)
from app.services.images import commons_url
from app.services.scoring import score_assignments

QUIZ_COLUMNS = "id, slug, title, description, difficulty, category_kind, created_at"
QUIZ_SOLUTION_COLUMNS = f"{QUIZ_COLUMNS}, source_url, source_title"
QUIZ_WITH_SUBJECT = f"{QUIZ_COLUMNS}, subjects(slug, name)"
SUBJECT_COLUMNS = "id, slug, name, description, position"
CATEGORY_COLUMNS = (
    "id, label, position, image_file, image_credit, image_licence, image_licence_url"
)
ITEM_SOLUTION_COLUMNS = "id, label, position, category_id, explanation"


def list_subjects() -> list[Subject]:
    response = (
        get_client()
        .table("subjects")
        .select(f"{SUBJECT_COLUMNS}, quizzes(difficulty)")
        .order("position")
        .execute()
    )
    return [
        Subject(
            **{k: v for k, v in row.items() if k != "quizzes"},
            quiz_count=len(row.get("quizzes") or []),
            difficulty_counts=Counter(
                quiz["difficulty"] for quiz in (row.get("quizzes") or [])
            ),
        )
        for row in response.data
    ]


def list_quizzes(subject_slugs: list[str] | None = None) -> list[QuizSummary]:
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


def pools_by_subject(
    subject_slugs: list[str],
    difficulties: list[Difficulty] | None = None,
) -> dict[str, list[str]]:
    """Available question slugs per subject, for the balanced draw.

    Subjects that exist but hold no questions are dropped; a subject slug that
    does not exist at all is reported, because silently playing a shorter game
    than the host asked for is worse than an error.

    `difficulties` narrows the pool to those ratings. None means all of them --
    distinct from an empty list, which no caller should send and which would
    correctly yield nothing.

    Filtered here in Python rather than in the query: PostgREST applies a
    condition on an embedded resource by nulling the embed out rather than
    dropping the parent row, so the obvious `quizzes.difficulty=in.(...)` returns
    every subject with `quizzes: null` and an empty pool. `!inner` fixes that but
    then also drops subjects whose questions are all filtered away -- which is
    information the caller wants to keep, since it is the difference between
    "that subject is empty" and "that subject has nothing at this difficulty".
    The pool is small enough that the distinction is worth more than the bytes.
    """
    response = (
        get_client()
        .table("subjects")
        .select("slug, quizzes(slug, difficulty)")
        .in_("slug", subject_slugs)
        .execute()
    )

    found = {row["slug"] for row in response.data}
    missing = [slug for slug in subject_slugs if slug not in found]
    if missing:
        raise NotFoundError(f"Unknown subject(s): {', '.join(sorted(missing))}.")

    wanted = None if difficulties is None else {str(d) for d in difficulties}
    pools = {
        row["slug"]: [
            quiz["slug"]
            for quiz in (row.get("quizzes") or [])
            if wanted is None or quiz.get("difficulty") in wanted
        ]
        for row in response.data
    }
    return {slug: quizzes for slug, quizzes in pools.items() if quizzes}


def pair_counts() -> dict[str, int]:
    """How many pairs each question holds, by slug.

    Used to decide which questions are worth replaying: one holding far more
    pairs than a board deals is a different board every time it comes up, so
    "already played" means much less for it. See `_replayable` in `lobbies`.

    Counts categories, not items. Since fakes came back the two differ by
    however many a question carries, and counting items would credit every
    question with two pairs it does not have -- pushing the ones sitting just
    under the replay threshold over it.
    """
    rows = get_client().table("quizzes").select("slug, categories(count)").execute().data
    return {row["slug"]: _embedded_count(row, "categories") for row in rows}


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
    random.shuffle(shuffled)

    hide_names = row.get("category_kind") == CategoryKind.image
    return QuizDetail(
        **row,
        categories=[public_category(c, hide_name=hide_names) for c in categories],
        items=[ItemPublic(id=item["id"], label=item["label"]) for item in shuffled],
    )


def get_quiz_solution(quiz_ref: str) -> tuple[dict, list[Category], list[ItemSolution]]:
    """Server-side view of a topic, including every item's category.

    Only for callers that need the answer key -- grading, and the lobby game
    loop. Never hand the result to a router that serves players.
    """
    row = _fetch_quiz_row(quiz_ref, with_source=True)
    categories, items = _fetch_parts(UUID(row["id"]))
    return (
        row,
        [public_category(c) for c in categories],
        [item_solution(i) for i in items],
    )


def public_category(row: dict, *, hide_name: bool = False) -> Category:
    """One category, with its photograph if it has one.

    The picture and the credit under it always travel together, which is what
    the licence requires. The *name* is withheld while a picture question is
    being played: "Albert Bridge" printed above a photograph of the Albert
    Bridge answers the question the photograph was chosen to ask.
    """
    source = image_of(row)
    return Category(
        id=row["id"],
        label=None if hide_name else row["label"],
        position=row["position"],
        image=(
            ImagePublic(
                src=commons_url(source.file),
                credit=source.credit,
                licence=source.licence,
                licence_url=source.licence_url,
            )
            if source
            else None
        ),
    )


def item_solution(row: dict) -> ItemSolution:
    """Server-side view of one answer, including the category it belongs to.

    A null `category_id` on the row is a fake and stays null here; nothing
    downstream may show it before the round is over.
    """
    return ItemSolution(
        id=row["id"],
        label=row["label"],
        position=row["position"],
        category_id=row["category_id"],
        explanation=row.get("explanation"),
    )


def image_of(row: dict) -> ImageSource | None:
    """The picture on a category row, or None when it has none.

    The four columns are flat in the database and nested above it on purpose: a
    picture without its licence cannot legally be rendered, so the two travel
    together everywhere above this line. The table's
    `categories_image_is_complete` constraint is the other half of that promise.
    """
    file = row.get("image_file")
    licence = row.get("image_licence")
    if not file or not licence:
        return None
    return ImageSource(
        file=file,
        credit=row.get("image_credit"),
        licence=licence,
        licence_url=row.get("image_licence_url"),
    )


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

    solutions = [item_solution(item) for item in items]
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
