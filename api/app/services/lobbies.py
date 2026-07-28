"""Ephemeral multiplayer lobbies -- the game rules, and nothing about storage.

A lobby never outlives the game it belongs to. That is deliberate: the database
stores questions, never who played them. Nicknames, scores and turn order exist
only for the lifetime of a game, and the store expires them on its own.

Where they are kept is `lobby_store`'s problem, not this module's. Every
read-modify-write below opens the same way:

    with _mutate(code) as lobby:
        ...

which holds that lobby exclusively for the block and writes it back at the end.
Two things follow, and both matter:

* Route handlers are plain `def`, so FastAPI runs them in a threadpool and two
  players can submit at the same instant. The block is what keeps one from
  overwriting the other.
* Whatever the block changed is written back even if it then raised. That is
  what makes a refused request still count as proof the client is alive: every
  entry point records the heartbeat before it validates, and dropping that on
  rejection would disconnect players for making moves the rules turned down.

With the shared store behind it this works on a horizontally scaled or
serverless host, where consecutive requests from one player land on different
instances. With the in-process store it needs a single long-lived process.
"""

import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID, uuid4

from app.errors import ConflictError, ValidationError
from app.schemas import (
    FinishedRound,
    ItemPublic,
    LastMove,
    LobbyStatus,
    LobbyView,
    PlayerPublic,
    ResolvedPair,
    RoundView,
    SolvedItem,
)
from app.services.drafting import draw_balanced
from app.services.lobby_state import Lobby, Player, Round
from app.services import realtime
from app.services.lobby_store import LOBBY_TTL, build_store
from app.services.quizzes import (
    get_quiz_solution,
    list_subjects,
    pools_by_subject,
    source_of,
)
from app.services.scoring import grade_item

# Re-exported: callers and tests build these, and moving them was a storage
# concern rather than a change to what a lobby is.
__all__ = ["Lobby", "Player", "Round"]

# Ambiguous characters left out so a code can be read aloud without confusion.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 4
MAX_PLAYERS = 10

# How many placements the round's running commentary keeps. A round cannot have
# many more than this -- ten pairs plus a knockout each -- so it is a ceiling
# rather than a window in practice.
MAX_HISTORY = 20

# Changes arrive by push, so the client's poll is no longer how it learns what
# happened -- it is the heartbeat, and the backstop for anything push misses.
# It runs every ~4s (POLL_MS in the lobby room) and these are scaled to that:
# a player has to miss several beats before the others are told anything.
#
# The poll was briefly 10s, tuned against a cache that billed per command. The
# store is Postgres now and nothing meters round trips, so the only reason to
# poll slowly was gone -- and a slow poll is what everything unresponsive about
# the game traced back to.
PRESENCE_TIMEOUT = timedelta(seconds=15)

# How long the player on the clock may be silent before the others are told
# something is up. Long enough to survive one missed poll, short enough that the
# wait before a skip is explained rather than mysterious. Must stay below
# PRESENCE_TIMEOUT or it could never fire.
QUIET_AFTER = timedelta(seconds=6)

# How long the finished round's answers stay up before the next round starts.
# Timed rather than host-gated so nobody can stall the table by walking away --
# the same reasoning as PRESENCE_TIMEOUT. The host can cut it short.
REVIEW_SECONDS = 10
REVIEW_FOR = timedelta(seconds=REVIEW_SECONDS)


# The one instance the whole API shares. Built from configuration: shared
# lobbies live in the database and are visible to every instance, otherwise this
# process holds them. Nothing else in this module knows the difference.
_store = build_store()


def store():
    """The live store. Exposed so tests can reach a lobby the same way the
    game does, rather than reaching into a dict that may not exist."""
    return _store


@contextmanager
def _mutate(code: str):
    """Open a lobby for writing, and tell the other players afterwards.

    Wraps the store's own context manager to add one thing: if the block
    actually changed the lobby, a notification goes out once the lobby has been
    released.

    Two details are deliberate.

    *After* the block, not inside it. Publishing is an HTTP call; doing it while
    still holding the lobby would make every other player queue behind an
    unrelated network round trip.

    Only when `version` moved. `touch()` is what marks a real change, and
    polling calls `get_view` constantly without changing anything -- announcing
    those would put back exactly the chatter this exists to remove.
    """
    announce: LobbyView | None = None
    with _store.mutate(code) as lobby:
        before = lobby.version
        yield lobby
        if lobby.version != before:
            announce = _view(lobby)

    if announce is not None:
        realtime.publish(announce)


