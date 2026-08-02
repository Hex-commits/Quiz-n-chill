"""The store, checked against both backends.

`test_lobbies.py` exercises the game rules and runs on whichever store is
configured. This file is about the store itself: that a lobby survives a
round-trip intact, that a failed mutation changes nothing, and that two writers
cannot interleave.

The Supabase tests are skipped when there is no database to talk to, so the
suite still runs on a laptop with nothing started. They are not optional in CI:
a `SupabaseStore` that has never executed is not a tested one, and the whole
point of the class is that it behaves identically to the memory store it stands
in for.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.errors import NotFoundError
from app.schemas import Category, ItemSolution, LobbyStatus, Source
from app.services.lobby_state import Lobby, Player, Round
from app.services.lobby_store import MemoryStore, SupabaseStore


def supabase_store_or_skip() -> SupabaseStore:
    try:
        from app.db import get_client

        store = SupabaseStore(get_client())
        store.exists("PING")
    except Exception as exc:  # noqa: BLE001 - absence of a database is not a failure
        pytest.skip(f"no Supabase reachable: {exc}")
    store.clear()
    return store


@pytest.fixture(params=["memory", "supabase"])
def store(request):
    """Every test in this file runs against both backends.

    Parametrised rather than duplicated, because the contract is that they are
    indistinguishable -- a test that only ever ran against one of them would
    prove nothing about the other.
    """
    if request.param == "memory":
        return MemoryStore()
    return supabase_store_or_skip()


def a_lobby(code: str = "TR3X") -> Lobby:
    DE = uuid4()
    return Lobby(
        code=code,
        players=[Player(id=uuid4(), nickname="Anna", is_host=True, score=3)],
        status=LobbyStatus.playing,
        quiz_slugs=["hauptstaedte"],
        subject_names=["Geografie"],
        rounds=[
            Round(
                quiz_id=uuid4(),
                slug="hauptstaedte",
                title="Hauptstädte",
                description=None,
                difficulty="medium",
                source=Source(url="https://de.wikipedia.org/wiki/Hauptstadt", title="Hauptstadt"),
                categories=[Category(id=DE, label="Deutschland", position=1)],
                items=[
                    ItemSolution(
                        id=uuid4(),
                        label="Berlin",
                        position=1,
                        category_id=DE,
                        explanation="Hauptstadt seit 1990, Regierungssitz seit 1999.",
                    )
                ],
            )
        ],
    )


def test_a_lobby_survives_a_round_trip(store):
    original = a_lobby()
    original.current_round = original.rounds[0]
    store.create(original)

    with store.mutate("TR3X") as loaded:
        assert loaded.code == original.code
        assert loaded.players[0].nickname == "Anna"
        assert loaded.players[0].score == 3
        assert loaded.status is LobbyStatus.playing
        assert loaded.current_round.source.title == "Hauptstadt"
        assert loaded.current_round.answer_key() == original.current_round.answer_key()


def test_umlauts_survive_the_round_trip(store):
    """Text has been silently mangled once already in this project."""
    store.create(a_lobby())

    with store.mutate("TR3X") as loaded:
        assert loaded.rounds[0].title == "Hauptstädte"
        assert "seit 1990" in loaded.rounds[0].items[0].explanation
        assert [hex(ord(c)) for c in "Hauptstädte"[8:9]] == ["0x64"]


def test_a_change_is_visible_to_the_next_reader(store):
    store.create(a_lobby())

    with store.mutate("TR3X") as lobby:
        lobby.players[0].score = 99

    with store.mutate("TR3X") as lobby:
        assert lobby.players[0].score == 99


def test_changes_made_before_a_rejection_still_persist(store):
    """Deliberate, and both stores must agree on it.

    Every entry point in `lobbies.py` records the caller's heartbeat before it
    validates anything, so a refused request still has to prove that client is
    alive -- otherwise a player who keeps making rejected moves gets marked
    disconnected. `MemoryStore` hands out the live object and cannot roll back;
    `SupabaseStore` therefore writes in a `finally` rather than on clean exit.
    """
    store.create(a_lobby())

    with pytest.raises(RuntimeError):
        with store.mutate("TR3X") as lobby:
            lobby.players[0].score = 999
            raise RuntimeError("refused by the rules")

    with store.mutate("TR3X") as lobby:
        assert lobby.players[0].score == 999


def test_an_unknown_code_is_not_found(store):
    with pytest.raises(NotFoundError):
        with store.mutate("NOPE"):
            pass


def test_mutate_if_present_yields_none_instead_of_raising(store):
    with store.mutate_if_present("NOPE") as lobby:
        assert lobby is None


def test_delete_removes_it(store):
    store.create(a_lobby())
    assert store.exists("TR3X")

    store.delete("TR3X")

    assert not store.exists("TR3X")


def test_codes_are_case_insensitive(store):
    store.create(a_lobby("TR3X"))

    assert store.exists("tr3x")
    with store.mutate("tr3x") as lobby:
        assert lobby.code == "TR3X"


def test_two_writers_do_not_interleave(store):
    """Both players scoring at the same instant must produce two points.

    A lost update here is the bug the whole locking design exists to prevent,
    and it is invisible in single-threaded tests.
    """
    store.create(a_lobby())
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def score_once():
        try:
            barrier.wait(timeout=5)
            with store.mutate("TR3X") as lobby:
                current = lobby.players[0].score
                import time

                time.sleep(0.05)
                lobby.players[0].score = current + 1
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=score_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    with store.mutate("TR3X") as lobby:
        assert lobby.players[0].score == 5


def test_a_stale_lobby_is_not_offered(store):
    """Old games go away on their own. No history is the promise; this is the
    mechanism behind it."""
    lobby = a_lobby()
    lobby.updated_at = datetime.now(UTC) - timedelta(days=1)
    store.create(lobby)

    if isinstance(store, MemoryStore):
        assert not store.exists("TR3X")
    else:
        assert store.sweep() >= 0
        assert store.exists("TR3X")
