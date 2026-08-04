"""Game-loop tests.

The topic loader is stubbed so these run without a database: the rules are what
is under test, not PostgREST.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas import (
    Category,
    Difficulty,
    ItemSolution,
    LobbySettings,
    LobbyStatus,
    Source,
    TurnSubmit,
)
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


def next_round(code, asks_first):
    """Leave the between-rounds review, as the players' buttons do.

    A round no longer rolls straight into the next one -- it pauses on the
    answers first, and then on a countdown -- so any test that wants round two
    has to say so. Everyone asks and the countdown is run out, which is the
    shortest way to say "get me to the next round" without describing the vote
    every time. The rule itself is tested below, one condition at a time.
    """
    for player in lobbies.get_view(code).players:
        lobbies.ready_for_next_round(code, player.id)
    expire_the_countdown(code)
    return lobbies.get_view(code, asks_first)


def expire_the_countdown(code):
    """Backdate the countdown, as if the three seconds had passed."""
    with lobbies.edit(code) as lobby:
        lobby.next_round_at = datetime.now(UTC) - timedelta(seconds=1)


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

    lobbies.submit_turn(code, anna, items["Berlin"], FR)
    view = lobbies.submit_turn(code, ben, items["Paris"], FR)

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
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)

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
    assert view.round_view.solved_items == []
    assert all(player.is_active for player in view.players)


def test_round_ends_when_nobody_is_active():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], FR)
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)

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

    lobbies.submit_turn(code, anna, items["Berlin"], FR)
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)

    solution = view.finished_rounds[0].solution
    assert len(solution) == 4
    assert all(pair.solved_by is None for pair in solution)
    assert {pair.item_label for pair in solution} == {"Berlin", "Paris", "Madrid", "Rom"}


def test_the_review_waits_however_long_it_takes():
    """The point of removing the clock: no amount of polling moves the game on
    while the answers are up. Only the players asking does."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    finish_round_one(code, anna, ben)

    for _ in range(3):
        view = lobbies.get_view(code, anna)

    assert view.status is LobbyStatus.reviewing
    assert view.round_index == 0
    assert view.next_round_in is None

    view = next_round(code, anna)

    assert view.status is LobbyStatus.playing
    assert view.round_index == 1


def review_with_three():
    """Three players, sitting on the review after round one.

    Three because two is the one lobby size where every majority is also a
    single vote, and the rule these tests are about would be invisible.
    """
    code, ids = setup_game(("Anna", "Ben", "Cem"), ("topic-a", "topic-b"))
    play_out(code, [ids[0], ids[1], ids[2], ids[0]])
    return code, ids


def test_anybody_can_ask_for_the_next_round():
    """The button is on every screen now, not only the host's."""
    code, (_anna, ben, _cem) = review_with_three()

    view = lobbies.ready_for_next_round(code, ben)

    assert view.ready_ids == [ben]


def test_half_the_players_asking_starts_the_countdown():
    code, (_anna, ben, cem) = review_with_three()

    view = lobbies.ready_for_next_round(code, cem)

    assert view.ready_needed == 2
    assert view.next_round_in is None
    assert view.status is LobbyStatus.reviewing

    view = lobbies.ready_for_next_round(code, ben)

    assert view.next_round_in == 3
    assert view.status is LobbyStatus.reviewing


def test_the_round_begins_when_the_countdown_runs_out():
    """The three seconds are the whole point -- the board must not change under
    a player who is still reading."""
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    finish_round_one(code, anna, ben)

    lobbies.ready_for_next_round(code, anna)
    view = lobbies.get_view(code, ben)

    assert view.status is LobbyStatus.reviewing
    assert view.next_round_in == 3

    expire_the_countdown(code)
    view = lobbies.get_view(code, ben)

    assert view.status is LobbyStatus.playing
    assert view.round_index == 1
    assert view.next_round_in is None


def test_asking_twice_counts_once():
    code, (anna, _ben, _cem) = review_with_three()

    lobbies.ready_for_next_round(code, anna)
    view = lobbies.ready_for_next_round(code, anna)

    assert view.ready_ids == [anna]
    assert view.next_round_in is None


