"""Poker's betting, played for a question instead of a hand.

There are no cards. What the blinds, the four betting rounds and the showdown
are built around here is a question that arrives a piece at a time --

    pre-reveal  nothing yet
    first       the subject          "Geografie"
    second      the topic            "Flüsse in Europa"
    third       the question itself  "Rhein"

-- so the first bets are made on a question you cannot see, and the last one
after you can read it. The answers to choose between are not part of that: they
come out when the betting is over, so the last bet is made on whether you know
the answer rather than on whether you recognise it in a list. Everyone still in
then answers at once, and whoever is right takes the pot; several right answers
split it. A pot nobody wins is not returned. It stays on the table and the next
hand plays for it too.

The stages keep poker's names -- flop, turn, river -- because that is what they
are: the betting rounds between one reveal and the next.

This module is rules only. It never touches the store, publishes nothing, and
every function here takes the `Lobby` it works on -- `lobbies` owns the
read-modify-write and calls in.

What the table may show and when is `view`'s single decision. `Lobby` holds the
whole answer key for the hand in `current_round`, exactly as it does in Classic,
and nothing else in this module hands any of it out.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from app.errors import ConflictError, ValidationError
from app.schemas import (
    CategoryKind,
    ItemPublic,
    LobbyStatus,
    PokerAction,
    PokerAward,
    PokerResult,
    PokerSeatView,
    PokerStage,
    PokerView,
)
from app.services.boards import deal_board
from app.services.lobby_state import Lobby, PokerSeat, PokerTable, Round

STARTING_STACK = 200

SMALL_BLIND = 5

BIG_BLIND = 10
"""Twenty big blinds each. Short enough that folding every hand loses the game
over the five to twenty hands one of these lasts, which is the point: the
players who never risk anything must not be the ones who win."""

PAYOUT_SECONDS = 12
"""How long the answer key stays up before the next hand is dealt."""

SIDE_BET_SHARE = 10
"""A backer takes a tenth of what the player they backed took home.

