"""Game-loop tests.

The topic loader is stubbed so these run without a database: the rules are what
is under test, not PostgREST.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas import Category, ItemSolution, LobbyStatus
from app.services import lobbies

DE, FR = uuid4(), uuid4()


def make_round(slug: str):
    """Two categories, two real items and one fake."""
    return lobbies.Round(
        quiz_id=uuid4(),
        slug=slug,
        title=slug.title(),
        description=None,
        categories=[
            Category(id=DE, label="Deutschland", position=1),
            Category(id=FR, label="Frankreich", position=2),
        ],
        items=[
            ItemSolution(id=uuid4(), label="Berlin", position=1, category_id=DE),
            ItemSolution(id=uuid4(), label="Paris", position=2, category_id=FR),
            ItemSolution(id=uuid4(), label="Barcelona", position=3, category_id=None),
        ],
    )


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    lobbies._reset_store_for_tests()
    monkeypatch.setattr(lobbies, "_load_round", make_round)


def setup_game(nicknames=("Anna", "Ben"), slugs=("topic-a",)):
    code, host_id = lobbies.create_lobby(nicknames[0])
    ids = [host_id] + [lobbies.join_lobby(code, name) for name in nicknames[1:]]
    lobbies.start_game(code, host_id, list(slugs))
    return code, ids


def items_of(code):
    view = lobbies.get_view(code)
    return {item.label: item.id for item in view.round_view.remaining_items}


def test_turn_passes_to_the_next_player_after_a_correct_answer():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    view = lobbies.submit_turn(code, anna, items["Berlin"], DE)

    assert view.current_player_id == ben
    assert view.players[0].score == 1
    assert view.players[0].is_active


def test_turn_also_passes_after_a_wrong_answer():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    view = lobbies.submit_turn(code, anna, items["Berlin"], FR)

    assert view.current_player_id == ben
    assert view.players[0].score == 0
    assert not view.players[0].is_active


def test_a_knocked_out_player_is_skipped_and_cannot_play():
    code, (anna, ben, cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], FR)  # Anna out
    view = lobbies.submit_turn(code, ben, items["Paris"], FR)  # Ben correct

    # Cem is next, and the cursor skips Anna on the way round again.
    assert view.current_player_id == cem
    with pytest.raises(ConflictError, match="out for this round"):
        lobbies.submit_turn(code, anna, items["Barcelona"], None)


def test_playing_out_of_turn_is_rejected():
    code, (_anna, ben) = setup_game()
    items = items_of(code)

    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.submit_turn(code, ben, items["Berlin"], DE)


def test_spotting_a_fake_scores_a_point():
    code, (anna, _ben) = setup_game()
    items = items_of(code)

    view = lobbies.submit_turn(code, anna, items["Barcelona"], None)

    assert view.players[0].score == 1
    assert [s.label for s in view.round_view.solved_items] == ["Barcelona"]


def test_calling_a_real_item_a_fake_knocks_you_out():
    code, (anna, _ben) = setup_game()
    items = items_of(code)

    view = lobbies.submit_turn(code, anna, items["Berlin"], None)

    assert view.players[0].score == 0
    assert not view.players[0].is_active


def test_a_solved_item_cannot_be_played_again():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    with pytest.raises(ConflictError, match="already been placed"):
        lobbies.submit_turn(code, ben, items["Berlin"], DE)


def test_round_ends_when_every_item_is_placed():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    view = lobbies.submit_turn(code, anna, items["Barcelona"], None)

    assert view.round_index == 1
    assert view.status is LobbyStatus.playing
    # Fresh round: nothing solved, everyone back in.
    assert view.round_view.solved_items == []
    assert all(player.is_active for player in view.players)


def test_round_ends_when_nobody_is_active():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], FR)  # wrong, Anna out
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out

    assert view.round_index == 1
    assert all(player.is_active for player in view.players)


def test_the_last_active_player_keeps_going_alone():
    """Knocking everyone else out does not end the round while items remain."""
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna 1
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out

    # Paris is still unplaced and Anna is still in, so play continues with her.
    assert view.status is LobbyStatus.playing
    assert view.current_player_id == anna


def test_game_finishes_after_the_last_round_and_names_a_winner():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna 1
    lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out
    lobbies.submit_turn(code, anna, items["Barcelona"], None)  # Anna 2
    view = lobbies.submit_turn(code, anna, items["Paris"], FR)  # Anna 3, all placed

    assert view.status is LobbyStatus.finished
    assert view.round_view is None
    assert view.winner_ids == [anna]


def test_a_draw_reports_every_tied_player():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna 1
    lobbies.submit_turn(code, ben, items["Paris"], FR)  # Ben 1
    lobbies.submit_turn(code, anna, items["Barcelona"], DE)  # wrong, Anna out
    view = lobbies.submit_turn(code, ben, items["Barcelona"], DE)  # wrong, Ben out

    # Nobody left active, so the round -- and the game -- ends at 1 apiece.
    assert view.status is LobbyStatus.finished
    assert sorted(view.winner_ids, key=str) == sorted([anna, ben], key=str)


def test_scores_carry_across_rounds():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    first = items_of(code)

    lobbies.submit_turn(code, anna, first["Berlin"], DE)
    lobbies.submit_turn(code, ben, first["Paris"], FR)
    lobbies.submit_turn(code, anna, first["Barcelona"], None)

    second = items_of(code)
    view = lobbies.submit_turn(code, ben, second["Berlin"], DE)

    scores = {player.nickname: player.score for player in view.players}
    assert scores == {"Anna": 2, "Ben": 2}


def test_the_lobby_view_never_leaks_an_unsolved_answer():
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)

    view = lobbies.get_view(code)
    payload = view.model_dump_json()

    # Berlin is solved, so its category is fair game. Paris and Barcelona are
    # not placed yet and must carry nothing that hints at the answer.
    assert [item.label for item in view.round_view.remaining_items] == ["Paris", "Barcelona"]
    assert all(not hasattr(item, "category_id") for item in view.round_view.remaining_items)
    assert payload.count(str(FR)) == 1  # only as a category definition


def test_unknown_item_is_rejected():
    code, (anna, _ben) = setup_game()

    with pytest.raises(ValidationError, match="does not belong to this topic"):
        lobbies.submit_turn(code, anna, uuid4(), DE)


def test_foreign_category_is_rejected():
    code, (anna, _ben) = setup_game()
    items = items_of(code)

    with pytest.raises(ValidationError, match="category does not belong"):
        lobbies.submit_turn(code, anna, items["Berlin"], uuid4())


def test_a_game_needs_at_least_two_players():
    code, host_id = lobbies.create_lobby("Solo")

    with pytest.raises(ConflictError, match="At least two players"):
        lobbies.start_game(code, host_id, ["topic-a"])


def test_only_the_host_can_start():
    code, _host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    with pytest.raises(ConflictError, match="Only the host"):
        lobbies.start_game(code, ben, ["topic-a"])


def test_duplicate_nicknames_are_rejected():
    code, _host = lobbies.create_lobby("Anna")

    with pytest.raises(ConflictError, match="already taken"):
        lobbies.join_lobby(code, "anna")


def test_cannot_join_a_running_game():
    code, _ids = setup_game()

    with pytest.raises(ConflictError, match="already started"):
        lobbies.join_lobby(code, "Latecomer")


# ---------------------------------------------------------------------------
# Leaving
# ---------------------------------------------------------------------------


def test_leaving_the_waiting_room_removes_the_player():
    code, _host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    view = lobbies.leave_lobby(code, ben)

    assert [player.nickname for player in view.players] == ["Anna"]


def test_the_host_role_moves_when_the_host_leaves():
    code, anna = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    view = lobbies.leave_lobby(code, anna)

    assert [p.nickname for p in view.players if p.is_host] == ["Ben"]
    # The promoted host can actually start a game.
    lobbies.join_lobby(code, "Cem")
    lobbies.start_game(code, ben, ["topic-a"])


def test_the_last_player_leaving_discards_the_lobby():
    code, anna = lobbies.create_lobby("Anna")

    assert lobbies.leave_lobby(code, anna) is None
    with pytest.raises(NotFoundError, match="No lobby"):
        lobbies.get_view(code)


def test_leaving_on_your_turn_passes_the_turn_on():
    code, (anna, ben, _cem) = setup_game(("Anna", "Ben", "Cem"))

    view = lobbies.leave_lobby(code, anna)  # Anna was first

    assert view.current_player_id == ben
    assert [player.nickname for player in view.players] == ["Ben", "Cem"]


def test_leaving_out_of_turn_leaves_the_clock_alone():
    """The player before the current one leaving must not steal the turn.

    This is the case the position-based cursor got wrong: removing Anna shifts
    Ben from index 1 to 0, so a cursor left at 1 would point at Cem.
    """
    code, (anna, ben, _cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # now Ben's turn

    view = lobbies.leave_lobby(code, anna)

    assert view.current_player_id == ben


def test_leaving_skips_knocked_out_players_when_passing_the_turn():
    code, (anna, ben, cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna correct
    lobbies.submit_turn(code, ben, items["Paris"], DE)  # Ben wrong, out
    # Cem is now on the clock; when Cem leaves the turn must skip Ben.

    view = lobbies.leave_lobby(code, cem)

    assert view.current_player_id == anna


def test_the_last_active_player_leaving_ends_the_round():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)  # Ben correct
    lobbies.submit_turn(code, anna, items["Barcelona"], DE)  # Anna wrong, out

    view = lobbies.leave_lobby(code, ben)  # only active player walks out

    # Round could not continue, so it advanced and Anna is back in.
    assert view.round_index == 1
    assert view.players[0].is_active


def test_leaving_can_finish_the_game_outright():
    code, (anna, ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], DE)  # Ben wrong, out

    view = lobbies.leave_lobby(code, anna)  # last active player leaves

    assert view.status is LobbyStatus.finished
    assert view.winner_ids == [ben]


def test_a_departed_player_cannot_play():
    code, (anna, _ben, _cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.leave_lobby(code, anna)

    with pytest.raises(NotFoundError, match="not in this lobby"):
        lobbies.submit_turn(code, anna, items["Berlin"], DE)


# ---------------------------------------------------------------------------
# Presence: closing a tab, and coming back
# ---------------------------------------------------------------------------


def go_silent(code, *player_ids):
    """Backdate last_seen so the player looks like a closed tab."""
    lobby = lobbies._lobbies[code]
    stale = datetime.now(UTC) - lobbies.PRESENCE_TIMEOUT - timedelta(seconds=1)
    for player in lobby.players:
        if player.id in player_ids:
            player.last_seen = stale


def test_a_silent_client_is_reported_disconnected():
    code, (anna, _ben) = setup_game()
    go_silent(code, anna)

    view = lobbies.get_view(code)

    assert [p.is_connected for p in view.players] == [False, True]


def test_polling_keeps_a_player_connected():
    code, (anna, _ben) = setup_game()
    go_silent(code, anna)

    # Anna's own poll is her heartbeat.
    view = lobbies.get_view(code, anna)

    assert view.players[0].is_connected


def test_a_disconnected_player_does_not_hold_the_turn():
    """The stall case: nobody submits, so only a read can move the clock."""
    code, (anna, ben) = setup_game()
    assert lobbies.get_view(code).current_player_id == anna

    go_silent(code, anna)
    view = lobbies.get_view(code, ben)

    assert view.current_player_id == ben


def test_a_disconnected_player_is_skipped_in_rotation():
    code, (anna, ben, cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    go_silent(code, ben)

    view = lobbies.submit_turn(code, anna, items["Berlin"], DE)

    assert view.current_player_id == cem


def test_a_disconnected_player_cannot_play():
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    go_silent(code, anna)
    lobbies.get_view(code)  # the sweep notices Anna is gone

    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.submit_turn(code, anna, items["Berlin"], DE)


def test_everyone_disconnecting_freezes_rather_than_ending_the_game():
    """Otherwise an empty lobby would race through every round to a winner."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    go_silent(code, anna, ben)

    view = lobbies.get_view(code)

    assert view.status is LobbyStatus.playing
    assert view.round_index == 0
    assert view.current_player_id is None


