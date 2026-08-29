"""Poker-mode tests: the betting, the staged reveal, and who takes the pot.

The topic loader is stubbed exactly as in `test_lobbies.py`, so none of this
touches a database. What is *not* stubbed is the shuffle: the deck and the
question are random by design, so every test below reads the table for what it
was dealt rather than assuming it.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import ConflictError, ValidationError
from app.main import app
from app.schemas import Category, GameMode, ItemSolution, PokerAction, PokerStage
from app.services import lobbies, poker

DE, FR, ES, IT = uuid4(), uuid4(), uuid4(), uuid4()


def make_round(slug: str):
    return lobbies.Round(
        quiz_id=uuid4(),
        slug=slug,
        title="Flüsse in Europa",
        description=None,
        subject_name="Geografie",
        difficulty="medium",
        categories=[
            Category(id=DE, label="Deutschland", position=1),
            Category(id=FR, label="Frankreich", position=2),
            Category(id=ES, label="Spanien", position=3),
            Category(id=IT, label="Italien", position=4),
        ],
        items=[
            ItemSolution(id=uuid4(), label="Berlin", position=1, category_id=DE,
                         explanation="Hauptstadt Deutschlands."),
            ItemSolution(id=uuid4(), label="Paris", position=2, category_id=FR),
            ItemSolution(id=uuid4(), label="Madrid", position=3, category_id=ES),
            ItemSolution(id=uuid4(), label="Rom", position=4, category_id=IT),
        ],
    )


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
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


def setup_poker(nicknames=("Anna", "Ben"), hands=1):
    """A poker game, with one question drawn per hand."""
    code, host_id = lobbies.create_lobby(nicknames[0])
    ids = [host_id] + [lobbies.join_lobby(code, name) for name in nicknames[1:]]
    slugs = [f"topic-{n}" for n in range(hands)]
    lobbies.start_game(code, host_id, slugs, hands, mode=GameMode.poker)
    return code, ids


def view(code, player_id=None):
    return lobbies.get_view(code, player_id).poker


def seat_of(code, player_id):
    return next(s for s in view(code).seats if s.player_id == player_id)


def answer_key(code):
    """The right answers to the hand in play, read off the table's own state."""
    with lobbies.edit(code) as lobby:
        asked = lobby.poker.question_category_id
        return [i.id for i in lobby.current_round.items if i.category_id == asked]


def a_wrong_answer(code):
    right = set(answer_key(code))
    return next(item.id for item in view(code).options if item.id not in right)


def settle_bets(code):
    """Everyone checks or calls until this street closes. The cheapest way on."""
    street = view(code).stage
    while True:
        table = view(code)
        if table.to_act is None or table.stage is not street:
            return table
        seat = next(s for s in table.seats if s.player_id == table.to_act)
        action = (
            PokerAction.check
            if seat.committed == table.current_bet
            else PokerAction.call
        )
        lobbies.poker_act(code, table.to_act, action)


BETTING = (
    PokerStage.preflop,
    PokerStage.flop,
    PokerStage.turn,
    PokerStage.river,
)


def deal_to_the_question(code):
    """Play the hand out to the point where it can be answered."""
    while view(code).stage in BETTING:
        settle_bets(code)
    return view(code)


def expire(code, field):
    with lobbies.edit(code) as lobby:
        setattr(lobby.poker, field, datetime.now(UTC) - timedelta(seconds=1))


# ---------------------------------------------------------------------------
# Dealing and the staged reveal
# ---------------------------------------------------------------------------


def test_a_hand_opens_with_blinds_up_and_two_cards_each():
    code, (anna, ben) = setup_poker()

    table = view(code)
    assert table.stage is PokerStage.preflop
    assert table.pot == poker.SMALL_BLIND + poker.BIG_BLIND
    assert all(seat.has_cards for seat in table.seats)
    assert {seat.stack for seat in table.seats} == {
        poker.STARTING_STACK - poker.SMALL_BLIND,
        poker.STARTING_STACK - poker.BIG_BLIND,
    }
    assert len(lobbies.poker_hand(code, anna).cards) == 2
    assert len(lobbies.poker_hand(code, ben).cards) == 2