Split between them where several backed the same player, so the player who
actually answered always keeps nine tenths of their pot however many people
were behind them. A cut of the winnings rather than a fixed prize, because a
side bet on a hand that got big should be worth more than one on a hand that
did not."""

BETTING = (PokerStage.preflop, PokerStage.flop, PokerStage.turn, PokerStage.river)

ORDER = (*BETTING, PokerStage.answering, PokerStage.payout)


# ---------------------------------------------------------------------------
# Entry points -- `lobbies` calls these inside its own mutate block
# ---------------------------------------------------------------------------


def begin(lobby: Lobby) -> None:
    """Seat everyone with a stack and deal the first hand."""
    lobby.poker = PokerTable(
        seats=[PokerSeat(player_id=p.id, stack=STARTING_STACK) for p in lobby.players],
        button=len(lobby.players) - 1,
        big_blind=BIG_BLIND,
    )
    _start_hand(lobby)


def act(
    lobby: Lobby, player_id: UUID, action: PokerAction, amount: int | None = None
) -> None:
    """Fold, check, call or raise. `amount` is the total to raise *to*."""
    table = _table(lobby)
    if table.stage not in BETTING:
        raise ConflictError("There is no betting to do right now.")

    seat = table.seat(player_id)
    if seat is None or table.to_act is None or table.seats[table.to_act] is not seat:
        raise ConflictError("It is not your turn to act.")

    owed = table.current_bet - seat.committed
    if action is PokerAction.fold:
        seat.folded = True
    elif action is PokerAction.check:
        if owed > 0:
            raise ValidationError(f"There is {owed} to you -- call, raise or fold.")
    elif action is PokerAction.call:
        if owed <= 0:
            raise ValidationError("Nothing to call. Check instead.")
        _commit(seat, owed)
    elif action is PokerAction.all_in:
        _raise_to(table, seat, seat.committed + seat.stack)
    else:
        if amount is None:
            raise ValidationError("A raise has to say how much to.")
        _raise_to(table, seat, amount)

    seat.acted = True
    _after_act(lobby)


def answer(lobby: Lobby, player_id: UUID, item_id: UUID) -> None:
    """Name the answer. Locked in once given, and hidden until the hand pays out."""
    table = _table(lobby)
    if table.stage is not PokerStage.answering:
        raise ConflictError("There is no question to answer right now.")

    seat = table.seat(player_id)
    if seat is None or not seat.in_hand():
        raise ConflictError("You are not in this hand.")
    if seat.answer_item_id is not None:
        raise ConflictError("You have already answered.")
    if item_id not in table.option_ids:
        raise ValidationError("That answer is not on the table.")

    seat.answer_item_id = item_id
    lobby.touch()
    if all(s.answer_item_id is not None for s in table.seats if s.in_hand()):
        _resolve(lobby)


def back(lobby: Lobby, player_id: UUID, backed_id: UUID) -> None:
    """Fold, then put a big blind behind somebody still in it.

    Only open to a player who has folded, and only while the betting runs: once
    the answers are up there is nothing left to bet on that the table cannot
    already see.

    The stake leaves the stack now and is settled when the hand is. Right, and
    it comes back with a share of what the backed player took; wrong, and it
    joins the pot for whoever does take it.
    """
    table = _table(lobby)
    if table.stage not in BETTING:
        raise ConflictError("There is nothing left to back this hand.")

    seat = table.seat(player_id)
    if seat is None or not seat.folded:
        raise ConflictError("Only a player who has folded can back someone.")
    if seat.backing is not None:
        raise ConflictError("You are already behind someone this hand.")

    backed = table.seat(backed_id)
    if backed is None or not backed.in_hand():
        raise ConflictError("They are not in this hand.")
    if seat.stack < table.big_blind:
        raise ValidationError(f"Backing someone costs {table.big_blind}.")

    seat.stack -= table.big_blind
    seat.side_stake = table.big_blind
    seat.backing = backed_id
    _sync_players(lobby)
    lobby.touch()


def resync(lobby: Lobby) -> None:
    """Move the hand on for whatever the clock has decided.

    Nobody submits anything while a clock runs down, so the players' polling is
    the only thing that can carry the table forward. Called on every read.
    """
    table = lobby.poker
    if table is None or lobby.status is not LobbyStatus.playing:
        return

    now = datetime.now(UTC)
    if table.stage is PokerStage.preflop and table.to_act is None:
        _start_hand(lobby)
        return
    if table.stage in BETTING:
        _fold_the_departed(lobby)
    if table.stage in BETTING and table.to_act is not None:
        waited = table.acts_by is not None and now >= table.acts_by
        if waited or not _connected(lobby, table.seats[table.to_act].player_id):
            _act_on_the_clock(lobby)
    if (
        table.stage is PokerStage.answering
        and table.answers_by is not None
        and now >= table.answers_by
    ):
        _resolve(lobby)
    if (
        table.stage is PokerStage.payout
        and table.next_hand_at is not None
        and now >= table.next_hand_at
    ):
        _next_hand(lobby)


def view(lobby: Lobby) -> PokerView | None:
    """The table, redacted to what the reveal has already said.

    The one place that decides what a player may see. Anything the deal has not
    reached yet is left out of the payload entirely rather than blanked, so
    there is nothing in it to read ahead of.

    Nothing on this table is private, which is what went with the cards: every
    player sees the same view, and the broadcast carries all of it.
    """
    table = lobby.poker
    if table is None:
        return None

    round_ = lobby.current_round
    seen = ORDER.index(table.stage)
    over = table.stage is PokerStage.payout

    return PokerView(
        stage=table.stage,
        hand_index=lobby.round_index,
        hand_count=len(lobby.rounds),
        pot=table.pot + sum(s.committed for s in table.seats) + table.carried,
        carried=table.carried,
        current_bet=table.current_bet,
        min_raise=table.min_raise,
        big_blind=table.big_blind,
        button_id=_seat_id(table, table.button),
        to_act=_seat_id(table, table.to_act),
        seconds_left=_seconds_left(table),
        seats=[
            PokerSeatView(
                player_id=seat.player_id,
                stack=seat.stack,
                committed=seat.committed,
                folded=seat.folded,
                all_in=seat.all_in,
                sitting_out=seat.sitting_out,
                has_answered=seat.answer_item_id is not None,
                answer_item_id=seat.answer_item_id if over else None,
                is_correct=seat.correct if over else None,
                won=seat.won if over else 0,
                backing=seat.backing,
                side_stake=seat.side_stake,
            )
            for seat in table.seats
        ],
        subject_name=round_.subject_name if round_ and seen >= 1 else None,
        title=round_.title if round_ and seen >= 2 else None,
        question=_question(table, round_, revealed=over) if seen >= 3 else None,
        options=_options(table, round_) if seen >= 4 else [],
        result=table.result,
    )


# ---------------------------------------------------------------------------
# Dealing
# ---------------------------------------------------------------------------


def _start_hand(lobby: Lobby) -> None:
    """Deal a hand, or hold the table until there is somebody to deal it to.

    Held rather than ended: a game of two whose second player is reloading has
    nothing wrong with it, and `resync` deals as soon as they are back. The
    table is cleared either way, so a held table shows an empty one rather than
    the last hand left lying on it.
    """
    table = _table(lobby)
    for seat in table.seats:
        seat.committed = seat.contributed = 0
        seat.folded = seat.all_in = seat.acted = False
        seat.answer_item_id = None
        seat.correct = None
        seat.won = 0
        seat.backing = None
        seat.side_stake = 0
        seat.sitting_out = not _dealt_in(lobby, seat)

    table.pot = 0
    table.current_bet = 0
    table.min_raise = BIG_BLIND
    table.big_blind = BIG_BLIND
    table.stage = PokerStage.preflop
    table.to_act = None
    table.result = None
    table.acts_by = None
    table.answers_by = None
    table.next_hand_at = None

    if sum(1 for seat in table.seats if not seat.sitting_out) < 2:
        return

    round_ = deal_board(lobby.rounds[lobby.round_index])
    lobby.current_round = round_
    options = [item.id for item in round_.items]
    random.shuffle(options)

    table.question_category_id = _pick_question(round_)
    table.option_ids = options

    table.button = _next_seat(table, table.button)
    _post_blinds(table)
    if table.to_act is None:
        _next_stage(lobby)
    else:
        _arm_act_clock(lobby)
    _sync_players(lobby)
    lobby.touch()


def _post_blinds(table: PokerTable) -> None:
    """Put the blinds up and decide who is first to speak.

    Heads-up runs on poker's own exception: the button posts the small blind and
    acts first on the opening round, and last on every one after it.
    """
    live = [i for i, seat in enumerate(table.seats) if seat.in_hand()]
    if len(live) < 2:
        table.to_act = None
        return

    if len(live) == 2:
        small, big = table.button, _next_seat(table, table.button)
        first = table.button
    else:
        small = _next_seat(table, table.button)
        big = _next_seat(table, small)
        first = _next_seat(table, big)

    _commit(table.seats[small], SMALL_BLIND)
    _commit(table.seats[big], BIG_BLIND)
    table.current_bet = BIG_BLIND
    table.to_act = first if table.seats[first].can_act() else _next_actor(table, first)


def _pick_question(round_: Round) -> UUID | None:
    """One category off the board, and only one that something answers.

    A board is trimmed before it is dealt, and a category whose answers were all
    trimmed away would be a question with no right answer.
    """
    answered = {item.category_id for item in round_.items if item.category_id}
    askable = [c.id for c in round_.categories if c.id in answered]
    return random.choice(askable) if askable else None


# ---------------------------------------------------------------------------
# Betting
# ---------------------------------------------------------------------------


def _commit(seat: PokerSeat, amount: int) -> int:
    """Move chips from a stack to the table, never more than the stack holds."""
    paid = max(0, min(amount, seat.stack))
    seat.stack -= paid
    seat.committed += paid
    seat.contributed += paid
    if seat.stack == 0:
        seat.all_in = True
    return paid


def _raise_to(table: PokerTable, seat: PokerSeat, target: int) -> None:
    """Put in enough to have `target` on the table this street.

    A raise smaller than the last one is only allowed as a shove -- a player out
    of chips can always put the rest in, but doing so does not reopen the
    betting for anyone who has already acted.
    """
    shove = target == seat.committed + seat.stack
    if target > seat.committed + seat.stack:
        raise ValidationError("You do not have that many chips.")
    if target <= table.current_bet and not shove:
        raise ValidationError(f"A raise has to beat {table.current_bet}.")
    if target < table.current_bet + table.min_raise and not shove:
        raise ValidationError(
            f"A raise has to be to at least {table.current_bet + table.min_raise}."
        )

    _commit(seat, target - seat.committed)
    if target > table.current_bet:
        if target - table.current_bet >= table.min_raise:
            table.min_raise = target - table.current_bet
            for other in table.seats:
                if other is not seat and other.can_act():
                    other.acted = False
        table.current_bet = target


def _after_act(lobby: Lobby) -> None:
    table = _table(lobby)
    live = [seat for seat in table.seats if seat.in_hand()]
    if len(live) <= 1:
        _uncontested(lobby, live[0] if live else None)
        return

    if _betting_done(table):
        _next_stage(lobby)
        return

    table.to_act = _next_actor(table, table.to_act)
    _arm_act_clock(lobby)
    _sync_players(lobby)
    lobby.touch()


def _betting_done(table: PokerTable) -> bool:
    """Has everyone who can still bet acted, and matched the bet?

    True with nobody left to act, which is how a table that is all in gets the
    rest of the question without being asked to bet on it.
    """
    return all(
        seat.acted and seat.committed == table.current_bet
        for seat in table.seats
        if seat.can_act()
    )


def _next_stage(lobby: Lobby) -> None:
    """Gather the street's chips and let the question say one thing more."""
    table = _table(lobby)
    _collect(table)
    table.stage = ORDER[ORDER.index(table.stage) + 1]

    if table.stage is PokerStage.answering:
        table.to_act = None
        table.acts_by = None
        table.answers_by = datetime.now(UTC) + timedelta(seconds=lobby.turn_seconds)
        _sync_players(lobby)
        lobby.touch()
        return

    if sum(1 for seat in table.seats if seat.can_act()) < 2:
        _next_stage(lobby)
        return

    table.to_act = _next_actor(table, table.button)
    _arm_act_clock(lobby)
    _sync_players(lobby)
    lobby.touch()