def test_a_player_going_quiet_lowers_the_bar():
    """Cem's tab is gone, so the two who are left are the whole lobby as far as
    the count is concerned -- and Anna's vote already carries it."""
    code, (anna, _ben, cem) = review_with_three()
    lobbies.ready_for_next_round(code, anna)

    view = lobbies.get_view(code, anna)
    assert view.next_round_in is None

    lobbies.mark_away(code, cem)
    view = lobbies.get_view(code, anna)

    assert view.ready_needed == 1
    assert view.next_round_in == 3


def test_a_vote_from_somebody_who_has_since_gone_does_not_count():
    code, (anna, _ben, cem) = review_with_three()
    lobbies.ready_for_next_round(code, cem)

    lobbies.mark_away(code, cem)
    view = lobbies.get_view(code, anna)

    assert view.ready_ids == []
    assert view.next_round_in is None


def test_the_next_review_starts_from_nobody_being_ready():
    code, (anna, ben) = setup_game(("Anna", "Ben"), ("topic-a", "topic-b", "topic-c"))
    finish_round_one(code, anna, ben)
    next_round(code, anna)

    play_out(code, [ben, anna, ben, anna])
    view = lobbies.get_view(code, anna)

    assert view.status is LobbyStatus.reviewing
    assert view.ready_ids == []
    assert view.next_round_in is None


def test_a_round_that_is_still_running_cannot_be_left():
    """Otherwise a player could cut a live board short."""
    code, (anna, _ben) = setup_game(slugs=("topic-a", "topic-b"))

    with pytest.raises(ConflictError, match="no review to leave"):
        lobbies.ready_for_next_round(code, anna)


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

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    view = lobbies.submit_turn(code, ben, items["Paris"], DE)

    assert view.status is LobbyStatus.playing
    assert view.current_player_id == anna


def test_game_finishes_after_the_last_round_and_names_a_winner():
    code, (anna, ben) = setup_game()
    items = items_of(code)

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], DE)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    lobbies.submit_turn(code, anna, items["Paris"], FR)
    view = lobbies.submit_turn(code, anna, items["Rom"], IT)

    assert view.status is LobbyStatus.finished
    assert view.round_view is None
    assert view.winner_ids == [anna]


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

    view = lobbies.get_view(code)
    assert view.status is LobbyStatus.reviewing

    view = next_round(code, anna)

    assert view.is_catch_up
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
    lobbies.submit_turn(code, ben, items["Paris"], DE)
    lobbies.submit_turn(code, anna, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    view = lobbies.submit_turn(code, anna, items["Rom"], IT)

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

    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], DE)
    view = lobbies.submit_turn(code, ben, items["Madrid"], DE)

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

    scores = {player.nickname: player.score for player in view.players}
    assert scores == {"Anna": 2, "Ben": 3}


def test_the_lobby_view_never_leaks_an_unsolved_answer():
    code, (anna, _ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)

    view = lobbies.get_view(code)
    payload = view.model_dump_json()

    assert [item.label for item in view.round_view.remaining_items] == [
        "Paris",
        "Madrid",
        "Rom",
    ]
    assert all(not hasattr(item, "category_id") for item in view.round_view.remaining_items)
    assert payload.count(str(FR)) == 1


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


def test_the_settings_the_host_picks_are_visible_to_everyone():
    code, host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    lobbies.set_settings(
        code,
        host,
        LobbySettings(
            subject_slugs=["geografie", "musik"],
            difficulties=[Difficulty.easy],
            round_count=7,
            turn_seconds=45,
        ),
    )

    view = lobbies.get_view(code, ben)
    assert view.settings.subject_slugs == ["geografie", "musik"]
    assert view.settings.difficulties == [Difficulty.easy]
    assert view.settings.round_count == 7
    assert view.settings.turn_seconds == 45


def test_a_fresh_lobby_reports_the_defaults_rather_than_nothing():
    code, _host = lobbies.create_lobby("Anna")

    settings = lobbies.get_view(code).settings

    assert settings.subject_slugs == []
    assert settings.round_count == 5
    assert settings.turn_seconds == 30
    assert settings.difficulties == list(Difficulty)


def test_only_the_host_can_change_the_settings():
    code, _host = lobbies.create_lobby("Anna")
    ben = lobbies.join_lobby(code, "Ben")

    with pytest.raises(ConflictError, match="Only the host"):
        lobbies.set_settings(code, ben, LobbySettings(round_count=3))


def test_the_settings_are_fixed_once_the_game_is_running():
    code, (anna, _ben) = setup_game()

    with pytest.raises(ConflictError, match="already started"):
        lobbies.set_settings(code, anna, LobbySettings(round_count=3))


