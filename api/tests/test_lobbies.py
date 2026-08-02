"""Game-loop tests.

The topic loader is stubbed so these run without a database: the rules are what
is under test, not PostgREST.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas import Category, ItemSolution, LobbyStatus, Source, TurnSubmit
from app.services import lobbies

DE, FR, ES, IT = uuid4(), uuid4(), uuid4(), uuid4()


def make_round(slug: str):
    """Four categories, one answer each -- a one-to-one pairing.

    Four rather than three so the default two-player game is two whole laps of
    the table. A round now ends on a lap boundary, so a three-pair board would
    end after two placements and every test that plays one out would be
    describing a rule it does not mean to.
    """
    return lobbies.Round(
        quiz_id=uuid4(),
        slug=slug,
        title=slug.title(),
        description=None,
        difficulty="medium",
        source=Source(url=f"https://example.test/{slug}", title=slug.title()),
        categories=[
            Category(id=DE, label="Deutschland", position=1),
            Category(id=FR, label="Frankreich", position=2),
            Category(id=ES, label="Spanien", position=3),
            Category(id=IT, label="Italien", position=4),
        ],
        items=[
            ItemSolution(
                id=uuid4(), label="Berlin", position=1, category_id=DE,
                explanation="Hauptstadt Deutschlands seit 1990.",
            ),
            ItemSolution(
                id=uuid4(), label="Paris", position=2, category_id=FR,
                explanation="Hauptstadt Frankreichs.",
            ),
            ItemSolution(
                id=uuid4(), label="Madrid", position=3, category_id=ES,
                explanation="Hauptstadt Spaniens.",
            ),
            ItemSolution(
                id=uuid4(), label="Rom", position=4, category_id=IT,
                explanation="Hauptstadt Italiens.",
            ),
        ],
    )


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    """Stub out everything that would reach the database.

    `draw_balanced` is replaced with a deterministic passthrough so a test that
    asks for two rounds reliably gets the two it named -- the real draw is
    random by design and is tested separately in test_drafting.py.
    """
    lobbies._reset_store_for_tests()
    monkeypatch.setattr(lobbies, "_load_round", make_round)
    monkeypatch.setattr(lobbies, "_subject_names", lambda slugs: [s.title() for s in slugs])
    monkeypatch.setattr(
        lobbies,
        "pools_by_subject",
        lambda slugs, difficulties=None: {slug: [slug] for slug in slugs},
    )
    monkeypatch.setattr(
        lobbies,
        "draw_balanced",
        lambda pools, count, avoid=frozenset(): sorted(pools)[:count],
    )
    # Only reached when a caller actually excludes something, so most tests never
    # touch it -- but it is a database call and the point of this fixture is that
    # none of them happen.
    monkeypatch.setattr(lobbies, "pair_counts", dict)


def setup_game(nicknames=("Anna", "Ben"), slugs=("topic-a",), round_count=None):
    """Start a game. `round_count` defaults to one round per slug.

    Passing fewer rounds than slugs is how a test gets a settling round: the
    game holds one drawn question back for it, so with every slug spoken for
    there is nothing spare and no settling round can happen.
    """
    code, host_id = lobbies.create_lobby(nicknames[0])
    ids = [host_id] + [lobbies.join_lobby(code, name) for name in nicknames[1:]]
    lobbies.start_game(code, host_id, list(slugs), round_count or len(slugs))
    return code, ids


def items_of(code):
    view = lobbies.get_view(code)
    return {item.label: item.id for item in view.round_view.remaining_items}


def next_round(code, host):
    """Leave the between-rounds review, as the host's button does.

    A round no longer rolls straight into the next one -- it pauses on the
    answers first -- so any test that wants round two has to say so.
    """
    return lobbies.skip_review(code, host)


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
        lobbies.submit_turn(code, anna, items["Madrid"], ES)


def test_the_view_names_who_is_up_next():
    code, (anna, ben) = setup_game()

    view = lobbies.get_view(code)

    assert view.current_player_id == anna
    assert view.next_player_id == ben


def test_nobody_is_up_next_when_only_one_player_can_move():
    """Ben is knocked out, so the turn comes straight back to Anna. Naming her
    as "next" would be true and useless."""
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out

    assert view.current_player_id == anna
    assert view.next_player_id is None


def test_playing_out_of_turn_is_rejected():
    code, (_anna, ben) = setup_game()
    items = items_of(code)

    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.submit_turn(code, ben, items["Berlin"], DE)


def test_a_correct_placement_scores_a_point():
    code, (anna, _ben) = setup_game()
    items = items_of(code)

    view = lobbies.submit_turn(code, anna, items["Madrid"], ES)

    assert view.players[0].score == 1
    assert [s.label for s in view.round_view.solved_items] == ["Madrid"]


def test_a_turn_must_name_a_category():
    """There is no "this one fits nowhere" move any more: a question is a
    one-to-one pairing, so every turn places an answer in some category.

    Guarded at the schema rather than in the service, which is why this asserts
    on `TurnSubmit` -- the router never builds a call without one."""
    with pytest.raises(PydanticValidationError):
        TurnSubmit(player_id=uuid4(), item_id=uuid4(), category_id=None)


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
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    view = lobbies.submit_turn(code, ben, items["Rom"], IT)

    # The round pauses on its answers rather than rolling straight on.
    assert view.status is LobbyStatus.reviewing
    assert view.round_index == 0


def test_the_next_round_begins_after_the_review():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    lobbies.submit_turn(code, ben, items["Rom"], IT)

    view = next_round(code, anna)

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

    # Everyone knocked out is exactly the round worth reading afterwards.
    assert view.status is LobbyStatus.reviewing

    view = next_round(code, anna)
    assert view.round_index == 1
    assert all(player.is_active for player in view.players)


def finish_round_one(code, anna, ben):
    """Play topic-a out so the lobby lands on its review."""
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    return lobbies.submit_turn(code, ben, items["Rom"], IT)


def test_the_review_reveals_the_whole_answer_key_with_explanations():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))

    view = finish_round_one(code, anna, ben)

    solution = view.finished_rounds[0].solution
    assert [(p.category_label, p.item_label) for p in solution] == [
        ("Deutschland", "Berlin"),
        ("Frankreich", "Paris"),
        ("Spanien", "Madrid"),
        ("Italien", "Rom"),
    ]
    assert solution[0].explanation == "Hauptstadt Deutschlands seit 1990."


def test_the_review_includes_pairs_nobody_solved():
    """A round that ended because everyone was knocked out is the one most
    worth reading, so its unsolved pairs must be in the review too."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], FR)  # wrong, Anna out
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out

    solution = view.finished_rounds[0].solution
    assert len(solution) == 4
    assert all(pair.solved_by is None for pair in solution)
    assert {pair.item_label for pair in solution} == {"Berlin", "Paris", "Madrid", "Rom"}


