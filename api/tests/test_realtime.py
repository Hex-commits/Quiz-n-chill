"""The change notification, and the promises it makes.

Two of these matter more than the rest: the payload must never carry the answer
key, and a failed publish must never fail the move that triggered it.

The first used to be trivially true -- the payload was a version number. Now
that the state travels with the message it is a property that has to be tested,
because it is the same redaction the HTTP view depends on and a mistake in it
would hand every listener the solution.
"""

from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.schemas import LobbyView
from app.services import lobbies, realtime
from tests.test_lobbies import DE, make_round


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


def a_view(**overrides) -> LobbyView:
    return LobbyView(code="TR3X", status="lobby", version=7, **overrides)


def test_the_channel_is_the_lobby_code(monkeypatch):
    assert realtime.channel_for("tr3x") == "lobby:TR3X"


def test_nothing_is_published_when_it_is_switched_off(monkeypatch):
    monkeypatch.setenv("REALTIME_BROADCAST", "false")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(realtime.httpx, "post", lambda *a, **k: sent.append(k))

    assert realtime.publish(a_view()) is False
    assert sent == []


def test_nothing_is_published_without_credentials(monkeypatch):
    monkeypatch.setenv("REALTIME_BROADCAST", "true")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(realtime.httpx, "post", lambda *a, **k: sent.append(k))

    assert realtime.publish(a_view()) is False
    assert sent == []


class _Response:
    def raise_for_status(self):
        return None


def capture(monkeypatch) -> dict:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setattr(realtime.httpx, "post", fake_post)
    return captured


def test_the_payload_carries_the_state_and_its_version(monkeypatch):
    enable(monkeypatch)
    captured = capture(monkeypatch)

    assert realtime.publish(a_view()) is True

    message = captured["json"]["messages"][0]
    assert message["topic"] == "lobby:TR3X"
    assert message["payload"]["version"] == 7
    # Sent whole, so a client can render it without asking for anything.
    assert message["payload"]["state"]["code"] == "TR3X"
    assert captured["url"].endswith("/realtime/v1/api/broadcast")


def test_the_broadcast_never_carries_an_unplaced_answer(monkeypatch):
    """The security property, now that the message is a delivery rather than a
    doorbell. What goes out is the same redacted view the API serves: an answer
    still in the pool must not name its category, and no explanation may appear
    before the round is over."""
    enable(monkeypatch)
    # The round is stubbed the same way test_lobbies stubs it, so this runs
    # without a database and the answer key is known here.
    monkeypatch.setattr(lobbies, "_load_round", make_round)
    monkeypatch.setattr(lobbies, "_subject_names", lambda slugs: list(slugs))
    monkeypatch.setattr(
        lobbies,
        "pools_by_subject",
        lambda slugs, difficulties=None: {s: [s] for s in slugs},
    )
    monkeypatch.setattr(
        lobbies,
        "draw_balanced",
        lambda pools, count, avoid=frozenset(): sorted(pools)[:count],
    )

    code, anna = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1)

    captured = capture(monkeypatch)
    berlin = next(
        item.id
        for item in lobbies.get_view(code).round_view.remaining_items
        if item.label == "Berlin"
    )
    lobbies.submit_turn(code, anna, berlin, DE)

    state = captured["json"]["messages"][0]["payload"]["state"]
    round_view = state["round_view"]

    # Berlin is placed, so it may name its category. Nothing still in the pool
    # may, and no reason may appear before the round is over.
    assert [solved["label"] for solved in round_view["solved_items"]] == ["Berlin"]
    assert [item["label"] for item in round_view["remaining_items"]] == [
        "Paris",
        "Madrid",
        "Rom",
    ]
    for remaining in round_view["remaining_items"]:
        assert "category_id" not in remaining
    assert "Hauptstadt" not in json.dumps(state)
    assert ben is not None


def test_an_oversized_view_falls_back_to_the_doorbell(monkeypatch):
    """A long game's view grows an answer key per finished round. Past the
    ceiling the version goes out alone and the client fetches, which is what
    this did for every message before."""
    enable(monkeypatch)
    captured = capture(monkeypatch)
    monkeypatch.setattr(realtime, "MAX_PAYLOAD_BYTES", 10)

    assert realtime.publish(a_view()) is True

    payload = captured["json"]["messages"][0]["payload"]
    assert payload == {"version": 7}


def test_a_broken_realtime_does_not_raise(monkeypatch):
    enable(monkeypatch)

    def explode(*args, **kwargs):
        raise OSError("realtime is down")

    monkeypatch.setattr(realtime.httpx, "post", explode)

    assert realtime.publish(a_view()) is False


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
    published: list[LobbyView] = []
    monkeypatch.setattr(realtime, "publish", published.append)

    code, _host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    assert len(published) == 1
    assert published[0].code == code


def test_a_poll_that_changes_nothing_announces_nothing(monkeypatch):
    """The entire point of the exercise. If an idle poll still published, the
    chatter this replaces would simply move to a different channel."""
    enable(monkeypatch)
    code, host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    published: list[LobbyView] = []
    monkeypatch.setattr(realtime, "publish", published.append)

    lobbies.get_view(code, host)
    lobbies.get_view(code, host)
    lobbies.get_view(code, host)

    assert published == []
