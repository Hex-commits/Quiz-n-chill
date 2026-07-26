from fastapi import APIRouter

from app.config import get_settings
from app.db import get_client
from app.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    """Liveness probe that also reports whether Supabase is reachable.

    Always returns 200 -- `database` carries the detail, so a compose healthcheck
    can start the frontend while you are still wiring the database up.
    """
    settings = get_settings()
    try:
        get_client().table("quizzes").select("id").limit(1).execute()
        database = "connected"
    except Exception as exc:  # noqa: BLE001 - surfaced as a status string
        database = f"unavailable: {type(exc).__name__}"

    return HealthStatus(status="ok", environment=settings.environment, database=database)
