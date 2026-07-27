"""Tests for settings resolution.

The Supabase URL is the one setting with a real trap in it: `.env` holds the
value the *containers* use, and this tool runs on the host. Getting the
precedence wrong means silently talking to the wrong database -- or, with the
old hardcoded rewrite, being unable to talk to a remote one at all.
"""

from __future__ import annotations

import os

import pytest

from tools.ingest.config import ConfigError, Settings, load_dotenv, service_role_key, supabase_url

VARS = ("SUPABASE_URL", "INGEST_SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OLLAMA_URL",
        "INGEST_MODEL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Never inherit the developer's real .env into a test."""
    for name in VARS:
        monkeypatch.delenv(name, raising=False)


# -- the Supabase URL ----------------------------------------------------


def test_the_flag_beats_everything(monkeypatch):
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://from-env:54321")
    monkeypatch.setenv("SUPABASE_URL", "http://from-supabase:54321")

    assert supabase_url("http://from-flag:54321") == "http://from-flag:54321"


def test_the_dedicated_variable_beats_the_container_one(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://host.docker.internal:54321")
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:55000")

    assert supabase_url() == "http://127.0.0.1:55000"


def test_the_container_hostname_is_rewritten_when_falling_back(monkeypatch):
    """`.env` names a host only containers can resolve; this tool is not one."""
    monkeypatch.setenv("SUPABASE_URL", "http://host.docker.internal:54321")

    assert supabase_url() == "http://127.0.0.1:54321"


def test_a_remote_project_is_used_exactly_as_written(monkeypatch):
    """The rewrite must not touch a URL that was never a compose address --
    this is what the old hardcoded replace made impossible."""
    monkeypatch.setenv("INGEST_SUPABASE_URL", "https://abcdefgh.supabase.co")

    assert supabase_url() == "https://abcdefgh.supabase.co"


def test_a_trailing_slash_is_dropped(monkeypatch):
    """Paths get appended to this, so a stray slash means a double slash."""
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:54321/")

    assert supabase_url() == "http://127.0.0.1:54321"


def test_no_url_at_all_says_how_to_fix_it():
    with pytest.raises(ConfigError) as caught:
        supabase_url()

    assert "INGEST_SUPABASE_URL" in str(caught.value)


# -- the rest ------------------------------------------------------------


def test_a_missing_service_role_key_says_where_to_find_it():
    with pytest.raises(ConfigError) as caught:
        service_role_key()

    assert "service_role" in str(caught.value)


def test_settings_fall_back_to_the_documented_defaults(monkeypatch):
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    settings = Settings.resolve()

    assert settings.ollama_url == "http://localhost:11435"
    assert settings.model == "glm4:9b"


def test_flags_beat_the_environment_for_every_setting(monkeypatch):
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://from-env:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setenv("OLLAMA_URL", "http://from-env:11435")
    monkeypatch.setenv("INGEST_MODEL", "from-env")

    settings = Settings.resolve(
        supabase_url_override="http://flag:54321",
        ollama_url="http://flag:11435",
        model="flag-model",
    )

    assert settings.supabase_url == "http://flag:54321"
    assert settings.ollama_url == "http://flag:11435"
    assert settings.model == "flag-model"


# -- the .env reader -----------------------------------------------------


def test_an_exported_value_wins_over_the_file(monkeypatch, tmp_path):
    """Exporting a variable for one run must not mean editing .env."""
    monkeypatch.setenv("INGEST_MODEL", "exported")
    env_file = tmp_path / ".env"
    env_file.write_text("INGEST_MODEL=from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert os.environ["INGEST_MODEL"] == "exported"


def test_comments_and_blank_lines_are_ignored(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\n\nINGEST_MODEL=from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert os.environ["INGEST_MODEL"] == "from-file"


def test_a_missing_file_is_not_an_error(tmp_path):
    load_dotenv(tmp_path / "nope.env")  # must not raise


# -- console encoding ----------------------------------------------------


def test_the_console_is_switched_to_utf8(monkeypatch):
    """A cp1252 console raises UnicodeEncodeError on a title like
    `Seiin Kōkō Danshi Volley-bu`, killing a run hours in over one character in
    a heading. German Wikipedia is full of transliterated titles."""
    from tools.ingest.cli import _speak_utf8

    calls = []

    class FakeStream:
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("tools.ingest.cli.sys.stdout", FakeStream())
    monkeypatch.setattr("tools.ingest.cli.sys.stderr", FakeStream())

    _speak_utf8()

    assert calls == [{"encoding": "utf-8", "errors": "replace"}] * 2


def test_a_stream_that_cannot_be_reconfigured_is_not_fatal(monkeypatch):
    """Under pytest capture or a pipe, stdout may not support it at all."""
    from tools.ingest.cli import _speak_utf8

    class Awkward:
        def reconfigure(self, **_kwargs):
            raise ValueError("nope")

    monkeypatch.setattr("tools.ingest.cli.sys.stdout", Awkward())
    monkeypatch.setattr("tools.ingest.cli.sys.stderr", object())

    _speak_utf8()  # must not raise