def test_the_review_waits_for_the_host_however_long_it_takes():
    """The point of removing the clock: no amount of polling moves the game on
    while the answers are up. Only the host's button does."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    finish_round_one(code, anna, ben)

    for _ in range(3):
        view = lobbies.get_view(code, anna)

    assert view.status is LobbyStatus.reviewing
    assert view.round_index == 0

    view = lobbies.skip_review(code, anna)

    assert view.status is LobbyStatus.playing
    assert view.round_index == 1


def test_only_the_host_can_skip_the_review():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    finish_round_one(code, anna, ben)

    with pytest.raises(ConflictError, match="Only the host"):
        lobbies.skip_review(code, ben)


def test_a_review_cannot_be_skipped_while_a_round_is_still_running():
    """Otherwise the host could cut a live board short."""
    code, (anna, _ben) = setup_game(slugs=("topic-a", "topic-b"))

    with pytest.raises(ConflictError, match="no review to skip"):
        lobbies.skip_review(code, anna)


def test_a_turn_cannot_be_played_during_the_review():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    finish_round_one(code, anna, ben)

    with pytest.raises(ConflictError, match="not running"):
        lobbies.submit_turn(code, ben, uuid4(), DE)


def test_the_last_round_goes_straight_to_the_final_scoreboard():
    """There is no next round to pause before, and the finished screen carries
    every round's answers anyway."""
    code, (anna, ben) = setup_game(slugs=("topic-a",))

    view = finish_round_one(code, anna, ben)

    assert view.status is LobbyStatus.finished
    assert view.finished_rounds[0].solution


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
    lobbies.submit_turn(code, anna, items["Madrid"], ES)  # Anna 2
    lobbies.submit_turn(code, anna, items["Paris"], FR)  # Anna 3
    view = lobbies.submit_turn(code, anna, items["Rom"], IT)  # Anna 4, all placed

    assert view.status is LobbyStatus.finished
    assert view.round_view is None
    assert view.winner_ids == [anna]


# -- the settling round -------------------------------------------------------
#
# Four pairs across three players is one lap plus a remainder, so the seat the
# rotation starts on is credited two turns and the other two are credited one.
# That is the whole unfairness these are about: it is handed out by arithmetic
# before anybody has played, and it is settled after the last question rather
# than taxed out of every round.