def _collect(table: PokerTable) -> None:
    for seat in table.seats:
        table.pot += seat.committed
        seat.committed = 0
        seat.acted = False
    table.current_bet = 0
    table.min_raise = table.big_blind


def _arm_act_clock(lobby: Lobby) -> None:
    table = _table(lobby)
    table.acts_by = (
        datetime.now(UTC) + timedelta(seconds=lobby.turn_seconds)
        if table.to_act is not None
        else None
    )


def _act_on_the_clock(lobby: Lobby) -> None:
    """Play for whoever ran out of time: check if it is free, fold if it is not.

    The cheapest move that is never a bluff. Folding a player who could have
    checked would cost them a hand they had already paid for, and calling for
    them would spend chips they never agreed to spend.
    """
    table = _table(lobby)
    if table.to_act is None:
        return
    seat = table.seats[table.to_act]
    if table.current_bet > seat.committed:
        seat.folded = True
    seat.acted = True
    _after_act(lobby)


def _fold_the_departed(lobby: Lobby) -> None:
    """Fold anyone who has left the lobby outright, so the table is not held up."""
    present = {player.id for player in lobby.players}
    table = _table(lobby)
    gone = [
        seat for seat in table.seats if seat.in_hand() and seat.player_id not in present
    ]
    if not gone:
        return
    for seat in gone:
        seat.folded = True
        seat.acted = True
    if table.to_act is not None and table.seats[table.to_act] in gone:
        _after_act(lobby)
    else:
        lobby.touch()


