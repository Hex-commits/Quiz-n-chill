-- Live game state, so a lobby can outlive the process that created it.
--
-- The API runs on more than one instance in production -- serverless, where
-- consecutive requests from one player land on different machines. A lobby held
-- in process memory is invisible to the next request, so it lives here instead.
--
-- **This is not history.** A row exists only while its game does. There is no
-- record of who played, what they scored, or that a game happened at all: rows
-- carry an expiry, `sweep_lobbies()` removes them, and restarting the lobby
-- deletes and replaces. The promise the rest of this schema makes -- questions
-- are stored, players are not -- is unchanged. What is stored here is a game in
-- progress, and it disappears with the game.
--
-- The whole lobby is one jsonb document rather than a set of normalised tables.
-- It is written and read as a unit by exactly one writer, never queried by its
-- contents, and its shape is owned by the API's dataclasses. Normalising it
-- would mean maintaining that shape in two places for no query we ever make.

create table lobbies (
    code         text primary key,
    -- The serialised Lobby. Includes the answer key for the round in play,
    -- which is why nothing but the service role may read this table.
    state        jsonb       not null,
    -- Mirrored out of the document so a caller can check for a change without
    -- fetching and parsing the whole thing.
    version      integer     not null default 0,
    -- Mutual exclusion. Two players can act at the same instant, and a
    -- read-modify-write that interleaves loses one of them.
    lock_token   text,
    locked_until timestamptz,
    updated_at   timestamptz not null default now(),
    expires_at   timestamptz not null
);

comment on table lobbies is
    'Games in progress. Ephemeral by design: no history is kept, and rows are '
    'swept once they expire.';

-- The sweep's access path, and it keeps the table small enough that nothing
-- else needs one -- lookups are all by primary key.
create index lobbies_expires_at_idx on lobbies (expires_at);

-- ---------------------------------------------------------------------------
-- Row level security
--
-- Enabled with no policies, exactly like the question tables. The API holds the
-- service-role key and bypasses this; anon and authenticated get nothing.
--
-- That is load-bearing rather than tidy. `state` contains the loaded round,
-- including every item's category_id and explanation -- the complete solution
-- to the question being played. A readable row would hand players the answers.
-- ---------------------------------------------------------------------------

alter table lobbies enable row level security;

grant all privileges on table lobbies to service_role;

-- ---------------------------------------------------------------------------
-- Locking
--
-- PostgREST gives no transaction spanning a read and a later write, so the lock
-- cannot be a `select ... for update` held by the caller. These two functions
-- are the substitute: one takes the lobby and hands back its state, the other
-- writes and lets go. Both are single statements, so each is atomic on its own.
--
-- The lock has a deadline rather than a holder that must come back. A crashed
-- or timed-out instance would otherwise wedge a lobby permanently, and on
-- serverless an instance can vanish mid-request.
-- ---------------------------------------------------------------------------

-- `setof` rather than `lobbies`: a plain composite return type hands back a row
-- of nulls when nothing matched, which a caller has to tell apart from a real
-- row by inspecting its fields. An empty set is unambiguous.
create function lobby_acquire(p_code text, p_token text, p_ttl_seconds integer)
returns setof lobbies
language sql
security definer
set search_path = public
as $$
    update lobbies
       set lock_token   = p_token,
           locked_until = now() + make_interval(secs => p_ttl_seconds)
     where code = upper(p_code)
       -- Free, or the previous holder's deadline has passed.
       and (locked_until is null or locked_until < now())
    returning *;
$$;

comment on function lobby_acquire is
    'Take the lobby lock and return the row, or nothing if another writer holds '
    'it. now() is evaluated by the database, so callers need no synchronised '
    'clock.';

create function lobby_release(
    p_code    text,
    p_token   text,
    p_state   jsonb,
    p_version integer,
    p_ttl_seconds integer
)
returns boolean
language sql
security definer
set search_path = public
as $$
    update lobbies
       set state        = p_state,
           version      = p_version,
           updated_at   = now(),
           expires_at   = now() + make_interval(secs => p_ttl_seconds),
           lock_token   = null,
           locked_until = null
     where code = upper(p_code)
       -- Only if we still hold it. A writer whose lock had already expired must
       -- not overwrite the work of whoever took it next.
       and lock_token = p_token
    returning true;
$$;

comment on function lobby_release is
    'Write the lobby back and release the lock. False if the lock had expired '
    'and been taken by someone else, in which case this write was refused.';

create function sweep_lobbies()
returns integer
language sql
security definer
set search_path = public
as $$
    with gone as (
        delete from lobbies where expires_at < now() returning 1
    )
    select count(*)::integer from gone;
$$;

comment on function sweep_lobbies is
    'Delete finished and abandoned games. Called opportunistically by the API; '
    'nothing depends on it running on a schedule.';

revoke all on function lobby_acquire(text, text, integer) from public, anon, authenticated;
revoke all on function lobby_release(text, text, jsonb, integer, integer) from public, anon, authenticated;
revoke all on function sweep_lobbies() from public, anon, authenticated;

grant execute on function lobby_acquire(text, text, integer) to service_role;
grant execute on function lobby_release(text, text, jsonb, integer, integer) to service_role;
grant execute on function sweep_lobbies() to service_role;
