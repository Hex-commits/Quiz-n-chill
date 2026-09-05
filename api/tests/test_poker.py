"""Poker-mode tests: the betting, the staged reveal, and who takes the pot.

The topic loader is stubbed exactly as in `test_lobbies.py`, so none of this
touches a database. What is *not* stubbed is the shuffle: the deck and the
question are random by design, so every test below reads the table for what it
was dealt rather than assuming it.
"""

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import ConflictError, ValidationError
from app.main import app
from app.schemas import (
    Category,
    CategoryKind,
    GameMode,
    ImagePublic,
    ItemSolution,
    PokerAction,
    PokerStage,
)
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


def setup_open_end(nicknames=("Anna", "Ben"), questions=1):
    """A poker game with no length: it runs until one player has the chips."""
    code, host_id = lobbies.create_lobby(nicknames[0])
    ids = [host_id] + [lobbies.join_lobby(code, name) for name in nicknames[1:]]
    slugs = [f"topic-{n}" for n in range(questions)]
    lobbies.start_game(code, host_id, slugs, 1, mode=GameMode.poker, open_end=True)
    return code, ids


def view(code, player_id=None):
    return lobbies.get_view(code, player_id).poker


def seat_of(code, player_id):
    return next(s for s in view(code).seats if s.player_id == player_id)


def answer_key(code):
    """Where the answer in play belongs, read off the table's own state.

    One category, always: the board pairs one to one, so the answer being asked
    about fits exactly one of the categories offered against it.
    """
    with lobbies.edit(code) as lobby:
        asked = next(
            item
            for item in lobby.current_round.items
            if item.id == lobby.poker.question_item_id
        )
        return [asked.category_id]


def a_wrong_answer(code):
    right = set(answer_key(code))
    return next(option.id for option in view(code).options if option.id not in right)


def one_move(code):
    """The cheapest legal move for whoever is on the clock: check, or call."""
    table = view(code)
    seat = next(s for s in table.seats if s.player_id == table.to_act)
    action = (
        PokerAction.check if seat.committed == table.current_bet else PokerAction.call
    )
    lobbies.poker_act(code, table.to_act, action)


def settle_bets(code):
    """Everyone checks or calls until this street closes. The cheapest way on."""
    street = view(code).stage
    while True:
        table = view(code)
        if table.to_act is None or table.stage is not street:
            return table
        one_move(code)


BETTING = (PokerStage.preflop, PokerStage.flop, PokerStage.turn)


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


def test_a_hand_opens_with_the_blinds_up_and_the_subject_named():
    """The opening round has something to bet on, which is the point of it."""
    code, _ids = setup_poker()

    table = view(code)
    assert table.stage is PokerStage.preflop
    assert table.pot == poker.SMALL_BLIND + poker.BIG_BLIND
    assert table.subject_name == "Geografie"
    assert (table.title, table.question) == (None, None)
    assert {seat.stack for seat in table.seats} == {
        poker.STARTING_STACK - poker.SMALL_BLIND,
        poker.STARTING_STACK - poker.BIG_BLIND,
    }


def test_the_question_is_revealed_one_betting_round_at_a_time():
    code, _ids = setup_poker()

    opening = view(code)
    assert opening.subject_name == "Geografie"
    assert opening.title is None

    settle_bets(code)
    second = view(code)
    assert second.stage is PokerStage.flop
    assert second.title == "Flüsse in Europa"
    assert second.question is None
    assert second.options == []

    settle_bets(code)
    third = view(code)
    assert third.stage is PokerStage.turn
    assert third.question is not None
    assert third.options == []

    settle_bets(code)
    asked = view(code)
    assert asked.stage is PokerStage.answering
    assert asked.question is not None
    assert len(asked.options) == 4


def test_nothing_of_the_question_leaks_before_its_round():
    code, (anna, _ben) = setup_poker()

    payload = lobbies.get_view(code, anna).model_dump_json()

    for label in ("Berlin", "Paris", "Madrid", "Rom", "Deutschland"):
        assert label not in payload