# ---------------------------------------------------------------------------
# Paying out
# ---------------------------------------------------------------------------


def _resolve(lobby: Lobby) -> None:
    """Grade the answers and push the pot to whoever got it right."""
    table = _table(lobby)
    round_ = lobby.current_round
    correct = (
        {item.id for item in round_.items if item.category_id == table.question_category_id}
        if round_
        else set()
    )

    for seat in table.seats:
        if seat.in_hand():
            seat.correct = seat.answer_item_id in correct

    right = {seat.player_id for seat in table.seats if seat.correct}

    _collect(table)
    carried, table.carried = table.carried, 0
    dead = _lost_stakes(table, right)
    pots = _pots(table)
    if pots:
        pots[0] = (pots[0][0] + carried + dead, pots[0][1])
    else:
        table.carried = carried + dead

    awards: dict[UUID, int] = {}
    for amount, eligible in pots:
        winners = [seat for seat in eligible if seat.correct]
        if not winners:
            table.carried += amount
            continue
        for seat, won in _split(table, amount, winners).items():
            awards[seat] = awards.get(seat, 0) + won

    _pay_backers(table, awards, right)
    _credit(table, awards)
    _finish_hand(lobby, correct_ids=correct, awards=awards, uncontested=False)


def _uncontested(lobby: Lobby, winner: PokerSeat | None) -> None:
    """Everyone else folded. The pot goes without a question being asked.

    The side bets are still settled: whoever backed the last player standing
    backed the player who took the pot, however it was taken.
    """
    table = _table(lobby)
    _collect(table)
    right = {winner.player_id} if winner is not None else set()
    total = table.pot + table.carried + _lost_stakes(table, right)
    table.pot = 0
    table.carried = 0

    awards: dict[UUID, int] = {}
    if winner is not None:
        awards[winner.player_id] = total
        _pay_backers(table, awards, right)
        _credit(table, awards)
    else:
        table.carried = total

    round_ = lobby.current_round
    correct = (
        {item.id for item in round_.items if item.category_id == table.question_category_id}
        if round_
        else set()
    )
    _finish_hand(lobby, correct_ids=correct, awards=awards, uncontested=True)


