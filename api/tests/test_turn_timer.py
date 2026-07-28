"""The per-turn clock.

Every player gets a fixed number of seconds to place one answer. The countdown
is drawn by the client, but the deadline is the server's -- a client that lies
about its clock, or never reports back, must not be able to hold a turn open.

Timing out costs the round, exactly as a wrong answer does. That is the harsher
of the two options and it is deliberate: if running down the clock were free,
waiting would always be safer than guessing, and a table of cautious players
would never finish a round.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.errors import ConflictError
from app.schemas import LobbyStart, LobbyStatus
from app.services import lobbies

from tests.test_lobbies import DE, ES, FR, items_of, make_round  # noqa: F401
from tests.test_lobbies import clean_store  # noqa: F401  -- the autouse fixture


def setup_game():
    """A lobby with two players that has *not* started.

    `test_lobbies.setup_game` starts one for you, which is no use here -- these
    tests need to choose the clock at start time.
    """
    code, host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")
    return code, (host, ben)


def start_with(code, host, seconds):
    return lobbies.start_game(code, host, ["topic-a", "topic-b"], 2, seconds)


def expire_the_turn(code):
    """Backdate the deadline, as if the player had sat there doing nothing."""
    with lobbies.edit(code) as lobby:
        lobby.turn_expires_at = datetime.now(UTC) - timedelta(seconds=1)


# -- the clock is running -------------------------------------------------


def test_a_turn_starts_with_the_configured_time():
    code, (anna, _ben) = setup_game()
    view = start_with(code, anna, 45)

    assert view.turn_seconds == 45
    assert view.turn_seconds_left is not None
    assert 0 < view.turn_seconds_left <= 45


def test_the_default_is_used_when_the_host_does_not_choose():
    code, (anna, _ben) = setup_game()

    view = lobbies.start_game(code, anna, ["topic-a"], 1)

    assert view.turn_seconds == LobbyStart.model_fields["turn_seconds"].default


def test_the_clock_resets_when_the_turn_moves():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)
    items = items_of(code)

    # Wind Anna's clock most of the way down, then let her answer.
    with lobbies.edit(code) as lobby:
        lobby.turn_expires_at = datetime.now(UTC) + timedelta(seconds=2)

    view = lobbies.submit_turn(code, anna, items["Berlin"], DE)

    assert view.current_player_id == ben
    # Ben gets a whole turn, not the two seconds left on Anna's.
    assert view.turn_seconds_left > 2


def test_nobody_on_the_clock_means_no_countdown():
    """The waiting room, before anyone is on the clock."""
    code, (anna, _ben) = setup_game()

    view = lobbies.get_view(code, anna)

    assert view.turn_seconds_left is None
    assert view.turn_seconds is None


# -- running out ----------------------------------------------------------


def test_running_out_of_time_passes_the_turn_on():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)

    expire_the_turn(code)
    view = lobbies.get_view(code, ben)

    assert view.current_player_id == ben


def test_running_out_of_time_costs_the_round():
    """The same consequence as a wrong answer, and for the same reason: a turn
    that can be run down for free is one nobody would ever take."""
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)

    expire_the_turn(code)
    view = lobbies.get_view(code, ben)

    out = next(p for p in view.players if p.id == anna)
    assert not out.is_active
    assert out.score == 0


def test_the_table_is_told_who_ran_out():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)

    expire_the_turn(code)
    view = lobbies.get_view(code, ben)

    assert view.timed_out == "Anna"


def test_a_real_move_clears_the_timeout_notice():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)
    expire_the_turn(code)
    lobbies.get_view(code, ben)
    items = items_of(code)

    view = lobbies.submit_turn(code, ben, items["Berlin"], DE)

    assert view.timed_out is None


def test_a_timed_out_player_cannot_then_play():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)
    items = items_of(code)

    expire_the_turn(code)
    lobbies.get_view(code, ben)

    with pytest.raises(ConflictError, match="out for this round"):
        lobbies.submit_turn(code, anna, items["Berlin"], DE)


def test_everyone_timing_out_ends_the_round():
    """The property that matters: the clock guarantees a round terminates even
    if nobody ever answers."""
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)

    for _ in range(2):
        expire_the_turn(code)
        view = lobbies.get_view(code, anna)

    assert view.status is LobbyStatus.reviewing


def test_the_clock_does_not_run_during_a_review():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    view = lobbies.submit_turn(code, anna, items["Madrid"], ES)

    assert view.status is LobbyStatus.reviewing
    assert view.turn_seconds_left is None


def test_the_new_round_starts_the_clock_again():
    code, (anna, ben) = setup_game()
    start_with(code, anna, 30)
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)

    view = lobbies.skip_review(code, anna)

    assert view.status is LobbyStatus.playing
    assert view.turn_seconds_left is not None


# -- the bounds -----------------------------------------------------------


@pytest.mark.parametrize("seconds", [9, 121, 0, -5])
def test_the_host_cannot_ask_for_an_unplayable_clock(seconds):
    """Below ten seconds nobody can read a board; above two minutes it stops
    being a timer. Bounded at the schema so the service never sees one."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LobbyStart(player_id=DE, subject_slugs=["x"], turn_seconds=seconds)


@pytest.mark.parametrize("seconds", [10, 30, 120])
def test_the_sensible_range_is_accepted(seconds):
    assert LobbyStart(
        player_id=DE, subject_slugs=["x"], turn_seconds=seconds
    ).turn_seconds == seconds
