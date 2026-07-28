"""Which origins may call this API.

Vercel gives every preview deployment its own hostname, so the allowed origins
cannot all be known in advance. The pattern covers those. It is worth a test
because CORS fails at the browser rather than at the server -- a wrong policy
looks like a working API that no page can call, and nothing in the logs says so.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings


def client_allowing(origins: str, regex: str = "") -> TestClient:
    settings = Settings(cors_origins=origins, cors_origin_regex=regex)
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def allowed(client: TestClient, origin: str) -> bool:
    response = client.get("/ping", headers={"Origin": origin})
    return response.headers.get("access-control-allow-origin") == origin


PREVIEW = r"^https://quiz-n-chill-[a-z0-9-]+\.vercel\.app$"


def test_a_named_origin_is_allowed():
    client = client_allowing("https://quiz-n-chill.vercel.app")

    assert allowed(client, "https://quiz-n-chill.vercel.app")


def test_an_unnamed_origin_is_refused():
    client = client_allowing("https://quiz-n-chill.vercel.app")

    assert not allowed(client, "https://somewhere-else.example")


def test_a_preview_deployment_is_allowed_by_pattern():
    """The case that motivates the setting: this hostname did not exist when
    the API was configured."""
    client = client_allowing("https://quiz-n-chill.vercel.app", PREVIEW)

    assert allowed(client, "https://quiz-n-chill-git-feature-abc123.vercel.app")


def test_somebody_elses_vercel_project_is_still_refused():
    """The reason the pattern is anchored and prefixed rather than a bare
    `.*\\.vercel\\.app`. With credentials allowed, a loose pattern would let any
    Vercel project call this API as the player."""
    client = client_allowing("https://quiz-n-chill.vercel.app", PREVIEW)

    assert not allowed(client, "https://someone-elses-app.vercel.app")
    assert not allowed(client, "https://quiz-n-chill.vercel.app.evil.example")


def test_no_pattern_means_the_named_list_is_the_whole_policy():
    """Unset must not widen anything -- the default has to be the safe one."""
    client = client_allowing("http://localhost:3000")

    assert allowed(client, "http://localhost:3000")
    assert not allowed(client, "https://quiz-n-chill-git-feature.vercel.app")


@pytest.mark.parametrize(
    "configured, origin",
    [
        ("http://localhost:3000,http://127.0.0.1:3000", "http://127.0.0.1:3000"),
        ("http://localhost:3000, http://127.0.0.1:3000", "http://127.0.0.1:3000"),
    ],
)
def test_the_list_is_split_and_trimmed(configured, origin):
    assert allowed(client_allowing(configured), origin)