@contextmanager
def _mutate_if_present(code: str):
    """As `_mutate`, for the paths where a missing lobby is not an error."""
    announce: LobbyView | None = None
    with _store.mutate_if_present(code) as lobby:
        before = lobby.version if lobby else None
        yield lobby
        if lobby is not None and lobby.version != before:
            announce = _view(lobby)

    if announce is not None:
        realtime.publish(announce)


def edit(code: str):
    """Open a lobby for modification outside the game rules.

    Only tests use this -- to backdate a timestamp and simulate a player going
    quiet, or a review running out. It goes through the store so it works
    whichever one is in use.
    """
    return _store.mutate(code)


# ---------------------------------------------------------------------------
# Lobby lifecycle
# ---------------------------------------------------------------------------


def create_lobby(nickname: str) -> tuple[str, UUID]:
    code = _unique_code()
    host = Player(id=uuid4(), nickname=nickname.strip(), is_host=True)
    _store.create(Lobby(code=code, players=[host]))
    return code, host.id


def join_lobby(code: str, nickname: str) -> UUID:
    """Join a lobby, or reclaim a seat you were disconnected from.

    Reclaiming is what makes "close the tab, open the link again" work from a
    fresh browser, where localStorage no longer holds the player id. The
    nickname is the only credential, which is fine for a party game but means
    anyone who knows the code and a name can take that seat.
    """
    with _mutate(code) as lobby:
        _refresh_presence(lobby)
        cleaned = nickname.strip()

        existing = next(
            (p for p in lobby.players if p.nickname.casefold() == cleaned.casefold()),
            None,
        )
        if existing is not None:
            if existing.is_connected:
                raise ConflictError(f"'{cleaned}' is already taken in this lobby.")
            # Same person coming back: keep their score and their place in the
            # turn order rather than handing out a new seat.
            _heartbeat(lobby, existing.id)
            _resync(lobby)
            lobby.touch()
            return existing.id

        if lobby.status is not LobbyStatus.lobby:
            raise ConflictError("This game has already started.")
        if len(lobby.players) >= MAX_PLAYERS:
            raise ConflictError(f"This lobby is full ({MAX_PLAYERS} players).")

        player = Player(id=uuid4(), nickname=cleaned)
        lobby.players.append(player)
        lobby.touch()
        return player.id


def start_game(
    code: str,
    player_id: UUID,
    subject_slugs: list[str],
    round_count: int = 5,
    turn_seconds: int = 30,
) -> LobbyView:
    """Begin a game drawn from the chosen subjects.

    The host picks areas and a length, not specific questions -- which ones come
    up is decided here, spread evenly across the subjects.
    """
    with _mutate(code) as lobby:
        player = lobby.player(player_id)
        _heartbeat(lobby, player_id)
        _refresh_presence(lobby)
        if not player.is_host:
            raise ConflictError("Only the host can start the game.")
        if lobby.status in (LobbyStatus.playing, LobbyStatus.reviewing):
            raise ConflictError("This game is already running.")
        if len(lobby.players) < 2:
            raise ConflictError("At least two players are needed to start.")

        pools = pools_by_subject(subject_slugs)
        if not pools:
            raise ConflictError("The chosen subjects contain no questions.")

        # One more than asked for: the last is held back for the settling round
        # at the end, which is only played if the arithmetic left someone short.
        # A pool with nothing spare simply yields no extra, and then there is no
        # settling round -- which is why this is drawn rather than required.
        drawn = draw_balanced(pools, round_count + 1)
        quiz_slugs = drawn[:round_count]
        spare_slug = drawn[round_count] if len(drawn) > round_count else None
        subject_names = _subject_names(subject_slugs)

        # Load every question up front, so a content problem surfaces now
        # rather than halfway through a game.
        rounds = [_load_round(slug) for slug in quiz_slugs]
        lobby.catch_up_round = _load_round(spare_slug) if spare_slug else None

        lobby.subject_names = subject_names
        lobby.quiz_slugs = quiz_slugs
        lobby.rounds = rounds
        lobby.status = LobbyStatus.playing
        lobby.round_index = 0
        lobby.last_move = None
        lobby.turn_seconds = turn_seconds
        lobby.turn_credits = {}
        lobby.in_catch_up = False
        lobby.catch_up_left = {}
        for candidate in lobby.players:
            candidate.score = 0
        _begin_round(lobby, rounds[0])
        lobby.touch()
        return _view(lobby)