def test_the_two_cards_are_the_players_own_and_reach_nobody_else():
    """The safety property the whole per-player endpoint exists for."""
    code, (anna, ben) = setup_poker()

    payload = lobbies.get_view(code, anna).model_dump_json()
    for card in lobbies.poker_hand(code, anna).cards:
        # Quoted: "9c" is also two hex digits, and would match inside a uuid.
        assert f'"{card}"' not in payload

    assert lobbies.poker_hand(code, anna).cards != lobbies.poker_hand(code, ben).cards


def test_the_question_is_revealed_one_card_at_a_time():
    code, _ids = setup_poker()

    assert view(code).subject_name is None
    assert view(code).title is None

    settle_bets(code)
    flop = view(code)
    assert flop.stage is PokerStage.flop
    assert len(flop.board) == 3
    assert flop.subject_name == "Geografie"
    assert flop.title is None
    assert flop.question is None

    settle_bets(code)
    turn = view(code)
    assert turn.stage is PokerStage.turn
    assert len(turn.board) == 4
    assert turn.title == "Flüsse in Europa"
    assert turn.question is None
    assert turn.options == []

    settle_bets(code)
    river = view(code)
    assert river.stage is PokerStage.river
    assert len(river.board) == 5
    assert river.question is not None
    assert river.options == []

    settle_bets(code)
    asked = view(code)
    assert asked.stage is PokerStage.answering
    assert asked.question is not None
    assert len(asked.options) == 4


def test_nothing_of_the_question_leaks_before_its_card_turns_over():
    code, (anna, _ben) = setup_poker()

    payload = lobbies.get_view(code, anna).model_dump_json()

    for label in ("Berlin", "Paris", "Madrid", "Rom", "Deutschland", "Flüsse"):
        assert label not in payload


def test_the_answers_stay_off_the_table_while_the_last_bet_is_made():
    """The river asks. What it does not do is list what the answer might be."""
    code, _ids = setup_poker()
    while view(code).stage is not PokerStage.river:
        settle_bets(code)

    river = view(code)
    payload = lobbies.get_view(code).model_dump_json()
    assert river.question is not None
    assert river.options == []
    for label in ("Berlin", "Paris", "Madrid", "Rom"):
        assert f'"{label}"' not in payload

    settle_bets(code)
    assert len(view(code).options) == 4


def test_the_answers_are_offered_in_one_fixed_order():
    code, _ids = setup_poker()
    deal_to_the_question(code)

    assert [item.id for item in view(code).options] == [
        item.id for item in view(code).options
    ]


# ---------------------------------------------------------------------------
# Betting
# ---------------------------------------------------------------------------


def test_a_raise_has_to_be_called_before_the_street_closes():
    code, _ids = setup_poker()

    first = view(code).to_act
    lobbies.poker_act(code, first, PokerAction.raise_to, poker.BIG_BLIND * 3)

    table = view(code)
    assert table.stage is PokerStage.preflop
    assert table.current_bet == poker.BIG_BLIND * 3
    assert table.to_act is not None and table.to_act != first


def test_a_raise_below_the_minimum_is_refused():
    code, _ids = setup_poker()

    with pytest.raises(ValidationError, match="at least"):
        lobbies.poker_act(
            code, view(code).to_act, PokerAction.raise_to, poker.BIG_BLIND + 1
        )


def test_checking_a_bet_you_owe_is_refused():
    code, _ids = setup_poker()

    with pytest.raises(ValidationError, match="call, raise or fold"):
        lobbies.poker_act(code, view(code).to_act, PokerAction.check)


def test_playing_out_of_turn_is_refused():
    code, _ids = setup_poker()

    waiting = next(
        seat.player_id for seat in view(code).seats if seat.player_id != view(code).to_act
    )
    with pytest.raises(ConflictError, match="not your turn"):
        lobbies.poker_act(code, waiting, PokerAction.call)


