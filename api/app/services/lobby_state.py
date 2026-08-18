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
    LobbySettings,
    LobbyStatus,
    Source,
)


@dataclass
class Player:
    id: UUID
    nickname: str
    is_host: bool = False
    score: int = 0
    is_active: bool = True

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
    category_kind: CategoryKind = CategoryKind.text
    source: Source | None = None
    categories: list[Category] = field(default_factory=list)
    items: list[ItemSolution] = field(default_factory=list)

    def answer_key(self) -> dict[UUID, UUID | None]:
        """Every item in the pool, mapped to where it belongs -- None for a fake."""
        return {item.id: item.category_id for item in self.items}

    def fakes(self) -> list[ItemSolution]:
        """The answers in this pool that belong to no category."""
        return [item for item in self.items if item.category_id is None]

    def pairs(self) -> list[ItemSolution]:
        """The answers that do belong somewhere."""
        return [item for item in self.items if item.category_id is not None]


@dataclass
class Lobby:
    code: str
    players: list[Player] = field(default_factory=list)
    quiz_slugs: list[str] = field(default_factory=list)
    subject_names: list[str] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    status: LobbyStatus = LobbyStatus.lobby
    round_index: int = 0
    current_round: Round | None = None
    solved: dict[UUID, UUID] = field(default_factory=dict)
    turn_credits: dict[UUID, int] = field(default_factory=dict)
    catch_up_round: Round | None = None
    in_catch_up: bool = False
    catch_up_left: dict[UUID, int] = field(default_factory=dict)
    turn_cursor: int = 0
    turn_seconds: int = 30
    turn_expires_at: datetime | None = None
    turn_allowance: int = 0
    timed_out: str | None = None
    ready_ids: list[UUID] = field(default_factory=list)
    next_round_at: datetime | None = None
    last_move: LastMove | None = None
    history: list[LastMove] = field(default_factory=list)
    finished_rounds: list[FinishedRound] = field(default_factory=list)
    settings: LobbySettings = field(default_factory=LobbySettings)
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