def test_the_game_resumes_when_someone_comes_back():
    code, (anna, ben) = setup_game()
    go_silent(code, anna, ben)
    lobbies.get_view(code)

    view = lobbies.get_view(code, ben)

    assert view.current_player_id == ben


def test_reconnecting_by_nickname_keeps_the_same_seat_and_score():
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna scores 1
    go_silent(code, anna)
    lobbies.get_view(code)

    # A fresh browser has no player id, so it rejoins by name.
    reclaimed = lobbies.join_lobby(code, "Anna")

    assert reclaimed == anna
    view = lobbies.get_view(code)
    anna_view = next(p for p in view.players if p.id == anna)
    assert anna_view.score == 1
    assert anna_view.is_connected


def test_reconnecting_is_case_insensitive():
    code, (anna, _ben) = setup_game()
    go_silent(code, anna)

    assert lobbies.join_lobby(code, "  aNNa ") == anna


def test_a_connected_players_nickname_cannot_be_stolen():
    code, (_anna, _ben) = setup_game()

    with pytest.raises(ConflictError, match="already taken"):
        lobbies.join_lobby(code, "Anna")


def test_a_knocked_out_player_who_reconnects_stays_knocked_out():
    code, (anna, ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], FR)  # wrong, Anna out
    go_silent(code, anna)
    lobbies.get_view(code)

    lobbies.join_lobby(code, "Anna")

    view = lobbies.get_view(code)
    anna_view = next(p for p in view.players if p.id == anna)
    assert anna_view.is_connected
    assert not anna_view.is_active  # still out until the next round
    assert view.current_player_id == ben