def play_out(code, order):
    """Place all four pairs correctly, in the given seat order."""
    items = items_of(code)
    for player, (label, category) in zip(
        order, [("Berlin", DE), ("Paris", FR), ("Madrid", ES), ("Rom", IT)]
    ):
        lobbies.submit_turn(code, player, items[label], category)


def test_a_game_that_divides_evenly_has_no_settling_round():
    """Four pairs across two players is two clean laps. Nobody is owed
    anything, so the game ends where it always did."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"), round_count=1)

    play_out(code, [anna, ben, anna, ben])
    view = lobbies.get_view(code)

    assert view.status is LobbyStatus.finished
    assert not view.is_catch_up


def test_the_short_changed_players_get_the_turns_they_were_owed():
    code, (anna, ben, cem) = setup_game(
        ("Anna", "Ben", "Cem"), ("topic-a", "topic-b"), round_count=1
    )

    play_out(code, [anna, ben, cem, anna])

    # The last question is over, but the game is not: it pauses on the answers
    # first, exactly as any other round does.
    view = lobbies.get_view(code)
    assert view.status is LobbyStatus.reviewing

    view = next_round(code, anna)

    assert view.is_catch_up
    # Anna opened the round and so was credited the extra turn. Ben and Cem
    # were each one short, and this is where they get it back.
    assert view.catch_up_left == {ben: 1, cem: 1}
    assert not next(p for p in view.players if p.id == anna).is_active
    assert view.current_player_id in (ben, cem)


def test_the_settling_round_ends_when_the_owed_turns_run_out():
    code, (anna, ben, cem) = setup_game(
        ("Anna", "Ben", "Cem"), ("topic-a", "topic-b"), round_count=1
    )
    play_out(code, [anna, ben, cem, anna])
    view = next_round(code, anna)

    items = items_of(code)
    first = view.current_player_id
    view = lobbies.submit_turn(code, first, items["Berlin"], DE)
    second = view.current_player_id
    view = lobbies.submit_turn(code, second, items["Paris"], FR)

    # Two owed turns, two placements, done -- the rest of the board is not
    # played and Anna never gets a turn in it at all.
    assert view.status is LobbyStatus.finished
    assert {first, second} == {ben, cem}


def test_a_settling_turn_scores_like_any_other():
    code, (anna, ben, cem) = setup_game(
        ("Anna", "Ben", "Cem"), ("topic-a", "topic-b"), round_count=1
    )
    play_out(code, [anna, ben, cem, anna])
    view = next_round(code, anna)

    items = items_of(code)
    first = view.current_player_id
    view = lobbies.submit_turn(code, first, items["Berlin"], DE)

    assert next(p for p in view.players if p.id == first).score == 2


def test_being_knocked_out_earns_no_settling_turns():
    """The distinction the whole ledger exists for. Ben answers wrongly and
    takes no further turns that round -- but that is the rules working, not the
    arithmetic short-changing him, so it buys him nothing at the end."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"), round_count=1)
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], DE)  # wrong, Ben out
    lobbies.submit_turn(code, anna, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    view = lobbies.submit_turn(code, anna, items["Rom"], IT)

    # Anna took four turns to Ben's one, and the game still ends here.
    assert view.status is LobbyStatus.finished
    assert not view.is_catch_up


def test_no_settling_round_without_a_board_to_play_it_on():
    """The spare question is drawn, not required. A pool with nothing left over
    simply ends the game, rather than failing at the last moment."""
    code, (anna, ben, cem) = setup_game(("Anna", "Ben", "Cem"), ("topic-a",))

    play_out(code, [anna, ben, cem, anna])
    view = lobbies.get_view(code)

    assert view.status is LobbyStatus.finished
    assert not view.is_catch_up


def test_a_draw_reports_every_tied_player():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)  # Anna 1
    lobbies.submit_turn(code, ben, items["Paris"], FR)  # Ben 1
    lobbies.submit_turn(code, anna, items["Madrid"], DE)  # wrong, Anna out
    view = lobbies.submit_turn(code, ben, items["Madrid"], DE)  # wrong, Ben out

    # Nobody left active, so the round -- and the game -- ends at 1 apiece.
    assert view.status is LobbyStatus.finished
    assert sorted(view.winner_ids, key=str) == sorted([anna, ben], key=str)


def test_scores_carry_across_rounds():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    first = items_of(code)

    lobbies.submit_turn(code, anna, first["Berlin"], DE)
    lobbies.submit_turn(code, ben, first["Paris"], FR)
    lobbies.submit_turn(code, anna, first["Madrid"], ES)
    lobbies.submit_turn(code, ben, first["Rom"], IT)
    next_round(code, anna)

    second = items_of(code)
    view = lobbies.submit_turn(code, ben, second["Berlin"], DE)

    # Round two starts with Ben, because the starting seat rotates.
    scores = {player.nickname: player.score for player in view.players}
    assert scores == {"Anna": 2, "Ben": 3}


