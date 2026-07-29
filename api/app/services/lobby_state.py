"""The shape of a lobby, with no opinion about where it is kept.

Split out from `lobbies.py` so the store can serialise these types without
importing the game rules, and the game rules can stay unaware of whether a
lobby lives in this process or in the database.

These are plain dataclasses rather than Pydantic models on purpose -- they are
mutated constantly by the game loop, and validating on every attribute write
would be noise. Pydantic still handles them at the boundary: `TypeAdapter`
serialises a stdlib dataclass fine, which is what the shared store relies on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.errors import NotFoundError
from app.schemas import (
    CategoryKind,
    Category,
    FinishedRound,
    ItemSolution,
    LastMove,
    LobbyStatus,
    Source,
)


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
    difficulty: str
    # Whether the categories are words or photographs. Only tells the client how
    # to draw the board -- unlike the earlier picture-answer design, nothing is
    # withheld on the strength of it.
    category_kind: CategoryKind = CategoryKind.text
    # Held server-side for the whole round and only published once it is over.
    source: Source | None = None
    categories: list[Category] = field(default_factory=list)
    items: list[ItemSolution] = field(default_factory=list)

    def answer_key(self) -> dict[UUID, UUID]:
        return {item.id: item.category_id for item in self.items}


@dataclass
class Lobby:
    code: str
    players: list[Player] = field(default_factory=list)
    quiz_slugs: list[str] = field(default_factory=list)
    subject_names: list[str] = field(default_factory=list)
    # Every round is loaded when the game starts, so no database call happens
    # mid-game while the lobby is held for writing.
    rounds: list[Round] = field(default_factory=list)
    status: LobbyStatus = LobbyStatus.lobby
    round_index: int = 0
    current_round: Round | None = None
    solved: dict[UUID, UUID] = field(default_factory=dict)  # item_id -> player_id
    # How many turns the rotation has owed each player across the whole game,
    # totalled as each round starts. Deliberately *not* how many they took: a
    # player knocked out on their first answer took fewer turns than the rest
    # and that is the rules working, not something to compensate. This counts
    # only what the arithmetic handed out -- board size against player count --
    # which is the part nobody chose.
    turn_credits: dict[UUID, int] = field(default_factory=dict)
    # The board held back for the settling round, drawn with the others so no
    # database call happens mid-game. None when the pool had nothing spare.
    catch_up_round: Round | None = None
    in_catch_up: bool = False
    # Turns still owed to each player in the settling round, counted down as
    # they are taken. Empty outside it.
    catch_up_left: dict[UUID, int] = field(default_factory=dict)
    turn_cursor: int = 0
    # How long a player has to place one answer, chosen by the host at the
    # start. Kept on the lobby rather than derived, so changing the default
    # later does not alter the rules of a game already in progress.
    turn_seconds: int = 30
    # When the player on the clock runs out of time. Set every time the turn
    # moves, cleared whenever nobody is on the clock.
    turn_expires_at: datetime | None = None
    # Who last lost their turn to the clock, so the table is told why it moved.
    # Cleared by the next actual move.
    timed_out: str | None = None
    # When the between-rounds review stops and the next round begins. Set only
    # while `status` is `reviewing`.
    review_until: datetime | None = None
    last_move: LastMove | None = None
    # Every placement this round, oldest first. Bounded, and cleared when a
    # round starts -- it is a running commentary for the players on screen, not
    # a record of anything. It goes when the lobby does, like the rest of this.
    history: list[LastMove] = field(default_factory=list)
    finished_rounds: list[FinishedRound] = field(default_factory=list)
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
