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
# Pictures -- attached to categories, for a picture question
# --------------------------------------------------------------------------


class CategoryKind(StrEnum):
    """How a question's categories are presented.

    A property of the whole quiz rather than of each category: a board that
    mixed words and photographs would make the worded ones a different game,
    which is not a difficulty setting anyone chose.
    """

    text = "text"
    image = "image"


class ImagePublic(BaseModel):
    """A picture, and what has to be printed under it.

    `src` is a ready-to-load Commons URL. The file name is not sent because it
    is not what the client needs.

    Credit and licence are always present here, unlike the earlier design where
    pictures were answers and had to be shown anonymously until placed. A
    category is on the board from the first frame, so there is nothing to time
    the attribution against -- and CC BY-SA requires it wherever the work is
    shown, which now costs the game nothing.
    """

    src: str
    credit: str | None = None
    licence: str | None = None
    licence_url: str | None = None


class ImageSource(ORMModel):
    """The stored picture: server-side only.

    Separate from `ImagePublic` because the API builds a URL from `file` rather
    than sending it, and one model with an optional `file` would make it easy
    to serialise the wrong one.
    """

    file: str
    credit: str | None = None
    licence: str
    licence_url: str | None = None


# --------------------------------------------------------------------------
# Categories -- the buckets ("Deutschland", or a photograph of a bridge)
# --------------------------------------------------------------------------


class Category(ORMModel):
    id: UUID
    # None while a *picture* round is being played. The label of a photographic
    # category is the name of the thing in the photograph -- "Albert Bridge" --
    # and printing that above the picture answers the question the picture was
    # chosen to ask. It comes back for the review, which is where the point of
    # the round is made.
    label: str | None = None
    position: int
    # The photograph itself is never withheld: a category *is* the board, so
    # there is no moment when hiding it would mean anything. Its credit travels
    # with it for the same reason -- see `ImagePublic`.
    image: ImagePublic | None = None


class CategoryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    position: int = 0


# --------------------------------------------------------------------------
# Items -- the answer options ("Berlin", "Zürich")
# --------------------------------------------------------------------------


class ItemPublic(ORMModel):
    """What a player sees of an answer still in the pool.

    Deliberately has no `category_id`: that field IS the answer. The label is
    always present -- answers are words for every kind of question now that the
    photographs live on the categories.
    """

    id: UUID
    label: str


class ItemSolution(ORMModel):
    """Server-side view including the answer."""

    id: UUID
    label: str
    position: int
    # Never null: a question is a one-to-one pairing, so every answer has a
    # category. The database enforces it.
    category_id: UUID
    # One line on why this answer belongs where it does. Reveals the answer, so
    # it is absent from `ItemPublic` for the same reason `category_id` is.
    explanation: str | None = None