def reset_to_lobby(code: str, player_id: UUID) -> LobbyView:
    """Send a finished game back to the waiting room, keeping the players."""
    with _mutate(code) as lobby:
        if not lobby.player(player_id).is_host:
            raise ConflictError("Only the host can restart.")

        lobby.status = LobbyStatus.lobby
        lobby.current_round = None
        lobby.rounds = []
        lobby.subject_names = []
        lobby.finished_rounds = []
        lobby.solved = {}
        lobby.turn_credits = {}
        lobby.catch_up_round = None
        lobby.in_catch_up = False
        lobby.catch_up_left = {}
        lobby.round_index = 0
        lobby.turn_cursor = 0
        lobby.review_until = None
        lobby.last_move = None
        for candidate in lobby.players:
            candidate.score = 0
            candidate.is_active = True
        lobby.touch()
        return _view(lobby)


def leave_lobby(code: str, player_id: UUID) -> LobbyView | None:
    """Remove a player. Returns None if that emptied the lobby.

    The awkward part is mid-game: `turn_cursor` is a position in `players`, so
    removing anyone re-indexes the list underneath it. Whoever should be on the
    clock afterwards is therefore resolved by identity *before* the removal and
    the cursor is rebuilt from that, rather than nudged.
    """
    with _mutate(code) as lobby:
        player = lobby.player(player_id)
        _refresh_presence(lobby)

        current = _current_player(lobby)
        current_id = current.id if current else None
        # Only needed when the leaver is the one on the clock, but it has to be
        # computed while they are still in the list for the rotation to be right.
        successor_id = _next_active_id(lobby, exclude=player_id)

        lobby.players.remove(player)

        if not lobby.players:
            emptied = True
        else:
            emptied = False

        if not emptied:
            # The host leaving must not leave the lobby unstartable.
            if not any(candidate.is_host for candidate in lobby.players):
                lobby.players[0].is_host = True

            if lobby.status is LobbyStatus.playing:
                keep_id = current_id if current_id and current_id != player_id else successor_id
                lobby.turn_cursor = _index_of(lobby, keep_id) if keep_id else 0
                # The leaver may have been the last active player, which ends
                # the round exactly as a wrong answer would.
                _maybe_finish_round(lobby)

            lobby.touch()
            view = _view(lobby)

    # Outside the block: the lobby has to be written back before it can be
    # dropped, and dropping it inside would leave the store writing a lobby it
    # had just been told to forget.
    if emptied:
        _store.delete(code)
        return None
    return view


def get_view(code: str, player_id: UUID | None = None) -> LobbyView:
    """Read lobby state, and treat the read as `player_id`'s heartbeat.

    Piggybacking presence on the poll the client already makes keeps the
    protocol to one endpoint: a tab that closes simply stops polling.
    """
    with _mutate(code) as lobby:
        _heartbeat(lobby, player_id)
        changed = _refresh_presence(lobby)
        before = (lobby.turn_cursor, lobby.round_index, lobby.status)
        _resync(lobby)
        # Only bump the version on a real change, or every poll would look like
        # new state to the clients.
        if changed or before != (lobby.turn_cursor, lobby.round_index, lobby.status):
            lobby.touch()
        return _view(lobby)


