# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements are copied on their own so the dependency layer is only rebuilt
# when they actually change, not on every source edit.
COPY requirements.txt requirements-dev.txt ./


# --- development -----------------------------------------------------------
# Includes pytest/ruff and runs uvicorn with --reload. Source is bind-mounted
# by compose, so edits are picked up without a rebuild.
FROM base AS development

RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# --- production ------------------------------------------------------------
# Only used if you deploy the API as a container (Fly.io, Render, Railway).
# Vercel builds from `vercel.json` instead and ignores this file.
FROM base AS production

RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
