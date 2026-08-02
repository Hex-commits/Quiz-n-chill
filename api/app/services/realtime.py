"""Telling players that something changed, without them having to ask.

The game used to be discovered by polling: every client asked for the whole
lobby every 1.5 seconds whether anything had happened or not. That is a
read-modify-write against the shared store per client per interval -- tens of
thousands an hour for a four-player game, nearly all of them answering
"nothing new".

So the API says when something happened instead. After every mutation it
publishes one tiny message on a Supabase Realtime channel named after the lobby,
and clients fetch only when they hear one.

**The message carries the state.** This was a doorbell to begin with -- payload
`{"version": 7}`, and every client answered it with a fetch. That made a socket
the trigger for a poll rather than a replacement for one: the round trip it
existed to remove was still there, just moved. So the new state goes in the
message and clients render it as it arrives.

What goes out is `LobbyView`, not `Lobby`. The distinction is the whole safety
argument: `Lobby` holds `ItemSolution.category_id` and `explanation` for every
answer -- the complete solution -- while `LobbyView` is what the API already
hands anyone who asks for the lobby, with unplaced answers redacted. It is also
identical for every player: `_view` takes no player id, so there is no per-player
redaction to get wrong here.

That settles who can listen. The channel is named after the lobby code, and
anyone with the code can already call the API and get exactly this. Listening
tells them nothing extra.

Oversized views fall back to the doorbell. `finished_rounds` accumulates a full
answer key per round, so a long game's view can grow past what a broadcast
frame should carry; past `MAX_PAYLOAD_BYTES` the version goes out alone and the
client fetches, as it used to.

Publishing is best-effort by construction. A move that succeeded must not fail
because a notification did not go out -- clients keep a slow poll as a backstop,
so a dropped message costs latency and nothing else.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

from app.config import get_settings

if TYPE_CHECKING:
    from app.schemas import LobbyView

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 2.0

EVENT = "lobby-changed"

MAX_PAYLOAD_BYTES = 64 * 1024


def channel_for(code: str) -> str:
    return f"lobby:{code.upper()}"


def publish(view: LobbyView) -> bool:
    """Send `view` to everyone watching its lobby. Never raises.

    Returns whether the message went out, which is used by tests and by nothing
    else -- no caller should change behaviour based on it.
    """
    settings = get_settings()
    if not settings.realtime_broadcast:
        return False
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return False

    url = f"{settings.supabase_url.rstrip('/')}/realtime/v1/api/broadcast"
    key = settings.supabase_service_role_key

    payload: dict[str, object] = {"version": view.version}
    state = view.model_dump(mode="json")
    if len(json.dumps(state)) <= MAX_PAYLOAD_BYTES:
        payload["state"] = state

    try:
        response = httpx.post(
            url,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {
                        "topic": channel_for(view.code),
                        "event": EVENT,
                        "payload": payload,
                    }
                ]
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - a missed notification is not a failed move
        logger.debug("realtime broadcast for %s failed: %s", view.code, exc)
        return False
