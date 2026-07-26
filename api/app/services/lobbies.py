"""Ephemeral multiplayer lobbies.

Everything here lives in the API process and disappears on restart. That is
deliberate: the database stores questions, never who played them. Nicknames,
scores and turn order exist only for the lifetime of a game.

Consequences worth knowing:

* This requires a single long-lived process. It does NOT work on Vercel's
  serverless Python runtime, where each request may hit a different instance
  with its own empty dict. Deploy the API to a container host to use lobbies.
* Route handlers are plain `def`, so FastAPI runs them in a threadpool and two
  players can submit at the same instant. Every read-modify-write below is
  therefore guarded by a lock.
"""

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas import (
    Category,
    ItemPublic,
    ItemSolution,
    LastMove,
    LobbyStatus,
    LobbyView,
    PlayerPublic,
    RoundView,
    SolvedItem,
)
from app.services.drafting import draw_balanced
from app.services.quizzes import get_quiz_solution, list_subjects, pools_by_subject
from app.services.scoring import grade_item

# Ambiguous characters left out so a code can be read aloud without confusion.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 4
MAX_PLAYERS = 10
LOBBY_TTL = timedelta(hours=4)

# A client polls every ~1.5s, and that poll is the heartbeat. This allows
# several to be missed -- a flaky phone connection should not eject anyone --
# while still noticing a closed tab quickly enough not to stall a game.
PRESENCE_TIMEOUT = timedelta(seconds=10)

# How long the player on the clock may be silent before the others are told
# something is up. Two missed polls: long enough not to cry wolf over one
# dropped request, short enough that the wait before a skip is explained rather
# than mysterious. Must stay below PRESENCE_TIMEOUT or it could never fire.
QUIET_AFTER = timedelta(seconds=3)


@dataclass
class Player:
    id: UUID
    nickname: str
    is_host: bool = False
    score: int = 0
    # Cleared when the player answers wrongly; restored at the next round.
    is_active: bool = True

    # Presence is separate from is_active on purpose. Being knocked out is a
    # game state that resets each round; being gone is a connection state that
    # persists until the player comes back.
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    marked_away: bool = False
    is_connected: bool = True

    def can_play(self) -> bool:
        return self.is_active and self.is_connected


@dataclass
class Round:
    """The loaded topic for the current round, including the answer key."""

    quiz_id: UUID
    slug: str
    title: str
    description: str | None
    categories: list[Category]
    items: list[ItemSolution]

    def answer_key(self) -> dict[UUID, UUID | None]:
        return {item.id: item.category_id for item in self.items}


@dataclass
class Lobby:
    code: str
    players: list[Player] = field(default_factory=list)
    quiz_slugs: list[str] = field(default_factory=list)
    subject_names: list[str] = field(default_factory=list)
    # Every round is loaded when the game starts, so no database call happens
    # mid-game while the store lock is held.
    rounds: list[Round] = field(default_factory=list)
    status: LobbyStatus = LobbyStatus.lobby
    round_index: int = 0
    current_round: Round | None = None
    solved: dict[UUID, UUID] = field(default_factory=dict)  # item_id -> player_id
    turn_cursor: int = 0
    last_move: LastMove | None = None
    version: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def player(self, player_id: UUID) -> Player:
        for candidate in self.players:
            if candidate.id == player_id:
                return candidate
        raise NotFoundError("You are not in this lobby.")

    def touch(self) -> None:
        self.version += 1
        self.updated_at = datetime.now(UTC)


_lobbies: dict[str, Lobby] = {}
_lock = threading.RLock()


# ---------------------------------------------------------------------------
# Lobby lifecycle
# ---------------------------------------------------------------------------


def create_lobby(nickname: str) -> tuple[str, UUID]:
    with _lock:
        _evict_stale()
        code = _unique_code()
        host = Player(id=uuid4(), nickname=nickname.strip(), is_host=True)
        _lobbies[code] = Lobby(code=code, players=[host])
        return code, host.id


def join_lobby(code: str, nickname: str) -> UUID:
    """Join a lobby, or reclaim a seat you were disconnected from.

    Reclaiming is what makes "close the tab, open the link again" work from a
    fresh browser, where localStorage no longer holds the player id. The
    nickname is the only credential, which is fine for a party game but means
    anyone who knows the code and a name can take that seat.
    """
    with _lock:
        lobby = _require(code)
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
) -> LobbyView:
    """Begin a game drawn from the chosen subjects.

    The host picks areas and a length, not specific questions -- which ones come
    up is decided here, spread evenly across the subjects.
    """
    with _lock:
        lobby = _require(code)
        player = lobby.player(player_id)
        _heartbeat(lobby, player_id)
        _refresh_presence(lobby)
        if not player.is_host:
            raise ConflictError("Only the host can start the game.")
        if lobby.status is LobbyStatus.playing:
            raise ConflictError("This game is already running.")
        if len(lobby.players) < 2:
            raise ConflictError("At least two players are needed to start.")

        pools = pools_by_subject(subject_slugs)
        if not pools:
            raise ConflictError("The chosen subjects contain no questions.")

        quiz_slugs = draw_balanced(pools, round_count)
        subject_names = _subject_names(subject_slugs)

        # Load every question up front, so a content problem surfaces now
        # rather than halfway through a game.
        rounds = [_load_round(slug) for slug in quiz_slugs]

        lobby.subject_names = subject_names
        lobby.quiz_slugs = quiz_slugs
        lobby.rounds = rounds
        lobby.status = LobbyStatus.playing
        lobby.round_index = 0
        lobby.last_move = None
        for candidate in lobby.players:
            candidate.score = 0
        _begin_round(lobby, rounds[0])
        lobby.touch()
        return _view(lobby)