def test_the_answers_stay_off_the_table_while_the_last_bet_is_made():
    """The last round asks. What it does not do is list what the answer may be."""
    code, _ids = setup_poker()
    while view(code).stage is not PokerStage.turn:
        settle_bets(code)

    asking = view(code)
    payload = lobbies.get_view(code).model_dump_json()
    assert asking.question is not None
    assert asking.options == []
    for label in ("Deutschland", "Frankreich", "Spanien", "Italien"):
        assert f'"{label}"' not in payload

    settle_bets(code)
    assert len(view(code).options) == 4


def test_the_question_is_an_answer_and_the_options_are_where_it_belongs():
    """The short way round: one answer up, and the categories under it.

    A board is four categories and four answers here and ten to twelve of each
    in the real thing, so this is also the shorter way round to read.
    """
    code, _ids = setup_poker()
    table = deal_to_the_question(code)

    with lobbies.edit(code) as lobby:
        items = {item.id for item in lobby.current_round.items}
        categories = {c.id for c in lobby.current_round.categories}

    assert table.question.id in items
    assert {option.id for option in table.options} == categories
    assert set(answer_key(code)) <= categories


def test_a_fake_answer_is_never_the_question():
    """It belongs in no category, so there would be nothing on the table to pick."""
    round_ = make_round("topic-0")
    fake = ItemSolution(id=uuid4(), label="Kathmandu", position=5, category_id=None)
    round_.items.append(fake)

    asked = {poker._pick_question(round_) for _ in range(200)}

    assert fake.id not in asked
    assert asked == {item.id for item in round_.items if item.category_id}


def test_a_picture_round_offers_its_photographs_unnamed(monkeypatch):
    """The caption on a photograph is the answer to it.

    Knowing the tower is the Eiffel Tower is knowing it is in France, so the
    names stay off the options until the hand is over -- the same rule as when
    the photograph was the question rather than one of the answers.
    """

    def in_pictures(slug: str):
        round_ = make_round(slug)
        round_.category_kind = CategoryKind.image
        for category in round_.categories:
            category.image = ImagePublic(
                src="https://commons.wikimedia.org/wiki/Special:FilePath/X.jpg",
                credit="Ein Fotograf",
                licence="CC BY-SA 4.0",
                licence_url="https://creativecommons.org/licenses/by-sa/4.0",
            )
        return round_

    monkeypatch.setattr(lobbies, "_load_round", in_pictures)
    code, (anna, ben) = setup_poker()
    deal_to_the_question(code)

    asked = view(code)
    assert asked.question.label in ("Berlin", "Paris", "Madrid", "Rom")
    assert all(o.label is None and o.image is not None for o in asked.options)

    wrong = a_wrong_answer(code)
    lobbies.poker_answer(code, anna, answer_key(code)[0])
    lobbies.poker_answer(code, ben, wrong)

    assert all(option.label for option in view(code).options)


def test_the_payout_explains_the_answer_it_asked_about():
    """The note is written on the answer, which is now the thing being asked."""
    code, (anna, ben) = setup_poker()
    deal_to_the_question(code)
    with lobbies.edit(code) as lobby:
        berlin = next(i for i in lobby.current_round.items if i.label == "Berlin")
        lobby.poker.question_item_id = berlin.id

    wrong = a_wrong_answer(code)
    lobbies.poker_answer(code, anna, answer_key(code)[0])
    lobbies.poker_answer(code, ben, wrong)

    result = view(code).result
    assert result.correct_labels == ["Deutschland"]
    assert result.explanation == "Hauptstadt Deutschlands."


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
    assert seat.answer_category_id is None
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
    assert result.correct_category_ids == answer_key(code)
    assert len(result.correct_labels) == 1
    assert view(code).question is not None


# ---------------------------------------------------------------------------
# Backing another player
# ---------------------------------------------------------------------------