def test_the_lobby_view_never_leaks_an_unsolved_answer():
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)

    view = lobbies.get_view(code)
    payload = view.model_dump_json()

    # Berlin is solved, so its category is fair game. Paris and Madrid are not
    # placed yet and must carry nothing that hints at the answer.
    assert [item.label for item in view.round_view.remaining_items] == [
        "Paris",
        "Madrid",
        "Rom",
    ]
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
    lobbies.submit_turn(code, anna, items["Madrid"], DE)  # Anna wrong, out

    view = lobbies.leave_lobby(code, ben)  # only active player walks out

    # Round could not continue, so it ended -- on its review.
    assert view.status is LobbyStatus.reviewing

    view = next_round(code, anna)
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
    stale = datetime.now(UTC) - lobbies.PRESENCE_TIMEOUT - timedelta(seconds=1)
    with lobbies.edit(code) as lobby:
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


def go_quiet(code, *player_ids):
    """Backdate last_seen past QUIET_AFTER but well inside PRESENCE_TIMEOUT."""
    quiet = datetime.now(UTC) - lobbies.QUIET_AFTER - timedelta(seconds=1)
    with lobbies.edit(code) as lobby:
        for player in lobby.players:
            if player.id in player_ids:
                player.last_seen = quiet


def test_a_responsive_player_is_not_flagged_as_quiet():
    code, _ids = setup_game()

    assert not lobbies.get_view(code).current_player_quiet


def test_the_others_are_told_when_the_active_player_goes_quiet():
    code, (anna, ben) = setup_game()
    go_quiet(code, anna)

    view = lobbies.get_view(code, ben)

    assert view.current_player_quiet
    # Still their turn: this explains the pause, it does not cause a skip.
    assert view.current_player_id == anna


def test_a_quiet_player_can_still_take_their_turn():
    """The flag is advisory -- the grace period is the whole point."""
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    go_quiet(code, anna)

    view = lobbies.submit_turn(code, anna, items["Berlin"], DE)

    assert view.players[0].score == 1


def test_a_quiet_player_going_silent_clears_the_flag_by_skipping():
    code, (anna, ben) = setup_game()
    go_quiet(code, anna)
    assert lobbies.get_view(code, ben).current_player_quiet

    go_silent(code, anna)
    view = lobbies.get_view(code, ben)

    # The turn moved on, so there is nothing left to warn about.
    assert view.current_player_id == ben
    assert not view.current_player_quiet


def test_a_quiet_player_who_checks_in_clears_the_flag():
    code, (anna, ben) = setup_game()
    go_quiet(code, anna)
    assert lobbies.get_view(code, ben).current_player_quiet

    assert not lobbies.get_view(code, anna).current_player_quiet


def test_the_quiet_flag_is_off_in_the_waiting_room():
    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    go_quiet(code, anna)

    assert not lobbies.get_view(code).current_player_quiet


def test_the_source_is_hidden_while_a_round_is_being_played():
    code, _ids = setup_game(slugs=("topic-a", "topic-b"))

    view = lobbies.get_view(code)
    payload = view.model_dump_json()

    assert view.round_view is not None
    assert not hasattr(view.round_view, "source")
    assert view.finished_rounds == []
    assert "example.test" not in payload  # the source URL has not leaked


def test_a_finished_round_publishes_its_source():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    view = lobbies.submit_turn(code, ben, items["Rom"], IT)

    # Round one is over, so its source is now fair game -- round two's is not.
    assert [r.slug for r in view.finished_rounds] == ["topic-a"]
    assert view.finished_rounds[0].source.url == "https://example.test/topic-a"
    assert "example.test/topic-b" not in view.model_dump_json()

    view = next_round(code, anna)
    assert view.round_view.slug == "topic-b"
    assert "example.test/topic-b" not in view.model_dump_json()