def reset_to_lobby(code: str, player_id: UUID) -> LobbyView:
    """Send a finished game back to the waiting room, keeping the players."""
    with _lock:
        lobby = _require(code)
        if not lobby.player(player_id).is_host:
            raise ConflictError("Only the host can restart.")

        lobby.status = LobbyStatus.lobby
        lobby.current_round = None
        lobby.rounds = []
        lobby.subject_names = []
        lobby.solved = {}
        lobby.round_index = 0
        lobby.turn_cursor = 0
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
    with _lock:
        lobby = _require(code)
        player = lobby.player(player_id)
        _refresh_presence(lobby)

        current = _current_player(lobby)
        current_id = current.id if current else None
        # Only needed when the leaver is the one on the clock, but it has to be
        # computed while they are still in the list for the rotation to be right.
        successor_id = _next_active_id(lobby, exclude=player_id)

        lobby.players.remove(player)

        if not lobby.players:
            _lobbies.pop(lobby.code, None)
            return None

        # The host leaving must not leave the lobby unstartable.
        if not any(candidate.is_host for candidate in lobby.players):
            lobby.players[0].is_host = True

        if lobby.status is LobbyStatus.playing:
            keep_id = current_id if current_id and current_id != player_id else successor_id
            lobby.turn_cursor = _index_of(lobby, keep_id) if keep_id else 0
            # The leaver may have been the last active player, which ends the
            # round exactly as a wrong answer would.
            _maybe_finish_round(lobby)

        lobby.touch()
        return _view(lobby)


def get_view(code: str, player_id: UUID | None = None) -> LobbyView:
    """Read lobby state, and treat the read as `player_id`'s heartbeat.

    Piggybacking presence on the poll the client already makes keeps the
    protocol to one endpoint: a tab that closes simply stops polling.
    """
    with _lock:
        lobby = _require(code)
        _heartbeat(lobby, player_id)
        changed = _refresh_presence(lobby)
        before = (lobby.turn_cursor, lobby.round_index, lobby.status)
        _resync(lobby)
        # Only bump the version on a real change, or every poll would look like
        # new state to the clients.
        if changed or before != (lobby.turn_cursor, lobby.round_index, lobby.status):
            lobby.touch()
        return _view(lobby)


def mark_away(code: str, player_id: UUID) -> None:
    """Best-effort 'my tab is closing' signal.

    Optimisation only -- browsers do not guarantee an unload request goes out,
    so `PRESENCE_TIMEOUT` remains the mechanism that actually guarantees a
    vanished player stops holding up the game.
    """
    with _lock:
        lobby = _lobbies.get(code.upper())
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
    category_id: UUID | None,
) -> LobbyView:
    """Place one item, then pass the turn on -- right or wrong.

    A wrong placement also knocks the player out for the rest of the round.
    """
    with _lock:
        lobby = _require(code)
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
        if category_id is not None and all(c.id != category_id for c in current.categories):
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

        _advance_turn(lobby)
        _maybe_finish_round(lobby)
        lobby.touch()
        return _view(lobby)


# ---------------------------------------------------------------------------
# Round and turn mechanics
# ---------------------------------------------------------------------------


def _begin_round(lobby: Lobby, round_: Round) -> None:
    lobby.current_round = round_
    lobby.solved = {}
    for player in lobby.players:
        player.is_active = True

    # Rotate the starting player each round so the same person is not always
    # first at the easy items.
    lobby.turn_cursor = lobby.round_index % max(len(lobby.players), 1)


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
    """
    if lobby.status is not LobbyStatus.playing:
        return
    if _current_player(lobby) is None:
        _advance_turn(lobby)
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

    next_index = lobby.round_index + 1
    if next_index >= len(lobby.rounds):
        lobby.status = LobbyStatus.finished
        lobby.current_round = None
        return

    lobby.round_index = next_index
    _begin_round(lobby, lobby.rounds[next_index])


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
        categories=categories,
        items=items,
    )


# ---------------------------------------------------------------------------
# Views -- everything below must be safe to send to a player
# ---------------------------------------------------------------------------


def _view(lobby: Lobby) -> LobbyView:
    current_player = _current_player(lobby)
    return LobbyView(
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
        round_view=_round_view(lobby),
        last_move=lobby.last_move,
        winner_ids=_winner_ids(lobby),
        version=lobby.version,
    )


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


def _require(code: str) -> Lobby:
    lobby = _lobbies.get(code.upper())
    if lobby is None:
        raise NotFoundError(f"No lobby with code '{code.upper()}'.")
    return lobby


def _unique_code() -> str:
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in _lobbies:
            return code
    raise ConflictError("Could not allocate a lobby code. Try again.")


def _evict_stale() -> None:
    cutoff = datetime.now(UTC) - LOBBY_TTL
    for code in [c for c, lobby in _lobbies.items() if lobby.updated_at < cutoff]:
        del _lobbies[code]


def _reset_store_for_tests() -> None:
    with _lock:
        _lobbies.clear()