def fold_out(code, folder):
    """Bet round the table until `folder` is on the clock, then fold them.

    Bounded rather than a bare `while`: if the hand ends or the stage moves on
    without them ever speaking, a test should say so rather than spin.
    """
    for _ in range(20):
        table = view(code)
        if table.to_act == folder:
            lobbies.poker_act(code, folder, PokerAction.fold)
            return
        assert table.stage in BETTING, f"hand reached {table.stage} before {folder}"
        one_move(code)
    raise AssertionError("never got the clock round to that player")


def a_backed_hand(code, backer, backed, *, right=True):
    """Play one hand out with `backer` folded and a blind behind `backed`.

    Returns the pot it was played for, which is what the cut comes off. Everyone
    still in answers wrongly except `backed`, and only when the bet is meant to
    come in -- so the hand turns on the one side bet being tested and nothing
    else.
    """
    fold_out(code, backer)
    lobbies.poker_back(code, backer, backed)
    deal_to_the_question(code)
    pot = view(code).pot

    key, wrong = answer_key(code)[0], a_wrong_answer(code)
    for seat in view(code).seats:
        if seat.folded or seat.sitting_out:
            continue
        hit = seat.player_id == backed and right
        lobbies.poker_answer(code, seat.player_id, key if hit else wrong)
    return pot


def next_hand(code):
    """Run the payout clock out and let the poll deal the next one."""
    expire(code, "next_hand_at")
    view(code)


def price(code):
    """What a side bet costs. The same whenever it is placed -- see `odds`."""
    return poker.SIDE_BET_STAKE


def odds(code):
    """What a side bet placed right now pays back, per chip staked."""
    return poker.SIDE_BET_LADDER[view(code).stage]


def bust(code, player):
    """Take a player's chips away and deal the hand that leaves them out.

    Played out rather than just emptied, because `sitting_out` is decided when a
    hand is dealt: a stack emptied mid-hand is still in the one being played.
    """
    deal_to_the_question(code)
    for seat in view(code).seats:
        if not (seat.folded or seat.sitting_out):
            lobbies.poker_answer(code, seat.player_id, a_wrong_answer(code))
    with lobbies.edit(code) as lobby:
        lobby.poker.seat(player).stack = 0
    next_hand(code)
    assert seat_of(code, player).sitting_out