def test_folding_hands_the_pot_over_without_a_question_being_asked():
    code, _ids = setup_poker()

    folder = view(code).to_act
    lobbies.poker_act(code, folder, PokerAction.fold)

    table = view(code)
    assert table.stage is PokerStage.payout
    assert table.result.uncontested
    winner = next(seat for seat in table.seats if seat.player_id != folder)
    assert winner.won == poker.SMALL_BLIND + poker.BIG_BLIND
    assert winner.stack == poker.STARTING_STACK + poker.SMALL_BLIND


def test_the_clock_checks_for_you_when_checking_is_free():
    code, _ids = setup_poker()
    settle_bets(code)
    on_the_clock = view(code).to_act

    expire(code, "acts_by")
    table = view(code)

    assert next(s for s in table.seats if s.player_id == on_the_clock).folded is False
    assert table.to_act != on_the_clock


def test_the_clock_folds_you_when_there_is_a_bet_to_answer():
    code, _ids = setup_poker()
    first = view(code).to_act
    lobbies.poker_act(code, first, PokerAction.raise_to, poker.BIG_BLIND * 4)

    expire(code, "acts_by")

    assert view(code).stage is PokerStage.payout
    assert view(code).result.uncontested


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------


def test_the_right_answer_takes_the_pot():
    code, _ids = setup_poker()
    deal_to_the_question(code)
    table = view(code)
    assert table.stage is PokerStage.answering
    pot = table.pot

    right = answer_key(code)[0]
    first, second = (seat.player_id for seat in table.seats)
    lobbies.poker_answer(code, first, right)
    lobbies.poker_answer(code, second, a_wrong_answer(code))

    done = view(code)
    assert done.stage is PokerStage.payout
    assert seat_of(code, first).won == pot
    assert seat_of(code, second).won == 0
    assert seat_of(code, first).is_correct is True
    assert seat_of(code, second).is_correct is False