def test_any_request_counts_as_proof_of_life_even_a_rejected_one():
    """A client making requests is alive, whatever the request's verdict."""
    code, (anna, ben) = setup_game()
    items = items_of(code)
    go_silent(code, ben)
    lobbies.get_view(code)

    # Ben plays out of turn: refused, but it shows his tab is open.
    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.submit_turn(code, ben, items["Berlin"], DE)

    view = lobbies.get_view(code)
    assert next(p for p in view.players if p.id == ben).is_connected
    assert view.current_player_id == anna  # the turn itself is unaffected


def test_marking_away_moves_the_turn_immediately():
    code, (anna, ben) = setup_game()

    lobbies.mark_away(code, anna)

    view = lobbies.get_view(code)
    assert not view.players[0].is_connected
    assert view.current_player_id == ben


def test_marking_away_on_an_unknown_lobby_is_not_an_error():
    lobbies.mark_away("ZZZZ", uuid4())


def test_reconnecting_after_marking_away_works():
    code, (anna, _ben) = setup_game()
    lobbies.mark_away(code, anna)

    view = lobbies.get_view(code, anna)

    assert view.players[0].is_connected


def test_leaving_frees_a_slot_in_the_waiting_room():
    code, _anna = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")
    lobbies.leave_lobby(code, ben)

    # The nickname is available again because Ben is really gone.
    lobbies.join_lobby(code, "Ben")
