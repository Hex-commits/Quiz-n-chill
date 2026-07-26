"""Pydantic models: the contract between the Python backend and the frontend.

The `*Public` / `*Solution` split is the important part. An item's `category_id`
IS the answer, so player-facing payloads must never carry it. `ItemPublic` has no
such field, which means a frontend bug cannot leak the solution -- the data is
simply not there. Answers appear only in the response to `/check`, after the
player has committed to an assignment.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# Categories -- the buckets ("Deutschland")
# --------------------------------------------------------------------------


class Category(ORMModel):
    id: UUID
    label: str
    position: int


class CategoryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    position: int = 0


# --------------------------------------------------------------------------
# Items -- the answer options ("Berlin", "Zürich")
# --------------------------------------------------------------------------


class ItemPublic(ORMModel):
    """What a player sees. Deliberately has no `category_id`."""

    id: UUID
    label: str


class ItemSolution(ORMModel):
    """Server-side view including the answer."""

    id: UUID
    label: str
    position: int
    category_id: UUID | None = None


class ItemCreate(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    # None marks the item as a fake: it belongs to no category.
    category_id: UUID | None = None
    position: int = 0


# --------------------------------------------------------------------------
# Quizzes -- one Zuordnungs-topic
# --------------------------------------------------------------------------


class Subject(ORMModel):
    """A quiz-pool area (Geografie, Musik).

    Distinct from `Category`, which is a bucket *inside* one question.
    """

    id: UUID
    slug: str
    name: str
    description: str | None = None
    position: int
    quiz_count: int = 0


class QuizSummary(ORMModel):
    id: UUID
    slug: str
    title: str
    description: str | None = None
    subject_slug: str | None = None
    subject_name: str | None = None
    category_count: int = 0
    item_count: int = 0
    created_at: datetime


class QuizDetail(ORMModel):
    """Everything needed to play, and nothing more.

    `items` is shuffled by the service so their order cannot hint at the
    grouping, and carries no `category_id`.
    """

    id: UUID
    slug: str
    title: str
    description: str | None = None
    created_at: datetime
    categories: list[Category] = []
    items: list[ItemPublic] = []


class QuizCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


# --------------------------------------------------------------------------
# Checking an assignment
#
# Stateless: nothing about the attempt is stored. The player posts what they
# assigned, the API grades it and returns the result.
# --------------------------------------------------------------------------


class Assignment(BaseModel):
    item_id: UUID
    # None means the player declared this item a fake.
    category_id: UUID | None = None


class CheckRequest(BaseModel):
    assignments: list[Assignment] = []


class ItemResult(BaseModel):
    item_id: UUID
    label: str
    assigned_category_id: UUID | None = None
    correct_category_id: UUID | None = None
    is_fake: bool
    is_correct: bool


class CheckResult(BaseModel):
    quiz_id: UUID
    score: int
    max_score: int
    results: list[ItemResult] = []


# --------------------------------------------------------------------------
# Lobbies -- ephemeral multiplayer state
#
# None of this is stored in the database. It lives in the API process and is
# gone on restart, which is exactly the intent: the database holds questions,
# not who played them.
# --------------------------------------------------------------------------


class LobbyStatus(StrEnum):
    lobby = "lobby"
    playing = "playing"
    finished = "finished"


class PlayerPublic(BaseModel):
    id: UUID
    nickname: str
    score: int
    # False once the player has answered wrongly; resets each round.
    is_active: bool
    # False when their client has stopped checking in -- a closed tab. Distinct
    # from is_active: it persists across rounds until they come back.
    is_connected: bool = True
    is_host: bool


class SolvedItem(BaseModel):
    """An item that has been placed correctly, so revealing it is safe."""

    item_id: UUID
    label: str
    category_id: UUID | None
    solved_by: UUID


class LastMove(BaseModel):
    """What just happened, so every device can show the same feedback."""

    player_id: UUID
    nickname: str
    item_label: str
    category_id: UUID | None
    was_correct: bool


class RoundView(BaseModel):
    """The current topic as players may see it: no answer key."""

    quiz_id: UUID
    slug: str
    title: str
    description: str | None = None
    categories: list[Category] = []
    remaining_items: list[ItemPublic] = []
    solved_items: list[SolvedItem] = []


class LobbyView(BaseModel):
    code: str
    status: LobbyStatus
    players: list[PlayerPublic] = []
    quiz_slugs: list[str] = []
    subject_names: list[str] = []
    round_index: int = 0
    round_count: int = 0
    current_player_id: UUID | None = None
    # True when the player on the clock has stopped checking in but has not yet
    # timed out. Lets the other screens explain the pause instead of appearing
    # to hang. Goes false by itself once the turn is handed on.
    current_player_quiet: bool = False
    round_view: RoundView | None = None
    last_move: LastMove | None = None
    winner_ids: list[UUID] = []
    # Bumped on every mutation so a client can poll cheaply and skip re-renders.
    version: int = 0


class LobbyCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)


class LobbyJoin(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)


class LobbyIdentity(BaseModel):
    """Returned once on create/join. The player id doubles as the secret."""

    code: str
    player_id: UUID


class LobbyStart(BaseModel):
    player_id: UUID
    # Subjects to draw from, not specific questions -- the server picks which
    # ones, spread evenly across these.
    subject_slugs: list[str] = Field(min_length=1)
    round_count: int = Field(default=5, ge=1, le=20)


class TurnSubmit(BaseModel):
    player_id: UUID
    item_id: UUID
    # None means "I say this one is a fake".
    category_id: UUID | None = None


class PlayerAction(BaseModel):
    player_id: UUID


class HealthStatus(BaseModel):
    status: str
    environment: str
    database: str