def test_restarting_clears_the_published_sources():
    code, (anna, ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    lobbies.submit_turn(code, ben, items["Rom"], IT)
    assert lobbies.get_view(code).finished_rounds

    view = lobbies.reset_to_lobby(code, anna)

    assert view.finished_rounds == []


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


# -- not repeating what this browser has already played ----------------------
#
# The record lives in the client, so it arrives with the request. Two things
# soften it, and both are the point: a question big enough to deal a different
# board every time is never counted as used up, and once nothing new is left the
# played ones come back rather than the game being short.


def test_a_played_question_is_kept_out_of_the_draw(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        lobbies,
        "pools_by_subject",
        lambda slugs, difficulties=None: {"topic-a": ["q1", "q2", "q3"]},
    )
    monkeypatch.setattr(lobbies, "pair_counts", lambda: {"q1": 10, "q2": 10, "q3": 10})

    def spy(pools, count, avoid=frozenset()):
        seen["avoid"] = avoid
        return ["q3"] * count

    monkeypatch.setattr(lobbies, "draw_balanced", spy)

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1, exclude_slugs=["q1", "q2"])

    assert seen["avoid"] == {"q1", "q2"}


def test_a_big_question_is_never_counted_as_played(monkeypatch):
    """It deals a random subset, so the next board is a different one. Retiring
    it would spend the richest questions in the pool first -- the opposite of
    what a "don't repeat things" rule is for."""
    seen = {}
    monkeypatch.setattr(
        lobbies,
        "pools_by_subject",
        lambda slugs, difficulties=None: {"topic-a": ["big", "small"]},
    )
    monkeypatch.setattr(
        lobbies,
        "pair_counts",
        lambda: {"big": lobbies.REPLAYABLE_PAIRS, "small": lobbies.REPLAYABLE_PAIRS - 1},
    )

    def spy(pools, count, avoid=frozenset()):
        seen["avoid"] = avoid
        return ["big"] * count

    monkeypatch.setattr(lobbies, "draw_balanced", spy)

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1, exclude_slugs=["big", "small"])

    assert seen["avoid"] == {"small"}


def test_an_unknown_slug_is_simply_excluded(monkeypatch):
    """A browser's history outlives the questions in it: a slug that has since
    been deleted must not be treated as an enormous question and let through."""
    seen = {}
    monkeypatch.setattr(
        lobbies,
        "pools_by_subject",
        lambda slugs, difficulties=None: {"topic-a": ["q1"]},
    )
    monkeypatch.setattr(lobbies, "pair_counts", dict)

    def spy(pools, count, avoid=frozenset()):
        seen["avoid"] = avoid
        return ["q1"] * count

    monkeypatch.setattr(lobbies, "draw_balanced", spy)

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1, exclude_slugs=["gone"])

    assert seen["avoid"] == {"gone"}


def test_no_exclusions_costs_no_database_call(monkeypatch):
    """The common case -- a first game, or a browser with no history. The count
    query is skipped entirely rather than run and discarded."""
    def boom():
        raise AssertionError("pair_counts must not be called with nothing excluded")

    monkeypatch.setattr(lobbies, "pair_counts", boom)

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    view = lobbies.start_game(code, anna, ["topic-a"], 1)

    assert view.status is LobbyStatus.playing


# -- drawing only the difficulties the host ticked ---------------------------


def test_the_chosen_difficulties_reach_the_pool_query(monkeypatch):
    from app.schemas import Difficulty

    seen = {}

    def spy(slugs, difficulties=None):
        seen["difficulties"] = difficulties
        return {"topic-a": ["q1"]}

    monkeypatch.setattr(lobbies, "pools_by_subject", spy)

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, anna, ["topic-a"], 1, difficulties=[Difficulty.easy])

    assert seen["difficulties"] == [Difficulty.easy]


def test_a_narrowed_pool_that_is_empty_says_which_knob_to_turn(monkeypatch):
    """"No questions" would leave the host guessing between another subject and
    another difficulty. They are fixed differently, so they are named
    differently."""
    from app.schemas import Difficulty

    monkeypatch.setattr(lobbies, "pools_by_subject", lambda slugs, difficulties=None: {})

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    with pytest.raises(ConflictError, match="at that difficulty"):
        lobbies.start_game(code, anna, ["topic-a"], 1, difficulties=[Difficulty.hard])


def test_an_empty_pool_with_every_difficulty_still_blames_the_subjects(monkeypatch):
    from app.schemas import Difficulty

    monkeypatch.setattr(lobbies, "pools_by_subject", lambda slugs, difficulties=None: {})

    code, anna = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")

    with pytest.raises(ConflictError, match="contain no questions"):
        lobbies.start_game(code, anna, ["topic-a"], 1, difficulties=list(Difficulty))


def test_asking_for_no_difficulty_at_all_is_refused():
    """A game with nothing in it. The UI cannot produce this -- unticking the
    last box is refused -- so it is a client bug, and the schema says so."""
    from app.schemas import LobbyStart

    with pytest.raises(PydanticValidationError):
        LobbyStart(player_id=uuid4(), subject_slugs=["geografie"], difficulties=[])
