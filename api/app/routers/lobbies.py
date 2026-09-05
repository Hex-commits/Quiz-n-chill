from uuid import UUID

from fastapi import APIRouter, Response, status

from app.schemas import (
    LobbyCreate,
    LobbyIdentity,
    LobbyJoin,
    LobbySettingsUpdate,
    LobbyStart,
    LobbyView,
    PlayerAction,
    PokerAct,
    PokerAnswer,
    PokerBack,
    TurnSubmit,
)
from app.services import lobbies as service

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


@router.post("", response_model=LobbyIdentity, status_code=status.HTTP_201_CREATED)
def create_lobby(payload: LobbyCreate) -> LobbyIdentity:
    """Open a lobby. The creator becomes the host."""
    code, player_id = service.create_lobby(payload.nickname)
    return LobbyIdentity(code=code, player_id=player_id)


@router.post("/{code}/join", response_model=LobbyIdentity)
def join_lobby(code: str, payload: LobbyJoin) -> LobbyIdentity:
    player_id = service.join_lobby(code, payload.nickname)
    return LobbyIdentity(code=code.upper(), player_id=player_id)


@router.get("/{code}", response_model=LobbyView)
def get_lobby(code: str, player_id: UUID | None = None) -> LobbyView:
    """Poll for state, and check in as `player_id` while doing so.

    The poll doubles as the heartbeat, so a client that stops polling -- a
    closed tab -- is marked disconnected and stops being dealt turns.

    Contains no answer key: only items already placed correctly reveal their
    category.
    """
    return service.get_view(code, player_id)


@router.post("/{code}/settings", response_model=LobbyView)
def set_settings(code: str, payload: LobbySettingsUpdate) -> LobbyView:
    """Record the host's choices for the next game, for everyone to see.

    Separate from starting one: the players waiting are entitled to know what
    is being set up for them, and only the host may write it.
    """
    return service.set_settings(code, payload.player_id, payload.settings)


@router.post("/{code}/start", response_model=LobbyView)
def start_game(code: str, payload: LobbyStart) -> LobbyView:
    """Start a game drawn from the chosen subjects.

    The host picks areas and a round count; the server decides which questions
    come up, spread evenly across those subjects.
    """
    return service.start_game(
        code,
        payload.player_id,
        payload.subject_slugs,
        payload.round_count,
        payload.turn_seconds,
        payload.exclude_slugs,
        payload.difficulties,
        payload.mode,
        payload.open_end,
    )


@router.post("/{code}/turns", response_model=LobbyView)
def submit_turn(code: str, payload: TurnSubmit) -> LobbyView:
    """Place one item and pass the turn on. A wrong placement also puts the
    player out for the rest of the round.

    A null `category_id` is the move that says the item is a fake, and is
    graded like any other -- right if it was, out for the round if it was not.
    """
    return service.submit_turn(code, payload.player_id, payload.item_id, payload.category_id)


@router.post("/{code}/poker/act", response_model=LobbyView)
def poker_act(code: str, payload: PokerAct) -> LobbyView:
    """Fold, check, call or raise. `amount` is the total to raise *to*."""
    return service.poker_act(code, payload.player_id, payload.action, payload.amount)


@router.post("/{code}/poker/answer", response_model=LobbyView)
def poker_answer(code: str, payload: PokerAnswer) -> LobbyView:
    """Name the answer the hand is being played for.

    Everyone still in answers at once, so nothing about who chose what leaves
    the server until the hand pays out.
    """
    return service.poker_answer(code, payload.player_id, payload.category_id)


@router.post("/{code}/poker/back", response_model=LobbyView)
def poker_back(code: str, payload: PokerBack) -> LobbyView:
    """Put chips behind another player, at whatever the stage costs.

    Right, and the stake comes back doubled, paid by the house. Wrong, and it
    joins the pot for whoever does take it. A player with no chips left backs
    for nothing and is paid the stake once, which is the way back into the game.
    """
    return service.poker_back(code, payload.player_id, payload.backed_id)


@router.post("/{code}/next-round", response_model=LobbyView)
def ready_for_next_round(code: str, payload: PlayerAction) -> LobbyView:
    """Any player says they are done reading the answers.

    Once half of those present have said so a three-second countdown starts,
    and the round begins when it runs out. Nothing else moves a review on.
    """
    return service.ready_for_next_round(code, payload.player_id)


@router.post("/{code}/restart", response_model=LobbyView)
def restart(code: str, payload: PlayerAction) -> LobbyView:
    return service.reset_to_lobby(code, payload.player_id)


@router.post("/{code}/away", status_code=status.HTTP_204_NO_CONTENT)
def mark_away(code: str, payload: PlayerAction) -> Response:
    """Signal that a tab is closing, so the turn moves on without waiting out
    the presence timeout.

    Best effort: browsers may drop an unload request, and an unknown lobby or
    player is not an error. Correctness rests on the timeout, not on this.
    """
    service.mark_away(code, payload.player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{code}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave(code: str, payload: PlayerAction) -> Response:
    """Drop out of a lobby.

    Works at any point. Mid-game the turn passes on if it was the leaver's and
    the host role moves if the host left. The other players find out on their
    next poll. An emptied lobby stays put until its expiry sweeps it.
    """
    service.leave_lobby(code, payload.player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