def test_starting_records_the_game_that_was_actually_started():
    code, host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.set_settings(code, host, LobbySettings(subject_slugs=["stale"], round_count=9))

    view = lobbies.start_game(code, host, ["topic-a"], 1, 45)

    assert view.settings.subject_slugs == ["topic-a"]
    assert view.settings.round_count == 1
    assert view.settings.turn_seconds == 45


def test_changing_the_settings_moves_the_version_so_others_re_read():
    code, host = lobbies.create_lobby("Anna")
    before = lobbies.get_view(code).version

    after = lobbies.set_settings(code, host, LobbySettings(round_count=3)).version

    assert after > before


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
    lobbies.join_lobby(code, "Cem")
    lobbies.start_game(code, ben, ["topic-a"])


def test_the_last_player_leaving_discards_the_lobby():
    code, anna = lobbies.create_lobby("Anna")

    assert lobbies.leave_lobby(code, anna) is None
    with pytest.raises(NotFoundError, match="No lobby"):
        lobbies.get_view(code)


def test_leaving_on_your_turn_passes_the_turn_on():
    code, (anna, ben, _cem) = setup_game(("Anna", "Ben", "Cem"))

    view = lobbies.leave_lobby(code, anna)

    assert view.current_player_id == ben
    assert [player.nickname for player in view.players] == ["Ben", "Cem"]


def test_leaving_out_of_turn_leaves_the_clock_alone():
    """The player before the current one leaving must not steal the turn.

    This is the case the position-based cursor got wrong: removing Anna shifts
    Ben from index 1 to 0, so a cursor left at 1 would point at Cem.
    """
    code, (anna, ben, _cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)

    view = lobbies.leave_lobby(code, anna)

    assert view.current_player_id == ben


def test_leaving_skips_knocked_out_players_when_passing_the_turn():
    code, (anna, ben, cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], DE)

    view = lobbies.leave_lobby(code, cem)

    assert view.current_player_id == anna


def test_the_last_active_player_leaving_ends_the_round():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], DE)

    view = lobbies.leave_lobby(code, ben)

    assert view.status is LobbyStatus.reviewing

    view = next_round(code, anna)
    assert view.round_index == 1
    assert view.players[0].is_active


def test_leaving_can_finish_the_game_outright():
    code, (anna, ben) = setup_game()
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], DE)

    view = lobbies.leave_lobby(code, anna)

    assert view.status is LobbyStatus.finished
    assert view.winner_ids == [ben]


def test_a_departed_player_cannot_play():
    code, (anna, _ben, _cem) = setup_game(("Anna", "Ben", "Cem"))
    items = items_of(code)
    lobbies.leave_lobby(code, anna)

    with pytest.raises(NotFoundError, match="not in this lobby"):
        lobbies.submit_turn(code, anna, items["Berlin"], DE)


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
    lobbies.get_view(code)

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
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    go_silent(code, anna)
    lobbies.get_view(code)

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
    lobbies.submit_turn(code, anna, items["Berlin"], FR)
    go_silent(code, anna)
    lobbies.get_view(code)

    lobbies.join_lobby(code, "Anna")

    view = lobbies.get_view(code)
    anna_view = next(p for p in view.players if p.id == anna)
    assert anna_view.is_connected
    assert not anna_view.is_active
    assert view.current_player_id == ben


def test_any_request_counts_as_proof_of_life_even_a_rejected_one():
    """A client making requests is alive, whatever the request's verdict."""
    code, (anna, ben) = setup_game()
    items = items_of(code)
    go_silent(code, ben)
    lobbies.get_view(code)

    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.submit_turn(code, ben, items["Berlin"], DE)

    view = lobbies.get_view(code)
    assert next(p for p in view.players if p.id == ben).is_connected
    assert view.current_player_id == anna


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
    assert "example.test" not in payload


def test_a_finished_round_publishes_its_source():
    code, (anna, ben) = setup_game(slugs=("topic-a", "topic-b"))
    items = items_of(code)
    lobbies.submit_turn(code, anna, items["Berlin"], DE)
    lobbies.submit_turn(code, ben, items["Paris"], FR)
    lobbies.submit_turn(code, anna, items["Madrid"], ES)
    view = lobbies.submit_turn(code, ben, items["Rom"], IT)

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

    lobbies.join_lobby(code, "Ben")


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
