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


class CategoryKind(StrEnum):
    """How a question's categories are presented.

    A property of the whole quiz rather than of each category: a board that
    mixed words and photographs would make the worded ones a different game,
    which is not a difficulty setting anyone chose.
    """

    text = "text"
    image = "image"


class GameMode(StrEnum):
    """Which game the lobby is playing.

    A property of the game rather than of a question: every mode draws from the
    same pool of Zuordnungsfragen, and picking one changes what the table does
    with a board, not which boards exist.
    """

    classic = "classic"
    poker = "poker"


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


class Category(ORMModel):
    id: UUID
    label: str | None = None
    position: int
    image: ImagePublic | None = None


class CategoryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    position: int = 0


class ItemPublic(ORMModel):
    """What a player sees of an answer still in the pool.

    Deliberately has no `category_id`: that field IS the answer. The label is
    always present -- answers are words for every kind of question now that the
    photographs live on the categories.
    """

    id: UUID
    label: str


class ItemSolution(ORMModel):
    """Server-side view including the answer.

    `category_id` is None for a fake -- an answer that belongs to no category.
    Which of the two an item is may never reach a player before the round ends;
    that is the whole of what there is to spot.
    """

    id: UUID
    label: str
    position: int
    category_id: UUID | None = None
    explanation: str | None = None


class ItemCreate(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    category_id: UUID | None = None
    position: int = 0


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


class Assignment(BaseModel):
    item_id: UUID
    category_id: UUID | None = None


class CheckRequest(BaseModel):
    assignments: list[Assignment] = []


class ItemResult(BaseModel):
    item_id: UUID
    label: str
    assigned_category_id: UUID | None = None
    correct_category_id: UUID | None = None
    is_correct: bool
    explanation: str | None = None


class CheckResult(BaseModel):
    quiz_id: UUID
    score: int
    max_score: int
    difficulty: Difficulty = Difficulty.medium
    source: Source | None = None
    results: list[ItemResult] = []


class LobbyStatus(StrEnum):
    lobby = "lobby"
    playing = "playing"
    reviewing = "reviewing"
    finished = "finished"


class PlayerPublic(BaseModel):
    id: UUID
    nickname: str
    score: int
    is_active: bool
    is_connected: bool = True
    is_host: bool


class SolvedItem(BaseModel):
    """An item that has been resolved correctly, so revealing it is safe.

    `category_id` is None when the item was a fake and the player said so. It
    is the same null the answer key holds, and revealing it here gives nothing
    away: the move that resolved it already did.
    """

    item_id: UUID
    label: str
    category_id: UUID | None = None
    solved_by: UUID


class LastMove(BaseModel):
    """What just happened, so every device can show the same feedback."""

    player_id: UUID
    nickname: str
    item_label: str
    category_id: UUID | None = None
    was_correct: bool


class ResolvedPair(BaseModel):
    """One category and the answer that belongs to it, with the why.

    Only ever built for a round that is over, which is what makes revealing
    `explanation` safe -- while a round runs it gives the answer away.
    """

    category_label: str
    item_label: str
    image: ImagePublic | None = None
    explanation: str | None = None
    solved_by: UUID | None = None


class ResolvedFake(BaseModel):
    """An answer that belonged to no category, once saying so is safe.

    Separate from `ResolvedPair` rather than a pair with an empty category: a
    fake has nothing to sit beside, and the review reads it as its own list --
    "these two were never part of it".
    """

    item_label: str
    explanation: str | None = None
    solved_by: UUID | None = None


class FinishedRound(BaseModel):
    """A round that is over, so its source and answer key can be shown.

    Accumulated as the game runs. The whole pairing is included, unsolved pairs
    too: a round that ended because everyone was knocked out is exactly the one
    worth reading afterwards. `fakes` is the rest of the answer key -- what was
    in the pool and belonged nowhere.
    """

    quiz_id: UUID
    slug: str
    title: str
    difficulty: Difficulty = Difficulty.medium
    source: Source | None = None
    solution: list[ResolvedPair] = []
    fakes: list[ResolvedFake] = []


class RoundView(BaseModel):
    """The current topic as players may see it: no answer key, no source.

    `subject_name` is the pool area the question was drawn from (Geografie,
    Musik) -- safe to show while the round runs, since it says what kind of
    question this is and nothing about where the answers go.
    """

    quiz_id: UUID
    slug: str
    title: str
    description: str | None = None
    subject_name: str | None = None
    difficulty: Difficulty = Difficulty.medium
    category_kind: CategoryKind = CategoryKind.text
    categories: list[Category] = []
    remaining_items: list[ItemPublic] = []
    solved_items: list[SolvedItem] = []


class PokerStage(StrEnum):
    """Where a poker hand has got to.

    The four betting stages are ordinary Hold'em. What is not ordinary is what
    each deal reveals: the flop names the subject, the turn names the topic, and
    the river turns the question face up. So a player bets three times on a
    question they can only partly see, and once on one they can read.
    """

    preflop = "preflop"
    flop = "flop"
    turn = "turn"
    river = "river"
    answering = "answering"
    payout = "payout"


class PokerAction(StrEnum):
    fold = "fold"
    check = "check"
    call = "call"
    raise_to = "raise"
    all_in = "all_in"


class PokerSeatView(BaseModel):
    """One player at the table, as everyone at it may see them.

    No hole cards: they are the one thing at this table that is not public, and
    they never travel on the lobby view. `has_cards` is all anyone else gets --
    see `PokerHand`, which is fetched per player and answers only for the player
    who asks.

    `answer_item_id` and `is_correct` stay null until the hand is paid out.
    Answers are simultaneous, and a view that showed them as they arrived would
    turn the last player to answer into the best-informed one.
    """

    player_id: UUID
    stack: int
    committed: int = 0
    folded: bool = False
    all_in: bool = False
    sitting_out: bool = False
    has_cards: bool = False
    has_answered: bool = False
    answer_item_id: UUID | None = None
    is_correct: bool | None = None
    won: int = 0


class PokerAward(BaseModel):
    player_id: UUID
    amount: int


class PokerResult(BaseModel):
    """How a hand ended, revealed with the answer key once it has.

    `carried` is the part of the pot nobody won. Getting the question wrong does
    not return the chips -- they sit on the table and the next hand plays for
    them too.
    """

    correct_item_ids: list[UUID] = []
    correct_labels: list[str] = []
    explanation: str | None = None
    awards: list[PokerAward] = []
    carried: int = 0
    uncontested: bool = False


class PokerView(BaseModel):
    """The table as everyone at it may see it.

    Everything here is either public poker (chips, bets, the board) or a part of
    the question that has already been turned over. What has not been revealed
    yet is absent rather than hidden, so a client cannot read ahead however it
    is inspected: `question` is null until the river turns it over, and
    `options` stays empty until the betting after it is done.

    `question` is one category off the board -- named, or pictured on a picture
    question. `seconds_left` is whichever clock is running: the player on the
    clock, the answers, or the wait before the next hand. Which one it is
    follows from `stage`.
    """

    stage: PokerStage
    hand_index: int
    hand_count: int
    board: list[str] = []
    pot: int = 0
    carried: int = 0
    current_bet: int = 0
    min_raise: int = 0
    big_blind: int = 0
    button_id: UUID | None = None
    to_act: UUID | None = None
    seconds_left: int | None = None
    seats: list[PokerSeatView] = []
    subject_name: str | None = None
    title: str | None = None
    question: Category | None = None
    options: list[ItemPublic] = []
    result: PokerResult | None = None


class PokerHand(BaseModel):
    """One player's hole cards, answered only to that player.

    Its own endpoint rather than a field on the lobby view, because the lobby
    view is public: it is broadcast to every client watching the lobby, and one
    per-player secret on it would be one redaction to get wrong on every future
    change. Cards do not move during a hand, so this is fetched once per hand.
    """

    hand_index: int
    cards: list[str] = []


class PokerAct(BaseModel):
    """One betting move. `amount` is the total to raise *to*, and only a raise
    reads it."""

    player_id: UUID
    action: PokerAction
    amount: int | None = None


class PokerAnswer(BaseModel):
    player_id: UUID
    item_id: UUID


class LobbySettings(BaseModel):
    """The game the host has set up, before there is a game to play.

    Kept on the lobby rather than in the host's browser, because the other
    players have no other way of knowing what they are about to play -- and a
    player who joins late has then missed nothing.

    Looser than `LobbyStart`, which is what the same choices have to satisfy to
    become a game: a host part-way through picking has every right to no
    subjects ticked, and being told so belongs on the start button rather than
    on every click leading up to it.
    """

    mode: GameMode = GameMode.classic
    subject_slugs: list[str] = Field(default_factory=list, max_length=50)
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: list(Difficulty), max_length=len(Difficulty)
    )
    round_count: int = Field(default=5, ge=1, le=20)
    turn_seconds: int = Field(default=30, ge=10, le=120)