def skip_review(code: str, player_id: UUID) -> LobbyView:
    """Host cuts the between-rounds review short and starts the next round.

    Only shortens the wait -- it can never skip a review that has not started,
    so it cannot be used to rush players past a board that is still in play.
    """
    with _mutate(code) as lobby:
        player = lobby.player(player_id)
        _heartbeat(lobby, player_id)
        _refresh_presence(lobby)

        if not player.is_host:
            raise ConflictError("Only the host can start the next round.")
        if lobby.status is not LobbyStatus.reviewing:
            raise ConflictError("There is no review to skip.")

        _end_review(lobby)
        lobby.touch()
        return _view(lobby)


def mark_away(code: str, player_id: UUID) -> None:
    """Best-effort 'my tab is closing' signal.

    Optimisation only -- browsers do not guarantee an unload request goes out,
    so `PRESENCE_TIMEOUT` remains the mechanism that actually guarantees a
    vanished player stops holding up the game.
    """
    with _mutate_if_present(code) as lobby:
        if lobby is None:
            return
        for player in lobby.players:
            if player.id == player_id:
                player.marked_away = True
                player.is_connected = False
                _resync(lobby)
                lobby.touch()
                return


# ---------------------------------------------------------------------------
# Playing a turn
# ---------------------------------------------------------------------------


def submit_turn(
    code: str,
    player_id: UUID,
    item_id: UUID,
    category_id: UUID,
) -> LobbyView:
    """Place one item, then pass the turn on -- right or wrong.

    A wrong placement also knocks the player out for the rest of the round.
    """
    with _mutate(code) as lobby:
        player = lobby.player(player_id)
        _heartbeat(lobby, player_id)
        _refresh_presence(lobby)
        _resync(lobby)
        current = lobby.current_round

        if lobby.status is not LobbyStatus.playing or current is None:
            raise ConflictError("This game is not running.")
        if not player.is_active:
            raise ConflictError("You are out for this round.")

        active_player = _current_player(lobby)
        if active_player is None or active_player.id != player_id:
            raise ConflictError("It is not your turn.")

        if item_id in lobby.solved:
            raise ConflictError("That answer has already been placed.")

        answer_key = current.answer_key()
        if item_id not in answer_key:
            raise ValidationError("That answer does not belong to this topic.")
        if all(c.id != category_id for c in current.categories):
            raise ValidationError("That category does not belong to this topic.")

        was_correct = grade_item(
            assigned_category_id=category_id,
            correct_category_id=answer_key[item_id],
        )

        if was_correct:
            player.score += 1
            lobby.solved[item_id] = player.id
        else:
            player.is_active = False

        item = next(candidate for candidate in current.items if candidate.id == item_id)
        lobby.last_move = LastMove(
            player_id=player.id,
            nickname=player.nickname,
            item_label=item.label,
            category_id=category_id,
            was_correct=was_correct,
        )

        # Kept so the table can see how the round has gone, not just the last
        # thing that happened. Trimmed because the lobby is written back whole
        # on every mutation, and an unbounded list would grow the document for
        # the length of the game.
        lobby.history.append(lobby.last_move)
        del lobby.history[:-MAX_HISTORY]

        _spend_catch_up(lobby, player)
        _advance_turn(lobby)
        _arm_turn_clock(lobby)
        # A move resets the clock, so the previous player's expiry never lands
        # on the next one.
        lobby.timed_out = None
        _maybe_finish_round(lobby)
        lobby.touch()
        return _view(lobby)


# ---------------------------------------------------------------------------
# Round and turn mechanics
# ---------------------------------------------------------------------------


def _begin_round(lobby: Lobby, round_: Round) -> None:
    lobby.current_round = round_
    lobby.solved = {}
    lobby.timed_out = None
    lobby.history = []
    for player in lobby.players:
        player.is_active = True

    # Rotate the starting player each round so the same person is not always
    # first at the easy items.
    lobby.turn_cursor = lobby.round_index % max(len(lobby.players), 1)
    # After the cursor is set, because who is owed what depends on where the
    # rotation starts.
    _credit_turns(lobby)
    _arm_turn_clock(lobby)


