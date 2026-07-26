from fastapi import APIRouter, Query

from app.schemas import CheckRequest, CheckResult, QuizDetail, QuizSummary, Subject
from app.services import quizzes as service

router = APIRouter(tags=["quizzes"])


@router.get("/subjects", response_model=list[Subject])
def list_subjects() -> list[Subject]:
    """Quiz-pool areas a game can be drawn from, with how many questions each
    holds."""
    return service.list_subjects()


@router.get("/quizzes", response_model=list[QuizSummary])
def list_quizzes(
    subject: list[str] | None = Query(default=None, description="Filter by subject slug."),
) -> list[QuizSummary]:
    return service.list_quizzes(subject)


@router.get("/quizzes/{quiz_ref}", response_model=QuizDetail)
def get_quiz(quiz_ref: str) -> QuizDetail:
    """One topic, addressable by slug or id.

    Items come back shuffled and without their category -- see `app.schemas`.
    """
    return service.get_quiz(quiz_ref)


@router.post("/quizzes/{quiz_ref}/check", response_model=CheckResult)
def check_assignment(quiz_ref: str, payload: CheckRequest) -> CheckResult:
    """Grade an assignment and return the solution.

    Stateless: no attempt, player or score is written to the database.
    """
    return service.check_assignment(quiz_ref, payload.assignments)