class ItemCreate(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    # Required: a question is a one-to-one pairing, so writing an answer without
    # a category is rejected here rather than by the NOT NULL constraint.
    category_id: UUID
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
    # How that total splits by rating, so the host's setup screen can say how
    # much a difficulty filter would actually leave. Keyed by the `Difficulty`
    # values as plain strings -- the enum is declared below this class, and a
    # forward reference buys nothing here.
    difficulty_counts: dict[str, int] = Field(default_factory=dict)


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Source(BaseModel):
    """Where a question was written from.

    Deliberately NOT part of `QuizDetail`: during play a link to the source is a
    link to the answers. It is attached to results instead -- see `CheckResult`
    and the lobby's finished view.
    """

    url: str
    title: str | None = None


class QuizSummary(ORMModel):
    id: UUID
    slug: str
    title: str
    description: str | None = None
    subject_slug: str | None = None
    subject_name: str | None = None
    difficulty: Difficulty = Difficulty.medium
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
    difficulty: Difficulty = Difficulty.medium
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
    # Optional only so a partial board can be submitted; an unplaced answer is
    # wrong rather than meaningful.
    category_id: UUID | None = None


class CheckRequest(BaseModel):
    assignments: list[Assignment] = []


class ItemResult(BaseModel):
    item_id: UUID
    label: str
    # `assigned` stays optional -- the player may have submitted without placing
    # this one. `correct` never is: every answer has exactly one category.
    assigned_category_id: UUID | None = None
    correct_category_id: UUID
    is_correct: bool
    # Shown beside the answer once the round is over.
    explanation: str | None = None


class CheckResult(BaseModel):
    quiz_id: UUID
    score: int
    max_score: int
    difficulty: Difficulty = Difficulty.medium
    # Revealed here and nowhere earlier: the player has already committed to an
    # assignment, so the source is now a reference rather than a cheat sheet.
    source: Source | None = None
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
    # Between rounds: the finished round's answers are on screen and the next
    # round has not started yet.
    reviewing = "reviewing"
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
    category_id: UUID
    solved_by: UUID


class LastMove(BaseModel):
    """What just happened, so every device can show the same feedback."""

    player_id: UUID
    nickname: str
    # Always named. Answers are words, and a wrong one going back in the pool
    # is a word every player can already read there.
    item_label: str
    # Where it was placed -- always a real category, right or wrong.
    category_id: UUID
    was_correct: bool


class ResolvedPair(BaseModel):
    """One category and the answer that belongs to it, with the why.

    Only ever built for a round that is over, which is what makes revealing
    `explanation` safe -- while a round runs it gives the answer away.
    """

    category_label: str
    item_label: str
    # The category's photograph, so the review screen shows what was being
    # asked about rather than only its name.
    image: ImagePublic | None = None
    explanation: str | None = None
    # Who placed it, or None if the round ended with this one still open --
    # everybody knocked out, or the last player left.
    solved_by: UUID | None = None


class FinishedRound(BaseModel):
    """A round that is over, so its source and answer key can be shown.

    Accumulated as the game runs. The whole pairing is included, unsolved pairs
    too: a round that ended because everyone was knocked out is exactly the one
    worth reading afterwards.
    """

    quiz_id: UUID
    slug: str
    title: str
    difficulty: Difficulty = Difficulty.medium
    source: Source | None = None
    solution: list[ResolvedPair] = []


class RoundView(BaseModel):
    """The current topic as players may see it: no answer key, no source."""

    quiz_id: UUID
    slug: str
    title: str
    description: str | None = None
    difficulty: Difficulty = Difficulty.medium
    # Tells the client to render each category as a photograph rather than a
    # heading. The answers are words either way.
    category_kind: CategoryKind = CategoryKind.text
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
    # The short settling round after the last question, played only by whoever
    # the rotation short-changed over the game. `round_index` is meaningless
    # while this is true -- it is not one of the numbered rounds.
    is_catch_up: bool = False
    # Turns still owed, by player, during that round. Empty otherwise.
    catch_up_left: dict[UUID, int] = {}
    current_player_id: UUID | None = None
    # Who plays after the current player. Sent rather than derived on the client
    # because `players` is the seating order, not the *playing* order: whoever is
    # knocked out or disconnected is skipped, and only the server knows which.
    next_player_id: UUID | None = None
    # Seconds until the next round starts. Only set while status is `reviewing`.
    review_seconds_left: int | None = None
    # Seconds the player on the clock has left to place an answer, and how long
    # they got. Both None when nobody is on the clock.
    #
    # Sent as a remaining duration rather than a deadline so a client whose
    # clock is wrong still counts down correctly -- and the client ticks it
    # locally rather than asking again, which is the whole point of sending it.
    turn_seconds_left: int | None = None
    turn_seconds: int | None = None
    # Who last lost their turn to the clock. Cleared by the next real move.
    timed_out: str | None = None
    # Every placement this round, oldest first, so the table can follow how it
    # has gone rather than only what just happened.
    history: list[LastMove] = []
    # True when the player on the clock has stopped checking in but has not yet
    # timed out. Lets the other screens explain the pause instead of appearing
    # to hang. Goes false by itself once the turn is handed on.
    current_player_quiet: bool = False
    round_view: RoundView | None = None
    # Grows as rounds complete; rendered on the final scoreboard so players can
    # check the questions against the material they came from.
    finished_rounds: list[FinishedRound] = []
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
    # Which ratings may be drawn. `min_length=1` because an empty list would ask
    # for a game with no questions in it, which is a client bug rather than a
    # choice -- the UI cannot get here, since unticking the last box is refused.
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: list(Difficulty), min_length=1
    )
    round_count: int = Field(default=5, ge=1, le=20)
    # How long each player gets to place one answer. Bounded rather than free:
    # below about ten seconds nobody can read a board, and above two minutes the
    # timer stops being a timer.
    turn_seconds: int = Field(default=30, ge=10, le=120)
    # Questions the host's browser remembers this group having played. A
    # preference, not a filter: the server prefers anything else first and falls
    # back to these once nothing new is left. Nothing about it is stored -- the
    # record lives in the browser, because "what have we played" belongs to a
    # group of friends rather than to an account, and this game has no accounts.
    #
    # Bounded so a stale or tampered client cannot post a megabyte of slugs at a
    # route that has no auth.
    exclude_slugs: list[str] = Field(default_factory=list, max_length=500)


class TurnSubmit(BaseModel):
    player_id: UUID
    item_id: UUID
    # Required: every answer belongs to a category, so there is no longer a move
    # that means "this one fits nowhere".
    category_id: UUID


class PlayerAction(BaseModel):
    player_id: UUID


class HealthStatus(BaseModel):
    status: str
    environment: str
    database: str