def _arm_turn_clock(lobby: Lobby) -> None:
    """Start the clock for whoever is now on it, or stop it if nobody is.

    Called after every move of the turn rather than computed on read, so the
    deadline is a fact about the game rather than a function of when someone
    happened to ask.
    """
    if lobby.status is LobbyStatus.playing and _current_player(lobby) is not None:
        lobby.turn_expires_at = datetime.now(UTC) + timedelta(seconds=lobby.turn_seconds)
    else:
        lobby.turn_expires_at = None


def _enforce_turn_deadline(lobby: Lobby) -> bool:
    """Take the turn away from a player who has run out of time.

    Timing out costs the round, exactly as a wrong answer does. That is the
    harsher of the two options and it is deliberate: if running down the clock
    were free, waiting would always be safer than guessing, and a table of
    cautious players would never finish a round at all.

    Distinct from the presence timeout, which is about a client that has gone
    away. This one is for a player who is present and simply has not moved.
    """
    if lobby.turn_expires_at is None or datetime.now(UTC) < lobby.turn_expires_at:
        return False

    player = _current_player(lobby)
    if player is None:
        return False

    player.is_active = False
    # Spent even though the clock took it: the turn was theirs and they had it.
    # Not doing this would leave a credit outstanding in a settling round that
    # they can no longer play, and the round would have to end on the knockout
    # instead -- true here, but only by accident.
    _spend_catch_up(lobby, player)
    # Named so the table is told why the turn moved. `last_move` cannot say it:
    # a timeout has no item and no category, and making those optional to fit
    # would weaken a type that is right everywhere else.
    lobby.timed_out = player.nickname
    _advance_turn(lobby)
    _arm_turn_clock(lobby)
    return True


def _spend_catch_up(lobby: Lobby, player: Player) -> None:
    """Use up one of a player's owed turns, and retire them when they run out.

    No-op outside a settling round. Inside one, running out is expressed as
    being knocked out -- which is what keeps the rotation and the round-end
    check from needing to know this round is different.
    """
    if not lobby.in_catch_up:
        return

    left = lobby.catch_up_left.get(player.id, 0) - 1
    lobby.catch_up_left[player.id] = max(0, left)
    if left <= 0:
        player.is_active = False


def _advance_turn(lobby: Lobby) -> None:
    """Move the cursor to the next active player, if there is one."""
    count = len(lobby.players)
    if count == 0:
        return

    for step in range(1, count + 1):
        candidate = lobby.players[(lobby.turn_cursor + step) % count]
        if candidate.can_play():
            lobby.turn_cursor = (lobby.turn_cursor + step) % count
            return

    # Nobody left active. The cursor no longer matters; the round is over and
    # `_maybe_finish_round` is about to handle it.


def _refresh_presence(lobby: Lobby) -> bool:
    """Recompute who is still connected. Returns True if anything changed.

    Called at the top of every operation, so a player whose tab went away stops
    being dealt turns even though nothing in the game itself happened.
    """
    now = datetime.now(UTC)
    changed = False
    for player in lobby.players:
        connected = not player.marked_away and (now - player.last_seen) <= PRESENCE_TIMEOUT
        if connected != player.is_connected:
            player.is_connected = connected
            changed = True
    return changed


def _resync(lobby: Lobby) -> None:
    """Keep the clock on someone who can actually play.

    Without this a disconnected player would hold the turn forever: no one
    submits, so nothing would otherwise run to move it along.

    The review deadline rides on the same mechanism, and for the same reason:
    nobody submits anything during a review, so polling is the only thing that
    can notice it has run out.
    """
    if lobby.status is LobbyStatus.reviewing:
        if lobby.review_until is not None and datetime.now(UTC) >= lobby.review_until:
            _end_review(lobby)
        return
    if lobby.status is not LobbyStatus.playing:
        return
    if _current_player(lobby) is None:
        _advance_turn(lobby)
        _arm_turn_clock(lobby)
    # Nobody submits anything when a player simply stops playing, so -- like the
    # review deadline -- a request arriving is the only thing that can notice
    # the clock has run out.
    _enforce_turn_deadline(lobby)
    _maybe_finish_round(lobby)


def _heartbeat(lobby: Lobby, player_id: UUID | None) -> None:
    """Record that a player's client is still there."""
    if player_id is None:
        return
    for player in lobby.players:
        if player.id == player_id:
            player.last_seen = datetime.now(UTC)
            player.marked_away = False
            player.is_connected = True
            return


