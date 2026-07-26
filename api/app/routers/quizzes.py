from fastapi import APIRouter

from app.schemas import CheckRequest, CheckResult, QuizDetail, QuizSummary
from app.services import quizzes as service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.get("", response_model=list[QuizSummary])
def list_quizzes() -> list[QuizSummary]:
    return service.list_quizzes()


@router.get("/{quiz_ref}", response_model=QuizDetail)
def get_quiz(quiz_ref: str) -> QuizDetail:
    """One topic, addressable by slug or id.

    Items come back shuffled and without their category -- see `app.schemas`.
    """
    return service.get_quiz(quiz_ref)


@router.post("/{quiz_ref}/check", response_model=CheckResult)
def check_assignment(quiz_ref: str, payload: CheckRequest) -> CheckResult:
    """Grade an assignment and return the solution.

    Stateless: no attempt, player or score is written to the database.
    """
    return service.check_assignment(quiz_ref, payload.assignments)
