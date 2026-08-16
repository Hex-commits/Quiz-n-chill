"""Tests for settings resolution.

The Supabase URL is the one setting with a real trap in it: `.env` holds the
value the *containers* use, and this tool runs on the host. Getting the
precedence wrong means silently talking to the wrong database -- or, with the
old hardcoded rewrite, being unable to talk to a remote one at all.

`INGEST_VET` and `INGEST_JUDGE_MODEL` describe the machine rather than the run,
so they are environment-only by design and there is nothing on the command line
to override them with. The tests for them go through the environment alone.
"""

from __future__ import annotations

import os

import pytest

from tools.ingest.config import (
    ConfigError,
    Settings,
    is_local,
    load_dotenv,
    service_role_key,
    supabase_url,
)

VARS = ("SUPABASE_URL", "INGEST_SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
        "INGEST_SUPABASE_SERVICE_ROLE_KEY", "OLLAMA_URL", "INGEST_MODEL",
        "INGEST_VET", "INGEST_JUDGE_MODEL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Never inherit the developer's real .env into a test."""
    for name in VARS:
        monkeypatch.delenv(name, raising=False)



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



def test_a_missing_service_role_key_says_where_to_find_it():
    with pytest.raises(ConfigError) as caught:
        service_role_key()

    assert "service_role" in str(caught.value)



def test_the_key_flag_beats_everything(monkeypatch):
    monkeypatch.setenv("INGEST_SUPABASE_SERVICE_ROLE_KEY", "from-env")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "local-stack")

    assert service_role_key("from-flag") == "from-flag"


def test_the_dedicated_key_beats_the_local_stack_one(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "local-stack")
    monkeypatch.setenv("INGEST_SUPABASE_SERVICE_ROLE_KEY", "hosted-project")

    assert service_role_key() == "hosted-project"


def test_the_url_and_the_key_can_be_overridden_together(monkeypatch):
    """The point of the pair: filling a hosted project from this machine must
    not reach for the local stack's key."""
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "local-stack")

    settings = Settings.resolve(
        supabase_url_override="https://abc.supabase.co",
        supabase_key_override="hosted-key",
    )

    assert settings.supabase_url == "https://abc.supabase.co"
    assert settings.supabase_key == "hosted-key"


@pytest.mark.parametrize(
    "url, local",
    [
        ("http://127.0.0.1:54321", True),
        ("http://localhost:54321", True),
        ("http://host.docker.internal:54321", True),
        ("https://abcdefgh.supabase.co", False),
    ],
)
def test_a_remote_project_is_recognised_as_remote(url, local):
    """Drives the [REMOTE PROJECT] marker in the run header."""
    assert is_local(url) is local


def test_settings_fall_back_to_the_documented_defaults(monkeypatch):
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    settings = Settings.resolve()

    assert settings.ollama_url == "http://localhost:11435"
    # Spelled out rather than compared against the constant, so that changing the
    # default model is a deliberate edit to this line and not a silent pass. The
    # quantisation suffix is part of the identity: the bare `gemma4:e4b` tag is a
    # different, much larger download.
    assert settings.model == "gemma4:e4b-it-q4_K_M"


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
    load_dotenv(tmp_path / "nope.env")



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

    _speak_utf8()


@pytest.fixture
def resolvable(monkeypatch):
    """Enough for `Settings.resolve()` to get as far as the settings under test."""
    monkeypatch.setenv("INGEST_SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


def test_vetting_is_off_unless_asked_for(monkeypatch, resolvable):
    monkeypatch.delenv("INGEST_VET", raising=False)
    assert Settings.resolve().vet is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " true "])
def test_the_ways_of_saying_yes(monkeypatch, resolvable, raw):
    monkeypatch.setenv("INGEST_VET", raw)
    assert Settings.resolve().vet is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "maybe"])
def test_anything_else_is_off(monkeypatch, resolvable, raw):
    """A typo has to read as off. The asymmetry is deliberate for a setting that
    costs a model call per candidate."""
    monkeypatch.setenv("INGEST_VET", raw)
    assert Settings.resolve().vet is False


def test_the_judge_defaults_to_the_run_model(monkeypatch, resolvable):
    """Not to the package default -- setting INGEST_MODEL alone should still
    give one consistent model rather than silently two."""
    monkeypatch.delenv("INGEST_JUDGE_MODEL", raising=False)
    monkeypatch.setenv("INGEST_MODEL", "llama3:8b")

    settings = Settings.resolve()

    assert settings.model == "llama3:8b"
    assert settings.judge_model == "llama3:8b"


def test_the_judge_can_be_a_different_model(monkeypatch, resolvable):
    monkeypatch.setenv("INGEST_MODEL", "gemma4:12b")
    monkeypatch.setenv("INGEST_JUDGE_MODEL", "qwen2.5:14b")

    settings = Settings.resolve()

    assert (settings.model, settings.judge_model) == ("gemma4:12b", "qwen2.5:14b")