class LobbySettingsUpdate(BaseModel):
    player_id: UUID
    settings: LobbySettings


class LobbyView(BaseModel):
    code: str
    status: LobbyStatus
    players: list[PlayerPublic] = []
    quiz_slugs: list[str] = []
    subject_names: list[str] = []
    round_index: int = 0
    round_count: int = 0
    is_catch_up: bool = False
    catch_up_left: dict[UUID, int] = {}
    current_player_id: UUID | None = None
    next_player_id: UUID | None = None
    turn_seconds_left: int | None = None
    turn_seconds: int | None = None
    ready_ids: list[UUID] = []
    ready_needed: int = 1
    next_round_in: int | None = None
    timed_out: str | None = None
    history: list[LastMove] = []
    current_player_quiet: bool = False
    round_view: RoundView | None = None
    poker: PokerView | None = None
    finished_rounds: list[FinishedRound] = []
    last_move: LastMove | None = None
    winner_ids: list[UUID] = []
    settings: LobbySettings = Field(default_factory=LobbySettings)
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
    mode: GameMode = GameMode.classic
    subject_slugs: list[str] = Field(min_length=1)
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: list(Difficulty), min_length=1
    )
    round_count: int = Field(default=5, ge=1, le=20)
    turn_seconds: int = Field(default=30, ge=10, le=120)
    exclude_slugs: list[str] = Field(default_factory=list, max_length=500)


class TurnSubmit(BaseModel):
    """One placement. `category_id` None means "I say this one is a fake"."""

    player_id: UUID
    item_id: UUID
    category_id: UUID | None = None


class PlayerAction(BaseModel):
    player_id: UUID


class HealthStatus(BaseModel):
    status: str
    environment: str
    database: str