def _next_active_id(lobby: Lobby, *, exclude: UUID | None = None) -> UUID | None:
    """Who plays after the cursor, ignoring `exclude`. Identity, not position."""
    count = len(lobby.players)
    for step in range(1, count + 1):
        candidate = lobby.players[(lobby.turn_cursor + step) % count]
        if candidate.can_play() and candidate.id != exclude:
            return candidate.id
    return None


def _index_of(lobby: Lobby, player_id: UUID) -> int:
    for index, candidate in enumerate(lobby.players):
        if candidate.id == player_id:
            return index
    return 0


def _current_player(lobby: Lobby) -> Player | None:
    if not lobby.players:
        return None
    player = lobby.players[lobby.turn_cursor % len(lobby.players)]
    return player if player.can_play() else None


def _solution_of(current: Round, solved: dict[UUID, UUID]) -> list[ResolvedPair]:
    """The finished round's answer key, in the categories' own order.

    Built at the moment the round ends rather than read back later: `Round` is
    dropped as soon as the next one begins, and this is the only record of what
    the answers were.
    """
    by_category = {item.category_id: item for item in current.items}

    return [
        ResolvedPair(
            category_label=category.label,
            item_label=item.label,
            explanation=item.explanation,
            solved_by=solved.get(item.id),
        )
        for category in current.categories
        if (item := by_category.get(category.id)) is not None
    ]


def _credit_turns(lobby: Lobby) -> None:
    """Record how many turns this round's rotation owes each seat.

    Turns go round the table one placement at a time, so unless the board size
    divides by the player count the seats at the front of the order are asked
    more questions than the ones at the back. With eleven pairs and four
    players the first three seats get three turns and the fourth gets two --
    an extra scoring chance handed out by arithmetic rather than by play.

    This is the ledger for that, and it is written when the round *starts*,
    from the board and the rotation offset alone. Nothing that happens during
    the round changes it: a player knocked out on their first answer is still
    credited the turns the rotation had for them, because losing those was the
    rules working. What is settled up afterwards is only ever the arithmetic.
    """
    current = lobby.current_round
    count = len(lobby.players)
    if current is None or count == 0:
        return

    base, extra = divmod(len(current.items), count)
    for offset in range(count):
        player = lobby.players[(lobby.turn_cursor + offset) % count]
        owed = base + (1 if offset < extra else 0)
        lobby.turn_credits[player.id] = lobby.turn_credits.get(player.id, 0) + owed


def _catch_up_owed(lobby: Lobby) -> dict[UUID, int]:
    """Turns each player is short of the best-served seat. Empty when level.

    Only players still in the lobby -- someone who left is owed nothing, and
    including them would keep a settling round open for a seat nobody is in.
    """
    present = {player.id for player in lobby.players}
    credits = {
        player_id: got
        for player_id, got in lobby.turn_credits.items()
        if player_id in present
    }
    if not credits:
        return {}

    best = max(credits.values())
    return {pid: best - got for pid, got in credits.items() if got < best}


def _maybe_finish_round(lobby: Lobby) -> None:
    """End the round when every item is placed, or nobody is left to place one."""
    current = lobby.current_round
    if current is None:
        return

    # If every last player has vanished, freeze rather than racing through the
    # remaining rounds to a meaningless winner. Play resumes when someone
    # reconnects.
    if not any(player.is_connected for player in lobby.players):
        return

    all_solved = len(lobby.solved) == len(current.items)
    # Someone merely being disconnected must not stall the players who are
    # still here, so this asks who *can* play, not who is nominally active.
    nobody_can_play = not any(player.can_play() for player in lobby.players)
    if not (all_solved or nobody_can_play):
        return

    lobby.finished_rounds.append(
        FinishedRound(
            quiz_id=current.quiz_id,
            slug=current.slug,
            title=current.title,
            difficulty=current.difficulty,
            source=current.source,
            solution=_solution_of(current, lobby.solved),
        )
    )

    if not _has_another_round(lobby):
        lobby.status = LobbyStatus.finished
        lobby.current_round = None
        lobby.review_until = None
        lobby.in_catch_up = False
        lobby.catch_up_left = {}
        return

    # `current_round` deliberately stays loaded: the board with its answers in
    # place is what the explanations are shown underneath.
    lobby.status = LobbyStatus.reviewing
    lobby.review_until = datetime.now(UTC) + REVIEW_FOR


