from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import AppError
from app.routers import health, lobbies, quizzes

settings = get_settings()

app = FastAPI(
    title="Quiz Quiz API",
    version="0.2.0",
    description=(
        "Zuordnungsfragen: every category takes exactly one answer, and every "
        "answer belongs to exactly one category. All logic lives here; the "
        "Next.js frontend only renders what this returns. The database stores "
        "questions and games in progress -- never a record of who played."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Named origins cover production and local development; the pattern covers
    # hosts whose URL is generated per deployment, which on Vercel is every
    # preview. Left unset it matches nothing, so the named list is the whole
    # policy -- no accidental widening by default.
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.include_router(health.router)
app.include_router(quizzes.router)
app.include_router(lobbies.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "quiz-quiz-api", "docs": "/docs"}
