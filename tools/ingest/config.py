"""Where the tool gets its settings.

One layer of precedence, the same everywhere: **command line > environment >
repo-root `.env` > default.** The `.env` reader uses `setdefault`, so anything
already exported wins over the file -- matching how the API's settings behave.

The Supabase URL is the one setting that genuinely needs two values. `.env` sets
`SUPABASE_URL` for the *containers*, where the Supabase stack is reachable as
`host.docker.internal`. This tool runs on the host, where that name usually does
not resolve. So there is a dedicated override:

    SUPABASE_URL          http://host.docker.internal:54321   (containers)
    INGEST_SUPABASE_URL   http://127.0.0.1:54321              (this tool)

If the override is unset the tool falls back to `SUPABASE_URL` and swaps
`host.docker.internal` for `127.0.0.1`. That fallback is a convenience for the
default compose setup, not a rule -- point `INGEST_SUPABASE_URL` at a remote
project, a second local stack or a tunnel and it is used exactly as written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OLLAMA_URL = "http://localhost:11435"
DEFAULT_MODEL = "glm4:9b"

# Only applied to the fallback, and only for the hostname compose injects.
CONTAINER_HOST = "host.docker.internal"
LOCALHOST = "127.0.0.1"


class ConfigError(RuntimeError):
    """A setting is missing or unusable. Carries the fix in its message."""


def load_dotenv(path: Path | None = None) -> None:
    """Read the repo-root `.env` without adding a dependency.

    Values already in the environment win, so exporting a variable for one run
    does not mean editing the file.
    """
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def supabase_url(override: str | None = None) -> str:
    """The Supabase URL as reachable from *this process*.

    `override` is the `--supabase-url` flag and beats everything.
    """
    if override:
        return override.rstrip("/")

    configured = os.environ.get("INGEST_SUPABASE_URL")
    if configured:
        return configured.rstrip("/")

    base = os.environ.get("SUPABASE_URL")
    if not base:
        raise ConfigError(
            "No Supabase URL. Set INGEST_SUPABASE_URL (or SUPABASE_URL) in the "
            "repo-root .env, or pass --supabase-url."
        )
    # The compose value names a host only containers can resolve.
    return base.replace(CONTAINER_HOST, LOCALHOST).rstrip("/")


def service_role_key(override: str | None = None) -> str:
    """The service-role key for whichever project the URL names.

    Overridable for the same reason the URL is, and it matters more: the key and
    the URL have to describe the *same* project. Filling a hosted project from
    this machine means pointing the URL at it and passing its key in the same
    breath -- with only the URL overridable, that run would reach for the local
    stack's key and fail against production, or worse, succeed against the wrong
    one.
    """
    if override:
        return override

    configured = os.environ.get("INGEST_SUPABASE_SERVICE_ROLE_KEY")
    if configured:
        return configured

    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise ConfigError(
            "No service-role key. Set SUPABASE_SERVICE_ROLE_KEY in the repo-root "
            "`.env` for the local stack (`npm run db:start` prints it as "
            '"service_role key"), or INGEST_SUPABASE_SERVICE_ROLE_KEY / '
            "--supabase-key to fill a hosted project."
        )
    return key


def is_local(url: str) -> bool:
    """Does this URL name a stack on this machine?

    Used to say out loud when a run is about to write somewhere permanent.
    """
    return any(host in url for host in ("127.0.0.1", "localhost", CONTAINER_HOST))


@dataclass(frozen=True)
class Settings:
    """Everything resolved, so the run loop never reads the environment."""

    supabase_url: str
    supabase_key: str
    ollama_url: str
    model: str

    @classmethod
    def resolve(
        cls,
        *,
        supabase_url_override: str | None = None,
        supabase_key_override: str | None = None,
        ollama_url: str | None = None,
        model: str | None = None,
    ) -> Settings:
        return cls(
            supabase_url=supabase_url(supabase_url_override),
            supabase_key=service_role_key(supabase_key_override),
            ollama_url=(
                ollama_url or os.environ.get("OLLAMA_URL") or DEFAULT_OLLAMA_URL
            ).rstrip("/"),
            model=model or os.environ.get("INGEST_MODEL") or DEFAULT_MODEL,
        )