def _finish_hand(
    lobby: Lobby, *, correct_ids: set[UUID], awards: dict[UUID, int], uncontested: bool
) -> None:
    table = _table(lobby)
    round_ = lobby.current_round
    answers = [item for item in (round_.items if round_ else []) if item.id in correct_ids]

    table.stage = PokerStage.payout
    table.to_act = None
    table.acts_by = None
    table.answers_by = None
    table.next_hand_at = datetime.now(UTC) + timedelta(seconds=PAYOUT_SECONDS)
    table.result = PokerResult(
        correct_item_ids=[item.id for item in answers],
        correct_labels=[item.label for item in answers],
        explanation=next((i.explanation for i in answers if i.explanation), None),
        awards=[
            PokerAward(player_id=player_id, amount=amount)
            for player_id, amount in awards.items()
        ],
        carried=table.carried,
        uncontested=uncontested,
    )
    _sync_players(lobby)
    lobby.touch()


def _lost_stakes(table: PokerTable, right: set[UUID]) -> int:
    """The side bets that backed the wrong player. Their chips join the pot."""
    return sum(
        seat.side_stake
        for seat in table.seats
        if seat.backing is not None and seat.backing not in right
    )


def _pay_backers(table: PokerTable, awards: dict[UUID, int], right: set[UUID]) -> None:
    """Hand the winning backers their stake back and their cut of the winnings.

    Taken out of the award rather than added beside it, so backing someone can
    never make a pot bigger than the chips that were put in it -- the player who
    answered simply takes home nine tenths of it instead of all of it.
    """
    behind: dict[UUID, list[PokerSeat]] = {}
    for seat in table.seats:
        if seat.backing is None or seat.backing not in right:
            continue
        seat.stack += seat.side_stake
        behind.setdefault(seat.backing, []).append(seat)

    for backed, backers in behind.items():
        cut = awards.get(backed, 0) // SIDE_BET_SHARE
        if cut <= 0:
            continue
        awards[backed] -= cut
        share, odd = divmod(cut, len(backers))
        for index, seat in enumerate(backers):
            paid = share + (1 if index < odd else 0)
            awards[seat.player_id] = awards.get(seat.player_id, 0) + paid


def _credit(table: PokerTable, awards: dict[UUID, int]) -> None:
    """Move the settled awards onto the stacks they were won by."""
    for seat in table.seats:
        seat.won = awards.get(seat.player_id, 0)
        seat.stack += seat.won
    table.pot = 0


def _pots(table: PokerTable) -> list[tuple[int, list[PokerSeat]]]:
    """The pot, split into the layers different players can win.

    One layer per all-in size. A player who put in 20 against two who put in 100
    can win 60 of it and no more, and the 160 above their head is played for by
    the two who covered it -- folded chips included, since those are in the pot
    whoever ends up taking it.
    """
    levels = sorted({seat.contributed for seat in table.seats if seat.contributed > 0})
    layers: list[tuple[int, list[PokerSeat]]] = []
    floor = 0
    for level in levels:
        amount = sum(
            min(seat.contributed, level) - min(seat.contributed, floor)
            for seat in table.seats
        )
        eligible = [
            seat for seat in table.seats if seat.in_hand() and seat.contributed >= level
        ]
        layers.append((amount, eligible))
        floor = level
    return layers