def test_backing_costs_the_same_whenever_you_place_it():
    code, (anna, ben, _cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    stack = seat_of(code, anna).stack

    lobbies.poker_back(code, anna, ben)

    backer = seat_of(code, anna)
    assert backer.backing == ben
    assert backer.side_stake == poker.SIDE_BET_STAKE
    assert backer.stack == stack - poker.SIDE_BET_STAKE


def test_the_odds_on_a_side_bet_fall_as_the_hand_goes_on():
    """The stake never moves. What moves is what being right is worth.

    Before a chip has moved the subject is all anybody has, and a read made on
    that pays four times the stake. By the turn the question is face up and the
    betting has said who liked it -- the same call, made knowing most of what
    there is to know, and worth half as much.
    """
    seen = []
    for stage in poker.LIVE:
        code, (anna, ben, _cleo) = setup_poker(("Anna", "Ben", "Cleo"))
        fold_out(code, anna)
        while view(code).stage is not stage:
            settle_bets(code)

        assert view(code).side_price == poker.SIDE_BET_STAKE, "the price is flat"
        assert view(code).side_odds == poker.SIDE_BET_LADDER[stage]
        lobbies.poker_back(code, anna, ben)
        seen.append((seat_of(code, anna).side_stake, seat_of(code, anna).side_odds))

    stakes = [stake for stake, _ in seen]
    assert stakes == [poker.SIDE_BET_STAKE] * len(poker.LIVE)
    assert [o for _, o in seen] == [4, 3, 2, 2]


def test_an_early_side_bet_pays_more_than_the_same_read_made_late():
    """The whole of the mechanic, in chips actually taken.

    The same stake goes down on the same player in every one of these hands and
    the only difference is when. Waiting has to cost, or a bet on a hand in
    progress is just a bet placed at the last safe moment.
    """
    took = []
    for stage in poker.LIVE:
        code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
        fold_out(code, anna)
        while view(code).stage is not stage:
            settle_bets(code)
        stake = price(code)
        lobbies.poker_back(code, anna, ben)

        deal_to_the_question(code)
        lobbies.poker_answer(code, ben, answer_key(code)[0])
        lobbies.poker_answer(code, cleo, a_wrong_answer(code))

        assert seat_of(code, anna).won == stake * poker.SIDE_BET_LADDER[stage]
        took.append(seat_of(code, anna).won)

    assert took[0] > took[1] > took[2], "earlier pays better, every rung of it"
    assert took[0] == took[-1] * 2, "and the first rung is worth twice the last"


def test_the_odds_are_zero_once_there_is_nothing_left_to_back():
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    deal_to_the_question(code)
    for player in (ben, cleo):
        lobbies.poker_answer(code, player, a_wrong_answer(code))

    assert view(code).stage is PokerStage.payout
    assert (view(code).side_price, view(code).side_odds) == (0, 0)


def test_backing_the_right_answer_pays_the_odds_and_the_pot_keeps_its_chips():
    """The house pays the rail, so the hand pays its winner in full.

    Which is the whole of the change: what a hand is worth is settled by the
    hand, and a player who won one is no worse off for having been watched.
    """
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    stake, paid = price(code), price(code) * odds(code)
    lobbies.poker_back(code, anna, ben)
    backer_stack = seat_of(code, anna).stack

    deal_to_the_question(code)
    pot = view(code).pot
    lobbies.poker_answer(code, ben, answer_key(code)[0])
    lobbies.poker_answer(code, cleo, a_wrong_answer(code))

    assert seat_of(code, anna).won == paid
    assert seat_of(code, anna).stack == backer_stack + paid
    assert paid > stake, "and it is a profit, not a refund"
    assert seat_of(code, ben).won == pot, "not a chip of it went to the rail"


def test_backing_the_wrong_player_loses_the_stake_into_the_pot():
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    stake = price(code)
    lobbies.poker_back(code, anna, cleo)
    backer_stack = seat_of(code, anna).stack

    deal_to_the_question(code)
    pot = view(code).pot
    lobbies.poker_answer(code, ben, answer_key(code)[0])
    lobbies.poker_answer(code, cleo, a_wrong_answer(code))

    assert seat_of(code, anna).stack == backer_stack, "nothing came back"
    assert seat_of(code, ben).won == pot + stake
    assert sum(seat.stack for seat in view(code).seats) == 3 * poker.STARTING_STACK


def test_two_backers_on_one_player_are_each_paid_in_full():
    """Nobody splits anything. The bets are separate, and so are the payouts."""
    code, (anna, ben, cleo, dan) = setup_poker(("Anna", "Ben", "Cleo", "Dan"))
    fold_out(code, anna)
    stake, paid = price(code), price(code) * odds(code)
    lobbies.poker_back(code, anna, dan)
    fold_out(code, ben)
    lobbies.poker_back(code, ben, dan)

    deal_to_the_question(code)
    pot = view(code).pot
    lobbies.poker_answer(code, cleo, a_wrong_answer(code))
    lobbies.poker_answer(code, dan, answer_key(code)[0])

    assert seat_of(code, anna).won == paid
    assert seat_of(code, ben).won == paid
    assert seat_of(code, dan).won == pot
    assert stake == poker.SIDE_BET_STAKE


def test_a_split_pot_leans_towards_the_player_with_money_on_them():
    """Two right answers, one of them backed.

    The pot is shared eleven parts to ten in favour of the player the money was
    on -- and the whole of it is shared, because the side bet is not paid out of
    it any more.
    """
    code, (anna, ben, cleo, dan) = setup_poker(("Anna", "Ben", "Cleo", "Dan"))
    fold_out(code, anna)
    lobbies.poker_back(code, anna, ben)
    fold_out(code, dan)

    deal_to_the_question(code)
    pot = view(code).pot
    right = answer_key(code)[0]
    lobbies.poker_answer(code, ben, right)
    lobbies.poker_answer(code, cleo, right)

    backed, unbacked = seat_of(code, ben).won, seat_of(code, cleo).won
    assert backed + unbacked == pot
    assert backed > unbacked


def test_a_backer_is_paid_on_a_pot_nobody_had_to_answer_for():
    """Everyone else folded, so the side bet settles on the hand as it ended."""
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    paid = price(code) * odds(code)
    lobbies.poker_back(code, anna, ben)
    backer_stack = seat_of(code, anna).stack
    fold_out(code, cleo)

    assert seat_of(code, anna).won == paid
    assert seat_of(code, anna).stack == backer_stack + paid
    assert seat_of(code, ben).won > 0


def test_a_player_still_in_the_hand_can_back_somebody_else():
    """The side game runs beside the first, not instead of it.

    Folding is not the price of admission: a player with chips in the pot can
    put money on somebody else without giving up their own hand to do it.
    """
    code, _ids = setup_poker(("Anna", "Ben", "Cleo"))
    backer = view(code).to_act
    target = next(
        seat.player_id
        for seat in view(code).seats
        if seat.player_id != backer and not seat.folded
    )
    stack = seat_of(code, backer).stack
    stake = price(code)

    lobbies.poker_back(code, backer, target)

    seat = seat_of(code, backer)
    assert (seat.backing, seat.side_stake) == (target, stake)
    assert seat.folded is False, "backing is not folding"
    assert seat.stack == stack - stake
    assert view(code).to_act == backer, "and it is still their turn to act"


def test_backing_is_still_one_bet_a_hand():
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    lobbies.poker_back(code, anna, ben)

    with pytest.raises(ConflictError, match="already behind"):
        lobbies.poker_back(code, anna, cleo)


def test_you_cannot_back_yourself_or_somebody_who_has_folded():
    code, (anna, ben, _cleo, _dan) = setup_poker(("Anna", "Ben", "Cleo", "Dan"))
    fold_out(code, anna)

    with pytest.raises(ConflictError, match="cannot back yourself"):
        lobbies.poker_back(code, anna, anna)

    fold_out(code, ben)
    with pytest.raises(ConflictError, match="not in this hand"):
        lobbies.poker_back(code, anna, ben)


def test_a_side_bet_may_not_be_the_chips_you_had_left_to_play():
    """It would settle your own hand for you, which is not a side bet at all.

    Only binds on a player still in it. Somebody who has folded has nothing left
    to play with this hand, so spending down to nothing costs them nothing now.
    """
    code, _ids = setup_poker(("Anna", "Ben", "Cleo"))
    live = view(code).to_act
    target = next(
        seat.player_id for seat in view(code).seats if seat.player_id != live
    )
    with lobbies.edit(code) as lobby:
        lobby.poker.seat(live).stack = price(code)

    with pytest.raises(ValidationError, match="chips you have left"):
        lobbies.poker_back(code, live, target)

    fold_out(code, live)
    lobbies.poker_back(code, live, target)
    assert seat_of(code, live).stack == 0


def test_a_stack_too_short_for_the_stake_cannot_back_at_all():
    """The price is the price.

    Being nearly broke buys no discount, and it buys no better odds either --
    those are the hand's, not the player's. Only being broke outright changes
    the terms, and that is a different bet -- see the free one below.
    """
    code, (anna, ben, _cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    while view(code).stage is not PokerStage.turn:
        settle_bets(code)
    with lobbies.edit(code) as lobby:
        lobby.poker.seat(anna).stack = poker.SIDE_BET_STAKE - 1

    with pytest.raises(
        ValidationError, match=f"Backing someone costs {poker.SIDE_BET_STAKE}"
    ):
        lobbies.poker_back(code, anna, ben)


def test_a_player_with_no_chips_backs_for_nothing_and_wins_their_way_back_in():
    """The way back to the table for somebody already off it.

    They are not in the hand and cannot be -- the deal passes an empty stack by
    -- so the bet costs nothing and pays what it was worth. One good read and
    they are dealt in again.
    """
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"), hands=4)
    bust(code, anna)
    stake = price(code)

    winnings = stake * (odds(code) - 1)
    lobbies.poker_back(code, anna, ben)
    out = seat_of(code, anna)
    assert (out.stack, out.side_stake, out.side_free) == (0, stake, True)

    deal_to_the_question(code)
    lobbies.poker_answer(code, ben, answer_key(code)[0])
    lobbies.poker_answer(code, cleo, a_wrong_answer(code))

    assert seat_of(code, anna).won == winnings, "the winnings, without a stake back"
    assert seat_of(code, anna).stack == winnings
    next_hand(code)
    assert seat_of(code, anna).sitting_out is False, "and they are dealt back in"


def test_a_free_bet_that_misses_costs_nothing_and_leaves_the_pot_alone():
    """There is no stake to lose, so the pot is not handed one."""
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"), hands=4)
    bust(code, anna)
    lobbies.poker_back(code, anna, cleo)

    deal_to_the_question(code)
    pot = view(code).pot
    lobbies.poker_answer(code, ben, answer_key(code)[0])
    lobbies.poker_answer(code, cleo, a_wrong_answer(code))

    assert seat_of(code, anna).stack == 0
    assert seat_of(code, ben).won == pot, "the pot is what the table put in"


def test_backing_stays_open_while_the_answers_are_being_given():
    """Who knows it is exactly what is still unsettled once the options are up."""
    code, (anna, ben, _cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    deal_to_the_question(code)
    assert view(code).stage is PokerStage.answering

    lobbies.poker_back(code, anna, ben)

    assert seat_of(code, anna).backing == ben


def test_backing_closes_once_the_hand_has_paid_out():
    """By then who was right is public, and a bet on it is chips for nothing."""
    code, (anna, ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, anna)
    deal_to_the_question(code)
    for player in (ben, cleo):
        lobbies.poker_answer(code, player, a_wrong_answer(code))
    assert view(code).stage is PokerStage.payout

    with pytest.raises(ConflictError, match="nothing left to back"):
        lobbies.poker_back(code, anna, ben)


def test_a_backer_who_wins_the_pot_himself_is_paid_for_both():
    """Two bets, two payouts, and neither one taken out of the other.

    Backing somebody else while playing your own hand is a hedge, and both sides
    of it can come in: the pot for the hand you played, the doubled stake for
    the read you made.
    """
    code, (_anna, _ben, cleo) = setup_poker(("Anna", "Ben", "Cleo"))
    fold_out(code, cleo)
    backer = view(code).to_act
    other = next(
        seat.player_id
        for seat in view(code).seats
        if seat.player_id not in (backer, cleo)
    )
    paid = price(code) * odds(code)
    lobbies.poker_back(code, backer, other)

    deal_to_the_question(code)
    pot = view(code).pot
    right = answer_key(code)[0]
    lobbies.poker_answer(code, backer, right)
    lobbies.poker_answer(code, other, right)

    backer_won, other_won = seat_of(code, backer).won, seat_of(code, other).won
    assert backer_won + other_won == pot + paid, "the pot, and the bet on top"
    assert backer_won - paid > 0, "their share of the pot as well as the payout"
    assert other_won > 0, "and the player they backed is not paying for the privilege"


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
    assert held.pot == 0, "no blinds are up until there is somebody to take them"

    dealt = lobbies.get_view(code, ben).poker
    assert dealt.to_act is not None
    assert dealt.pot == poker.SMALL_BLIND + poker.BIG_BLIND


def test_a_classic_game_has_no_poker_table_and_the_other_way_round():
    code, _ids = setup_poker()
    assert lobbies.get_view(code).round_view is None

    other, host = lobbies.create_lobby("Anna")
    lobbies.join_lobby(other, "Ben")
    lobbies.start_game(other, host, ["topic-a"], 1)

    assert lobbies.get_view(other).poker is None
    with pytest.raises(ConflictError, match="no poker game"):
        lobbies.poker_act(other, host, PokerAction.check)


def test_the_routes_carry_the_moves():
    """One pass over HTTP, since everything above this talks to the service."""
    client = TestClient(app)
    code, _ids = setup_poker(("Anna", "Ben", "Cleo"))
    on_the_clock = view(code).to_act

    folded = client.post(
        f"/lobbies/{code}/poker/act",
        json={"player_id": str(on_the_clock), "action": "fold"},
    )
    assert folded.status_code == 200

    backed = client.post(
        f"/lobbies/{code}/poker/back",
        json={
            "player_id": str(on_the_clock),
            "backed_id": str(view(code).to_act),
        },
    )
    assert backed.status_code == 200
    seats = {s["player_id"]: s for s in backed.json()["poker"]["seats"]}
    assert seats[str(on_the_clock)]["side_stake"] == poker.SIDE_BET_STAKE
    assert (
        seats[str(on_the_clock)]["side_odds"]
        == poker.SIDE_BET_LADDER[PokerStage.preflop]
    )


# ---------------------------------------------------------------------------
# Open end: the game that runs until one player has the chips
# ---------------------------------------------------------------------------


def test_an_open_end_game_keeps_dealing_after_the_questions_run_out():
    """The questions are what it is played with, not what ends it."""
    code, _ids = setup_open_end(questions=1)
    lobbies.poker_act(code, view(code).to_act, PokerAction.fold)
    expire(code, "next_hand_at")

    table = view(code)
    assert lobbies.get_view(code).status.value == "playing"
    assert table.hand_index == 1, "past the one question drawn, and still dealing"
    assert table.hand_count == 1
    assert table.open_end is True
    assert table.pot == poker.SMALL_BLIND + poker.BIG_BLIND, "blinds are up again"


def test_an_open_end_game_ends_when_one_player_has_the_chips():
    code, (anna, ben) = setup_open_end(questions=1)

    lobbies.poker_act(code, view(code).to_act, PokerAction.all_in)
    lobbies.poker_act(code, view(code).to_act, PokerAction.all_in)
    assert view(code).stage is PokerStage.answering, "nobody left with chips to bet"

    right = answer_key(code)[0]
    lobbies.poker_answer(code, anna, right)
    lobbies.poker_answer(code, ben, a_wrong_answer(code))
    expire(code, "next_hand_at")

    lobby = lobbies.get_view(code)
    assert lobby.status.value == "finished"
    assert lobby.winner_ids == [anna]
    assert {seat.player_id: seat.stack for seat in view(code).seats}[ben] == 0


def test_a_question_that_comes_round_again_is_asked_differently():
    """Wrapping re-deals rather than replaying. One stored question holds several
    askable categories, and each pass draws again -- so a table that outlasts the
    pool gets new hands off it rather than the same hand twice.

    Seeded, because the draw is random by design and an unseeded run of this
    would be a test that usually passes."""
    random.seed(20260829)
    code, _ids = setup_open_end(questions=1)

    asked = []
    for _ in range(10):
        with lobbies.edit(code) as lobby:
            asked.append(lobby.poker.question_item_id)
        lobbies.poker_act(code, view(code).to_act, PokerAction.fold)
        expire(code, "next_hand_at")

    assert view(code).hand_index == 10, "ten hands off one question"
    assert len(set(asked)) > 1, "and not the same category every time"


def test_open_end_is_a_poker_rule_and_classic_ignores_it():
    code, host_id = lobbies.create_lobby("Anna")
    lobbies.join_lobby(code, "Ben")
    lobbies.start_game(code, host_id, ["topic-0"], 1, open_end=True)

    assert lobbies.get_view(code).settings.open_end is False
