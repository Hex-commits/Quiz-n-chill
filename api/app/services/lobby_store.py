"""Where lobbies are kept, and how two writers are kept apart.

`lobbies.py` holds the game rules and never learns which of these is in use.
Every mutation in that module looks the same either way:

    with store.mutate(code) as lobby:
        ...change it...

The context manager loads the lobby, hands it over, and writes it back when the
block ends -- with exclusive access held for the duration, so a read-modify-write
cannot interleave with another player's. Whatever the block changed is written
back even if it then raised: every entry point records the caller's heartbeat
before it validates, and a refused request still proves that client is alive.

Two implementations:

`MemoryStore` keeps a dict behind an RLock, exactly as this project always did.
It needs a single long-lived process, and is the right thing for the test suite
-- no database to reach, no network in a unit test.

`SupabaseStore` keeps each lobby as a row in `public.lobbies`, locked by two SQL
functions. This is what makes the game work on a horizontally scaled or
serverless host, where consecutive requests from the same player routinely land
on different instances.

Nothing here is history. Rows carry an expiry and are swept; a lobby exists only
while its game does. The promise made elsewhere in this project is unchanged --
the database stores questions, never who played them.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Iterator, Protocol
from uuid import uuid4

from pydantic import TypeAdapter

from app.errors import ConflictError, NotFoundError
from app.services.lobby_state import Lobby

LOBBY_TTL = timedelta(hours=4)

# How long a lock may be held before it is assumed abandoned. A deadline rather
# than a holder who must return: on serverless an instance can vanish mid-request,
# and a lock nobody releases would wedge that lobby for everyone.
LOCK_SECONDS = 5

# How long to wait for another writer to finish before giving up. Two players
# submitting at the same instant is ordinary; waiting seconds for one is not.
LOCK_WAIT = 3.0
LOCK_POLL = 0.02

_lobby_json = TypeAdapter(Lobby)




class LobbyStore(Protocol):
    """What `lobbies.py` needs. Deliberately small."""

    def create(self, lobby: Lobby) -> None: ...

    def exists(self, code: str) -> bool: ...

    def delete(self, code: str) -> None: ...

    def clear(self) -> None: ...

    def mutate(self, code: str) -> Iterator[Lobby]:
        """Exclusive read-modify-write. Raises NotFoundError if there is none."""
        ...

    def mutate_if_present(self, code: str) -> Iterator[Lobby | None]:
        """As `mutate`, but yields None instead of raising.

        For the best-effort paths -- an unload beacon naming a lobby that has
        already gone is not an error.
        """
        ...


# ---------------------------------------------------------------------------
# In this process
# ---------------------------------------------------------------------------


class MemoryStore:
    """A dict and a lock. Requires one long-lived process."""

    def __init__(self) -> None:
        import threading

        self._lobbies: dict[str, Lobby] = {}
        self._lock = threading.RLock()

    def create(self, lobby: Lobby) -> None:
        with self._lock:
            self._lobbies[lobby.code] = lobby

    def exists(self, code: str) -> bool:
        with self._lock:
            self._evict_stale()
            return code.upper() in self._lobbies

    def delete(self, code: str) -> None:
        with self._lock:
            self._lobbies.pop(code.upper(), None)

    def clear(self) -> None:
        with self._lock:
            self._lobbies.clear()

    @contextmanager
    def mutate(self, code: str) -> Iterator[Lobby]:
        with self._lock:
            lobby = self._lobbies.get(code.upper())
            if lobby is None:
                raise NotFoundError(f"No lobby with code '{code.upper()}'.")
            # The stored object *is* the working copy here, so there is nothing
            # to write back.
            yield lobby

    @contextmanager
    def mutate_if_present(self, code: str) -> Iterator[Lobby | None]:
        with self._lock:
            yield self._lobbies.get(code.upper())

    def _evict_stale(self) -> None:
        cutoff = datetime.now(UTC) - LOBBY_TTL
        for code in [c for c, lobby in self._lobbies.items() if lobby.updated_at < cutoff]:
            del self._lobbies[code]


# ---------------------------------------------------------------------------
# Shared across instances
# ---------------------------------------------------------------------------


class SupabaseStore:
    """One row per live game in `public.lobbies`, locked by the database.

    PostgREST gives no transaction spanning a read and a later write, so the
    lock cannot be a `select ... for update` the caller holds open. Two SQL
    functions stand in: `lobby_acquire` takes the lock *and* returns the row in
    one statement, `lobby_release` writes it back and lets go, refusing if the
    lock has since been taken by somebody else.

    Two round trips per mutation, and unmetered -- which is why the game state
    lives here rather than in a per-command-billed cache.
    """

    def __init__(self, client) -> None:
        self._db = client

    # -- plumbing --------------------------------------------------------

    @staticmethod
    def _ttl_seconds() -> int:
        return int(LOBBY_TTL.total_seconds())

    def _acquire(self, code: str):
        """Take the lock and read, or return None if the lobby does not exist.

        Waits briefly while another writer holds it. A turn-based game has
        little real contention: the common case is several players' heartbeats
        arriving together, and those are quick.
        """
        token = uuid4().hex
        deadline = time.monotonic() + LOCK_WAIT

        while True:
            rows = self._db.rpc(
                "lobby_acquire",
                {"p_code": code.upper(), "p_token": token, "p_ttl_seconds": LOCK_SECONDS},
            ).execute().data

            row = rows[0] if isinstance(rows, list) and rows else rows
            # Checked on `state` rather than on the row: a composite return type
            # can hand back a row of nulls, which is truthy but holds nothing.
            if isinstance(row, dict) and row.get("state") is not None:
                return token, _lobby_json.validate_python(row["state"])

            # Either there is no such lobby, or somebody else holds the lock.
            # Only the second is worth waiting on.
            if not self.exists(code):
                return None
            if time.monotonic() >= deadline:
                raise ConflictError("That lobby is busy right now. Try again.")
            time.sleep(LOCK_POLL)

    def _release(self, code: str, token: str, lobby: Lobby) -> None:
        self._db.rpc(
            "lobby_release",
            {
                "p_code": code.upper(),
                "p_token": token,
                "p_state": _lobby_json.dump_python(lobby, mode="json"),
                "p_version": lobby.version,
                "p_ttl_seconds": self._ttl_seconds(),
            },
        ).execute()

    # -- the interface ---------------------------------------------------

    def create(self, lobby: Lobby) -> None:
        expires = datetime.now(UTC) + LOBBY_TTL
        self._db.table("lobbies").insert(
            {
                "code": lobby.code.upper(),
                "state": _lobby_json.dump_python(lobby, mode="json"),
                "version": lobby.version,
                "expires_at": expires.isoformat(),
            }
        ).execute()

    def exists(self, code: str) -> bool:
        rows = (
            self._db.table("lobbies")
            .select("code")
            .eq("code", code.upper())
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)

    def delete(self, code: str) -> None:
        self._db.table("lobbies").delete().eq("code", code.upper()).execute()

    def clear(self) -> None:
        # Filtered on the primary key rather than an unfiltered delete, which
        # PostgREST refuses outright.
        self._db.table("lobbies").delete().neq("code", "").execute()

    def sweep(self) -> int:
        """Drop games that have expired. Nothing depends on this running."""
        try:
            return self._db.rpc("sweep_lobbies", {}).execute().data or 0
        except Exception:  # noqa: BLE001 - housekeeping must never fail a request
            return 0

    @contextmanager
    def mutate(self, code: str) -> Iterator[Lobby]:
        held = self._acquire(code)
        if held is None:
            raise NotFoundError(f"No lobby with code '{code.upper()}'.")
        token, lobby = held
        try:
            yield lobby
        finally:
            # Written even when the block raised -- see the note on the memory
            # store: every entry point records the caller's heartbeat before it
            # validates, and a refused request still proves that client is alive.
            self._release(code, token, lobby)

    @contextmanager
    def mutate_if_present(self, code: str) -> Iterator[Lobby | None]:
        held = self._acquire(code)
        if held is None:
            yield None
            return
        token, lobby = held
        try:
            yield lobby
        finally:
            self._release(code, token, lobby)


# ---------------------------------------------------------------------------
# Choosing one
# ---------------------------------------------------------------------------


def build_store() -> LobbyStore:
    from app.config import get_settings

    settings = get_settings()
    if settings.lobbies_are_shared:
        from app.db import get_client

        return SupabaseStore(get_client())
    return MemoryStore()
