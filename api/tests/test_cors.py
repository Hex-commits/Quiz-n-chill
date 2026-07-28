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


# -- the defaults that ship, with nothing configured ----------------------
#
# These are what a deploy uses when nobody sets an environment variable, and
# getting them wrong fails only in the browser -- the API answers normally and
# the response is discarded, with nothing in any log to say why. That happened
# once already: production returned "400 Disallowed CORS origin" while the API
# was otherwise perfectly healthy.


def default_client() -> TestClient:
    """Built from the class defaults, not from `Settings()`.

    Instantiating would read the environment and `.env`, which is exactly what a
    deploy with nothing configured does *not* have -- and locally would pick up
    docker-compose's own CORS_ORIGINS, so the test would pass while saying
    nothing about what ships.
    """
    fields = Settings.model_fields
    return client_allowing(
        fields["cors_origins"].default,
        fields["cors_origin_regex"].default,
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://quiz-n-chill-web.vercel.app",
        "https://quiz-n-chill-web-git-feature-hex.vercel.app",
    ],
)
def test_the_shipped_defaults_allow_the_real_frontends(origin):
    assert allowed(default_client(), origin)


@pytest.mark.parametrize(
    "origin",
    [
        "https://someone-elses-app.vercel.app",
        "https://quiz-n-chill-web.vercel.app.evil.example",
        "http://quiz-n-chill-web.vercel.app",  # plain http
        "https://evil.example",
    ],
)
def test_the_shipped_defaults_refuse_everything_else(origin):
    assert not allowed(default_client(), origin)
