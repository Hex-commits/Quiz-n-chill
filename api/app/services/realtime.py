"""Telling players that something changed, without them having to ask.

The game used to be discovered by polling: every client asked for the whole
lobby every 1.5 seconds whether anything had happened or not. That is a
read-modify-write against the shared store per client per interval -- tens of
thousands an hour for a four-player game, nearly all of them answering
"nothing new".

So the API says when something happened instead. After every mutation it
publishes one tiny message on a Supabase Realtime channel named after the lobby,
and clients fetch only when they hear one.

**The message deliberately carries no game state.** Just the version number that
the sender has now reached. A payload that contains nothing cannot leak
anything, and what would otherwise be in it -- the lobby -- holds
`ItemSolution.category_id` and `explanation` for every answer, which is the
complete solution. Clients hear "version 7 exists" and ask the API for the
redacted view they are allowed to see, exactly as before.

That also settles who can listen. The channel name is the lobby code, and anyone
with the code could already call the API; hearing a version number tells them
strictly less than that.

Publishing is best-effort by construction. A move that succeeded must not fail
because a notification did not go out -- clients keep a slow poll as a backstop,
so a dropped message costs latency and nothing else.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Short: this sits between a player's move and the response to it. A Realtime
# endpoint that is slow to answer should not hold up the game.
TIMEOUT_SECONDS = 2.0

EVENT = "lobby-changed"


def channel_for(code: str) -> str:
    return f"lobby:{code.upper()}"


def publish(code: str, version: int) -> bool:
    """Announce that `code` has reached `version`. Never raises.

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
                        "topic": channel_for(code),
                        "event": EVENT,
                        # The whole payload. See the module docstring: this is a
                        # doorbell, not a delivery.
                        "payload": {"version": version},
                    }
                ]
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - a missed notification is not a failed move
        # Logged at debug rather than warning: with the slow poll still running,
        # this is a latency event, not an error, and a Realtime outage would
        # otherwise fill the log with one line per turn.
        logger.debug("realtime broadcast for %s failed: %s", code, exc)
        return False