def test_two_right_answers_split_the_pot():
    code, _ids = setup_poker()
    deal_to_the_question(code)
    pot = view(code).pot

    right = answer_key(code)[0]
    for seat in view(code).seats:
        lobbies.poker_answer(code, seat.player_id, right)

    assert [seat.won for seat in view(code).seats] == [pot // 2, pot // 2]


def test_an_answer_is_hidden_until_the_hand_pays_out():
    code, _ids = setup_poker()
    deal_to_the_question(code)

    first = view(code).seats[0].player_id
    lobbies.poker_answer(code, first, answer_key(code)[0])

    seat = seat_of(code, first)
    assert seat.has_answered
    assert seat.answer_item_id is None
    assert seat.is_correct is None


def test_answering_twice_is_refused():
    code, _ids = setup_poker()
    deal_to_the_question(code)
    first = view(code).seats[0].player_id

    lobbies.poker_answer(code, first, answer_key(code)[0])
    with pytest.raises(ConflictError, match="already answered"):
        lobbies.poker_answer(code, first, answer_key(code)[0])


def test_running_out_of_time_answers_nothing_and_is_wrong():
    code, _ids = setup_poker()
    deal_to_the_question(code)
    pot = view(code).pot

    expire(code, "answers_by")

    table = view(code)
    assert table.stage is PokerStage.payout
    assert all(seat.won == 0 for seat in table.seats)
    assert table.carried == pot


def test_a_pot_nobody_wins_is_played_for_again():
    code, _ids = setup_poker(hands=2)
    deal_to_the_question(code)
    lost = view(code).pot

    for seat in view(code).seats:
        lobbies.poker_answer(code, seat.player_id, a_wrong_answer(code))
    assert view(code).result.carried == lost

    expire(code, "next_hand_at")

    table = view(code)
    assert table.hand_index == 1
    assert table.stage is PokerStage.preflop
    assert table.carried == lost
    assert table.pot == lost + poker.SMALL_BLIND + poker.BIG_BLIND


def test_the_answer_key_is_shown_once_the_hand_is_over():
    code, _ids = setup_poker()
    deal_to_the_question(code)

    for seat in view(code).seats:
        lobbies.poker_answer(code, seat.player_id, a_wrong_answer(code))

    result = view(code).result
    assert result.correct_item_ids == answer_key(code)
    assert len(result.correct_labels) == 1
    assert view(code).question is not None


# ---------------------------------------------------------------------------
# Chips, side pots and the end of the game
# ---------------------------------------------------------------------------


def test_a_short_all_in_can_only_win_what_it_covered():
    """The side pot rule: 20 in cannot win the 40 two other players put in above it.

    Seat order is fixed rather than shuffled, so the button sits with the host
    and the player after the blinds -- Anna -- speaks first. Asserted, so this
    reads as a broken test rather than a broken pot if that ever changes.
    """
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    with lobbies.edit(code) as lobby:
        lobby.poker.seat(anna).stack = 20

    assert view(code).to_act == anna
    lobbies.poker_act(code, anna, PokerAction.all_in)
    lobbies.poker_act(code, ben, PokerAction.raise_to, 60)
    lobbies.poker_act(code, cleo, PokerAction.call)

    deal_to_the_question(code)
    right = answer_key(code)[0]
    for seat in view(code).seats:
        lobbies.poker_answer(code, seat.player_id, right)

    stacks = {seat.player_id: seat.stack for seat in view(code).seats}
    assert stacks[anna] == 20
    assert stacks[ben] == poker.STARTING_STACK
    assert stacks[cleo] == poker.STARTING_STACK


def test_chips_are_the_score_and_the_biggest_stack_wins_the_game():
    code, _ids = setup_poker(hands=1)
    deal_to_the_question(code)

    winner = view(code).seats[0].player_id
    lobbies.poker_answer(code, winner, answer_key(code)[0])
    lobbies.poker_answer(code, view(code).seats[1].player_id, a_wrong_answer(code))
    expire(code, "next_hand_at")

    lobby = lobbies.get_view(code)
    assert lobby.status.value == "finished"
    assert lobby.winner_ids == [winner]
    assert {p.id: p.score for p in lobby.players}[winner] > poker.STARTING_STACK


def test_the_table_does_not_wait_out_the_clock_on_a_closed_tab():
    code, (anna, ben) = setup_poker()
    on_the_clock = view(code).to_act

    lobbies.mark_away(code, on_the_clock)

    table = view(code)
    assert next(s for s in table.seats if s.player_id == on_the_clock).folded
    assert table.stage is PokerStage.payout


def test_the_next_hand_waits_for_a_player_who_is_reloading():
    """Held, not ended. A tab that comes back finds the game where it was."""
    code, (_anna, ben) = setup_poker(hands=2)
    lobbies.poker_act(code, view(code).to_act, PokerAction.fold)
    lobbies.mark_away(code, ben)
    expire(code, "next_hand_at")

    held = view(code)
    assert held.hand_index == 1
    assert held.to_act is None
    assert all(not seat.has_cards for seat in held.seats)

    dealt = lobbies.get_view(code, ben).poker
    assert dealt.to_act is not None
    assert all(seat.has_cards for seat in dealt.seats)


def test_a_classic_game_has_no_poker_table_and_the_other_way_round():
    code, _ids = setup_poker()
    assert lobbies.get_view(code).round_view is None

    other, host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(other, "Ben")
    lobbies.start_game(other, host, ["topic-a"], 1)

    assert lobbies.get_view(other).poker is None
    with pytest.raises(ConflictError, match="no poker game"):
        lobbies.poker_act(other, host, PokerAction.check)


def test_the_routes_carry_the_moves_and_keep_the_cards_apart():
    """One pass over HTTP, since everything above this talks to the service."""
    client = TestClient(app)
    code, (anna, ben) = setup_poker()
    on_the_clock = view(code).to_act

    folded = client.post(
        f"/lobbies/{code}/poker/act",
        json={"player_id": str(on_the_clock), "action": "fold"},
    )
    assert folded.status_code == 200
    assert folded.json()["poker"]["stage"] == "payout"

    mine = client.get(f"/lobbies/{code}/poker/hand", params={"player_id": str(anna)})
    theirs = client.get(f"/lobbies/{code}/poker/hand", params={"player_id": str(ben)})
    assert len(mine.json()["cards"]) == 2
    assert mine.json()["cards"] != theirs.json()["cards"]