def _has_another_round(lobby: Lobby) -> bool:
    """Is there anything to play after the one that just ended?

    Either another question from the game's draw, or -- once those are gone --
    the settling round, if the arithmetic left anybody short.
    """
    if lobby.round_index + 1 < len(lobby.rounds):
        return True
    if lobby.in_catch_up or lobby.catch_up_round is None:
        return False
    return bool(_catch_up_owed(lobby))


def _end_review(lobby: Lobby) -> None:
    """Leave the review and start whatever comes next."""
    lobby.review_until = None
    lobby.status = LobbyStatus.playing

    if lobby.round_index + 1 < len(lobby.rounds):
        lobby.round_index += 1
        _begin_round(lobby, lobby.rounds[lobby.round_index])
        return

    _begin_catch_up(lobby)


def _begin_catch_up(lobby: Lobby) -> None:
    """Start the short settling round that evens out the turns.

    Everyone the arithmetic short-changed over the game gets exactly the turns
    they were missing, and nobody else plays. It is one board like any other,
    but most of it goes unplayed -- with four players and five rounds the whole
    thing is usually two or three placements.

    The mechanism is deliberately the knockout flag rather than a new one.
    Players with nothing owed are simply not active for this round, so the
    existing rotation skips them, `_maybe_finish_round` ends the round when the
    last owed turn is spent, and none of that machinery had to learn about
    settling rounds at all.
    """
    owed = _catch_up_owed(lobby)
    if not owed or lobby.catch_up_round is None:
        # `_has_another_round` already refused both of these, so reaching here
        # means the two disagree. Ending the game is the safe reading -- an
        # `assert` would be stripped under -O and leave `current_round` None in
        # a lobby that believes it is playing.
        lobby.status = LobbyStatus.finished
        lobby.current_round = None
        lobby.in_catch_up = False
        lobby.catch_up_left = {}
        return

    lobby.in_catch_up = True
    lobby.catch_up_left = dict(owed)
    lobby.current_round = lobby.catch_up_round
    lobby.solved = {}
    lobby.timed_out = None
    lobby.history = []

    for player in lobby.players:
        player.is_active = owed.get(player.id, 0) > 0

    # Whoever is furthest behind opens it. Any seat would do -- everyone here
    # plays a fixed number of turns whatever the order -- but starting with the
    # player who was short-changed most reads as the point of the round.
    lobby.turn_cursor = 0
    ranked = sorted(owed.items(), key=lambda pair: -pair[1])
    if ranked:
        lobby.turn_cursor = _index_of(lobby, ranked[0][0])
    if _current_player(lobby) is None:
        _advance_turn(lobby)
    _arm_turn_clock(lobby)


def _subject_names(subject_slugs: list[str]) -> list[str]:
    """Display names for the chosen subjects, so the lobby can show them."""
    by_slug = {subject.slug: subject.name for subject in list_subjects()}
    return [by_slug[slug] for slug in subject_slugs if slug in by_slug]


def _load_round(slug: str) -> Round:
    row, categories, items = get_quiz_solution(slug)
    return Round(
        quiz_id=UUID(row["id"]),
        slug=row["slug"],
        title=row["title"],
        description=row.get("description"),
        difficulty=row["difficulty"],
        source=source_of(row),
        categories=categories,
        items=items,
    )


# ---------------------------------------------------------------------------
# Views -- everything below must be safe to send to a player
# ---------------------------------------------------------------------------


