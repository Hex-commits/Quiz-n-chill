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
    PokerResult,
    PokerStage,
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
    subject_name: str | None = None
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
class PokerSeat:
    """One player's place at the poker table, for the hand being played.

    `committed` is what they have put in on this street and `contributed` what
    they have put in over the whole hand. Two counters rather than one because
    they answer different questions: the first is what a call has to match, the
    second is what a side pot is built from when somebody is all in for less
    than the rest.

    `backing` is who this player put chips behind after folding, and
    `side_stake` is how many. Neither is part of the pot: the stake is out of
    the stack from the moment it is placed, and where it ends up is decided when
    the hand pays out.

    `side_streak` is the only thing on a seat that outlives the hand it was won
    in -- how many side bets in a row this player has had come in, which is what
    the next one pays out on.
    """

    player_id: UUID
    stack: int
    committed: int = 0
    contributed: int = 0
    folded: bool = False
    all_in: bool = False
    sitting_out: bool = False
    acted: bool = False
    answer_category_id: UUID | None = None
    correct: bool | None = None
    won: int = 0
    backing: UUID | None = None
    side_stake: int = 0
    side_streak: int = 0

    def in_hand(self) -> bool:
        return not self.sitting_out and not self.folded

    def can_act(self) -> bool:
        return self.in_hand() and not self.all_in


@dataclass
class PokerTable:
    """A game of betting rounds played for one question.

    Holds no answer key of its own: the question is the lobby's current round,
    and `question_item_id` points at the one answer off it being asked -- the
    table's job is to say which category that answer belongs in. What may be
    shown of it, and when, is `poker.view`'s decision.

    `acted` on a seat means "has acted since the last raise", which is what
    makes a betting round finishable. `pot` is what the streets behind this one
    gathered; `carried` is the part of an earlier pot nobody answered for, and
    it plays on. `option_ids` is the categories, in the order this hand offers
    them, so polling cannot reorder them under a player mid-decision.
    """

    stage: PokerStage = PokerStage.preflop
    seats: list[PokerSeat] = field(default_factory=list)
    button: int = 0
    to_act: int | None = None
    current_bet: int = 0
    min_raise: int = 0
    pot: int = 0
    carried: int = 0
    big_blind: int = 0
    question_item_id: UUID | None = None
    option_ids: list[UUID] = field(default_factory=list)
    acts_by: datetime | None = None
    answers_by: datetime | None = None
    next_hand_at: datetime | None = None
    result: PokerResult | None = None

    def seat(self, player_id: UUID) -> PokerSeat | None:
        return next((s for s in self.seats if s.player_id == player_id), None)


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
    poker: PokerTable | None = None
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
