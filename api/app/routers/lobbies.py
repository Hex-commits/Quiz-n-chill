from fastapi import APIRouter, Response, status

from app.schemas import (
    LobbyCreate,
    LobbyIdentity,
    LobbyJoin,
    LobbyStart,
    LobbyView,
    PlayerAction,
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
def get_lobby(code: str) -> LobbyView:
    """Poll for state. Contains no answer key -- only items already placed
    correctly reveal their category."""
    return service.get_view(code)


@router.post("/{code}/start", response_model=LobbyView)
def start_game(code: str, payload: LobbyStart) -> LobbyView:
    return service.start_game(code, payload.player_id, payload.quiz_slugs)


@router.post("/{code}/turns", response_model=LobbyView)
def submit_turn(code: str, payload: TurnSubmit) -> LobbyView:
    """Place one item and pass the turn on. A wrong placement also puts the
    player out for the rest of the round."""
    return service.submit_turn(code, payload.player_id, payload.item_id, payload.category_id)


@router.post("/{code}/restart", response_model=LobbyView)
def restart(code: str, payload: PlayerAction) -> LobbyView:
    return service.reset_to_lobby(code, payload.player_id)


@router.post("/{code}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave(code: str, payload: PlayerAction) -> Response:
    """Drop out of a lobby.

    Works at any point. Mid-game the turn passes on if it was the leaver's, the
    host role moves if the host left, and the lobby is discarded once the last
    player is gone. The other players find out on their next poll.
    """
    service.leave_lobby(code, payload.player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
