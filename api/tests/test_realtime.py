"""The change notification, and the promises it makes.

Two of these matter more than the rest: the payload must never carry game
state, and a failed publish must never fail the move that triggered it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.config import get_settings
from app.services import lobbies, realtime


@pytest.fixture(autouse=True)
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def enable(monkeypatch):
    monkeypatch.setenv("REALTIME_BROADCAST", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    get_settings.cache_clear()


def test_the_channel_is_the_lobby_code(monkeypatch):
    assert realtime.channel_for("tr3x") == "lobby:TR3X"


def test_nothing_is_published_when_it_is_switched_off(monkeypatch):
    monkeypatch.setenv("REALTIME_BROADCAST", "false")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(realtime.httpx, "post", lambda *a, **k: sent.append(k))

    assert realtime.publish("TR3X", 4) is False
    assert sent == []


def test_nothing_is_published_without_credentials(monkeypatch):
    monkeypatch.setenv("REALTIME_BROADCAST", "true")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(realtime.httpx, "post", lambda *a, **k: sent.append(k))

    assert realtime.publish("TR3X", 4) is False
    assert sent == []


class _Response:
    def raise_for_status(self):
        return None


def test_the_payload_carries_a_version_and_nothing_else(monkeypatch):
    """The security property. The lobby holds `category_id` and `explanation`
    for every answer -- the whole solution -- so the notification must be a
    doorbell, not a delivery."""
    enable(monkeypatch)
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setattr(realtime.httpx, "post", fake_post)

    assert realtime.publish("TR3X", 7) is True

    message = captured["json"]["messages"][0]
    assert message["topic"] == "lobby:TR3X"
    assert message["payload"] == {"version": 7}
    # Nothing that could name an answer, a category or a player.
    assert set(message["payload"]) == {"version"}
    assert captured["url"].endswith("/realtime/v1/api/broadcast")


def test_a_broken_realtime_does_not_raise(monkeypatch):
    enable(monkeypatch)

    def explode(*args, **kwargs):
        raise OSError("realtime is down")

    monkeypatch.setattr(realtime.httpx, "post", explode)

    assert realtime.publish("TR3X", 7) is False


def test_a_broken_realtime_does_not_fail_the_move(monkeypatch):
    """The property that matters in a game: a player's turn is accepted even
    when nobody can be told about it. The slow poll is the backstop."""
    enable(monkeypatch)
    monkeypatch.setattr(
        realtime.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
    )

    code, host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    view = lobbies.get_view(code, host)
    assert {p.nickname for p in view.players} == {"Anna", "Ben"}
    assert ben is not None


def test_a_change_announces_once(monkeypatch):
    enable(monkeypatch)
    published: list[tuple[str, int]] = []
    monkeypatch.setattr(realtime, "publish", lambda code, version: published.append((code, version)))

    code, _host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    assert len(published) == 1
    assert published[0][0] == code


def test_a_poll_that_changes_nothing_announces_nothing(monkeypatch):
    """The entire point of the exercise. If an idle poll still published, the
    chatter this replaces would simply move to a different channel."""
    enable(monkeypatch)
    code, host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    published: list[tuple[str, int]] = []
    monkeypatch.setattr(realtime, "publish", lambda code, version: published.append((code, version)))

    lobbies.get_view(code, host)
    lobbies.get_view(code, host)
    lobbies.get_view(code, host)

    assert published == []