def _split(table: PokerTable, amount: int, winners: list[PokerSeat]) -> dict[UUID, int]:
    """Share a pot out, odd chips going left of the button as poker does."""
    share, odd = divmod(amount, len(winners))
    awards = {seat.player_id: share for seat in winners}
    for seat in sorted(winners, key=lambda s: _from_button(table, s))[:odd]:
        awards[seat.player_id] += 1
    return awards


def _next_hand(lobby: Lobby) -> None:
    """Deal the next hand, or end the game if this was the last one."""
    lobby.round_index += 1
    playing = sum(1 for seat in _table(lobby).seats if not _busted(lobby, seat))
    if lobby.round_index >= len(lobby.rounds) or playing < 2:
        lobby.round_index = min(lobby.round_index, len(lobby.rounds) - 1)
        lobby.status = LobbyStatus.finished
        _table(lobby).next_hand_at = None
        _sync_players(lobby)
        lobby.touch()
        return
    _start_hand(lobby)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _table(lobby: Lobby) -> PokerTable:
    if lobby.poker is None:
        raise ConflictError("This lobby is not playing poker.")
    return lobby.poker


def _dealt_in(lobby: Lobby, seat: PokerSeat) -> bool:
    """Chips, and somebody there to play them."""
    return _connected(lobby, seat.player_id) and seat.stack > 0


def _connected(lobby: Lobby, player_id: UUID) -> bool:
    player = next((p for p in lobby.players if p.id == player_id), None)
    return player is not None and player.is_connected


def _busted(lobby: Lobby, seat: PokerSeat) -> bool:
    return seat.stack <= 0 or not any(p.id == seat.player_id for p in lobby.players)


def _next_seat(table: PokerTable, index: int) -> int:
    """The next seat in the hand, wrapping. `index` itself if it is the only one."""
    count = len(table.seats)
    for step in range(1, count + 1):
        candidate = (index + step) % count
        if table.seats[candidate].in_hand():
            return candidate
    return index


def _next_actor(table: PokerTable, index: int | None) -> int | None:
    """The next seat that can still put chips in, or None if nobody can."""
    if index is None:
        return None
    count = len(table.seats)
    for step in range(1, count + 1):
        candidate = (index + step) % count
        if table.seats[candidate].can_act():
            return candidate
    return None


def _from_button(table: PokerTable, seat: PokerSeat) -> int:
    return (table.seats.index(seat) - table.button) % len(table.seats)


def _seat_id(table: PokerTable, index: int | None) -> UUID | None:
    return table.seats[index].player_id if index is not None else None


def _seconds_left(table: PokerTable) -> int | None:
    deadline = (
        table.acts_by
        if table.stage in BETTING
        else table.answers_by
        if table.stage is PokerStage.answering
        else table.next_hand_at
    )
    if deadline is None:
        return None
    return max(0, ceil((deadline - datetime.now(UTC)).total_seconds()))


def _sync_players(lobby: Lobby) -> None:
    """Chips are the score, and a folded player is out of the hand.

    Both are things the lobby already knows how to show -- the scoreboard and
    the dimmed player -- so poker says what it means in those terms rather than
    growing a second set of them.
    """
    table = _table(lobby)
    for player in lobby.players:
        seat = table.seat(player.id)
        if seat is None:
            continue
        player.score = seat.stack
        player.is_active = seat.in_hand()


def _question(table: PokerTable, round_: Round | None, *, revealed: bool):
    """The category being asked, named unless naming it would answer it.

    A picture question asks with the photograph, and printing the caption over
    it -- "Rhein", above a photograph of the Rhine -- would be the answer.
    """
    if round_ is None:
        return None
    category = next(
        (c for c in round_.categories if c.id == table.question_category_id), None
    )
    if category is None:
        return None
    if round_.category_kind is CategoryKind.image and not revealed:
        return category.model_copy(update={"label": None})
    return category


def _options(table: PokerTable, round_: Round | None) -> list[ItemPublic]:
    """The answers on offer, in the order this hand fixed for them.

    Held back until the betting is done -- see `view`. A list of twelve answers
    is most of a question, and putting it up beside the last bet would turn that
    bet into "can I spot it" rather than "do I know it".
    """
    if round_ is None:
        return []
    by_id = {item.id: item for item in round_.items}
    return [
        ItemPublic(id=item_id, label=by_id[item_id].label)
        for item_id in table.option_ids
        if item_id in by_id
    ]