def _view(lobby: Lobby) -> LobbyView:
    # Nobody is on the clock unless a round is actually running. Without this
    # the cursor would still name a player during the between-rounds review,
    # and their client would arm the board against a round that is over.
    current_player = _current_player(lobby) if lobby.status is LobbyStatus.playing else None
    # Who is up after them, so a player can see their turn coming rather than
    # only discovering it has arrived. None when they would be up again
    # themselves, which is not "next" in any useful sense.
    next_player_id = _next_active_id(lobby, exclude=None) if current_player else None
    if next_player_id == (current_player.id if current_player else None):
        next_player_id = None
    return LobbyView(
        next_player_id=next_player_id,
        is_catch_up=lobby.in_catch_up,
        catch_up_left=dict(lobby.catch_up_left),
        current_player_quiet=_is_quiet(lobby, current_player),
        code=lobby.code,
        status=lobby.status,
        players=[
            PlayerPublic(
                id=p.id,
                nickname=p.nickname,
                score=p.score,
                is_active=p.is_active,
                is_connected=p.is_connected,
                is_host=p.is_host,
            )
            for p in lobby.players
        ],
        quiz_slugs=lobby.quiz_slugs,
        subject_names=lobby.subject_names,
        round_index=lobby.round_index,
        round_count=len(lobby.quiz_slugs),
        current_player_id=current_player.id if current_player else None,
        review_seconds_left=_review_seconds_left(lobby),
        turn_seconds_left=_turn_seconds_left(lobby),
        turn_seconds=lobby.turn_seconds if current_player else None,
        timed_out=lobby.timed_out,
        history=list(lobby.history),
        round_view=_round_view(lobby),
        finished_rounds=list(lobby.finished_rounds),
        last_move=lobby.last_move,
        winner_ids=_winner_ids(lobby),
        version=lobby.version,
    )


def _review_seconds_left(lobby: Lobby) -> int | None:
    """Seconds until the next round starts, or None when not reviewing.

    Sent as a remaining duration rather than a wall-clock deadline so a client
    whose clock is off still counts down correctly.
    """
    if lobby.status is not LobbyStatus.reviewing or lobby.review_until is None:
        return None
    left = (lobby.review_until - datetime.now(UTC)).total_seconds()
    return max(0, ceil(left))


def _turn_seconds_left(lobby: Lobby) -> int | None:
    """How long the player on the clock has left, or None if nobody is on it."""
    if lobby.status is not LobbyStatus.playing or lobby.turn_expires_at is None:
        return None
    if _current_player(lobby) is None:
        return None
    return max(0, ceil((lobby.turn_expires_at - datetime.now(UTC)).total_seconds()))


def _is_quiet(lobby: Lobby, current_player: Player | None) -> bool:
    """Has the player on the clock gone silent, without having timed out yet?

    Exists purely so the other players are told why nothing is happening. Once
    the silence passes PRESENCE_TIMEOUT the turn is handed on and there is no
    longer anything to explain, so this goes false on its own.
    """
    if lobby.status is not LobbyStatus.playing or current_player is None:
        return False
    return datetime.now(UTC) - current_player.last_seen > QUIET_AFTER


def _round_view(lobby: Lobby) -> RoundView | None:
    current = lobby.current_round
    if current is None:
        return None

    # Unsolved items carry no category: that is still the answer. Only items
    # already placed correctly reveal where they belong.
    return RoundView(
        quiz_id=current.quiz_id,
        slug=current.slug,
        title=current.title,
        description=current.description,
        difficulty=current.difficulty,
        categories=current.categories,
        remaining_items=[
            ItemPublic(id=item.id, label=item.label)
            for item in current.items
            if item.id not in lobby.solved
        ],
        solved_items=[
            SolvedItem(
                item_id=item.id,
                label=item.label,
                category_id=item.category_id,
                solved_by=lobby.solved[item.id],
            )
            for item in current.items
            if item.id in lobby.solved
        ],
    )


def _winner_ids(lobby: Lobby) -> list[UUID]:
    """Everyone tied at the top. Empty until the game is actually over."""
    if lobby.status is not LobbyStatus.finished or not lobby.players:
        return []
    best = max(player.score for player in lobby.players)
    return [player.id for player in lobby.players if player.score == best]


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------


def _unique_code() -> str:
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not _store.exists(code):
            return code
    raise ConflictError("Could not allocate a lobby code. Try again.")


def _reset_store_for_tests() -> None:
    _store.clear()
