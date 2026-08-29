# Quiz Quiz

**Zuordnungsfragen** (matching questions) with **all logic in Python**. The
frontend renders and collects input; it holds no rules about what a correct
answer is.

One topic = one question. Players assign answers to categories — and some
answers are **fakes** that belong to no category at all. Spotting those is part
of the game.

```
Topic:       Hauptstädte Europas

Categories:  Deutschland   Frankreich   Italien   Spanien
Answers:     Berlin  Paris  Rom  Madrid  Lissabon  Wien  Warschau
                                          └──── belong nowhere ────┘
```

The last three are **near misses, not nonsense**: real capitals that look
exactly like the others, but no Portugal, Austria or Poland category is offered.
That is what makes the question hard — an answer that is obviously absurd would
be spotted instantly and waste a slot.

```
Browser
   |  HTTP (JSON)
Next.js 16 + shadcn/ui        <- presentation only
   |  HTTP (JSON)
FastAPI (Python 3.12)         <- every rule lives here
   |  PostgREST + service-role key
Supabase Postgres             <- questions only, no play data
```

Content is German; code and schema identifiers are English.

## Requirements

- Docker Desktop (running)
- Node.js 20+ (for the Supabase CLI wrapper only)

## Quick start

```bash
npm install            # installs the Supabase CLI locally
npm run db:start       # boots Supabase in Docker (first run pulls ~2 GB)
cp .env.example .env   # then paste the service_role key printed above
docker compose up      # builds and starts the API and frontend
```

| Service            | URL                        |
| ------------------ | -------------------------- |
| Frontend           | http://localhost:3000      |
| API                | http://localhost:8001      |
| API docs (Swagger) | http://localhost:8001/docs |
| Supabase Studio    | http://127.0.0.1:54323     |

The API is on **8001**, not 8000, because 8000 is commonly taken. Change
`API_PORT` in `.env` to move it.

Frontend edits need `docker compose restart web` — Turbopack's file watcher does
not see changes across the Docker bind mount on Windows. The source is mounted,
so the restart takes seconds and needs no rebuild. (The Python side does reload
on save; uvicorn's watcher handles the mount fine.)

## The data model

Four tables.

```
subjects                     the quiz pool: "Geografie", "Musik"
  id, slug, name, position

quizzes       -> subject_id  one Zuordnungsfrage
  id, slug, title, description, difficulty
  source_url, source_title   where it was written from

categories    -> quiz_id     the buckets: "Deutschland"
  id, label, position

items         -> quiz_id     the answers: "Berlin", "Barcelona"
  id, label, position, category_id NULL
```

**`subject` and `category` are different things**, and the naming is deliberate.
A *subject* is the area a whole question belongs to and is what the host picks
before a game. A *category* is a bucket inside one question, and is what players
sort answers into during a round. Calling both "category" would mean the host
picks categories and then players sort into different categories.

**`items.category_id IS NULL` means the item is a fake.** No separate distractor
table, no flag column — one nullable foreign key says "belongs nowhere", and
grading a fake becomes `None == None`.

The composite foreign key `(category_id, quiz_id) → categories (id, quiz_id)`
stops an item from being assigned to a category belonging to a different topic.

**Nothing about gameplay is stored.** There is no players table, no attempts, no
scores, no auth. `/check` grades a submission and returns the result; the row
count in the database is exactly the same afterwards. A nickname, if you add
one, stays in the browser.

## Multiplayer

Several players join a lobby by code, then take turns. **Lobby state lives in
the API process, not the database** — it is gone on restart, and no row about a
player is ever written.

Rules, as implemented in `api/app/services/lobbies.py`:

- One placement per turn, then the turn passes — right or wrong.
- A wrong placement also knocks that player out **for the rest of the round**.
  They come back at the next topic.
- A correct placement scores **1 point**. Spotting a fake counts.
- A round ends when every item is placed **or** nobody is left active — so the
  last player standing keeps going alone while items remain.
- Between rounds the answers go up with a **Next round** button on every screen.
  It is a vote, not the host's alone: once **half of the connected players**
  have pressed it a **three-second countdown** runs on every device at once and
  the next round starts when it reaches zero. Half rather than all, so one
  player who has wandered off cannot hold the table up — and a vote from
  somebody whose tab has since gone stops counting.
- The host picks **subjects and a round count**, not individual questions. The
  server draws that many at random, spread as evenly as possible across the
  chosen subjects — 5 rounds over 3 subjects gives 2/2/1, and which subject
  gets the extra one varies. Asking for more rounds than exist simply plays
  everything available. Only hand-written questions are drawn — see
  `PLAYABLE_ORIGIN` under [Design decisions](#design-decisions). See
  `api/app/services/drafting.py`.
- Scores carry across rounds, and the highest total wins. Ties report every
  winner.
- The starting player rotates each round.
- Anyone can **leave** at any point. If it was their turn it passes on; if they
  were the host the role moves to whoever is left; if they were the last active
  player the round ends just as a wrong answer would; and once the last player
  leaves the lobby is discarded. Leaving is permanent — the seat is gone.
- **Closing a tab is not leaving.** The player is marked disconnected, keeps
  their seat and score, and can come back. See below.

### Presence

Two separate states, deliberately:

| | meaning | resets |
| --- | --- | --- |
| `is_active` | knocked out this round by a wrong answer | every round |
| `is_connected` | their client stopped checking in (10s) | when they return |

A player can only be dealt a turn when **both** are true.

The client already polls `GET /lobbies/{code}` every 1.5s, so that poll carries
`?player_id=` and doubles as the **heartbeat** — no extra traffic. Miss it for
`PRESENCE_TIMEOUT` (10s, several polls' grace) and the player is treated as
gone. On `pagehide` the browser also fires `POST /lobbies/{code}/away` with
`keepalive`, which hands the turn on instantly; that is an optimisation only,
since browsers do not guarantee unload requests. The timeout is what makes it
correct.

Any request from a client counts as proof of life, including a rejected one —
a client making requests is a client that is there.

A disconnected player is **skipped, not knocked out** — `is_active` and their
score are untouched, they just lose that turn and rejoin the rotation when it
comes round again. Only a wrong answer knocks you out.

The 10s grace is deliberate, but it would otherwise look like a hang, so
`LobbyView.current_player_quiet` goes true once the player on the clock has been
silent for `QUIET_AFTER` (3s, two missed polls). The other screens then show
"… has stopped responding — skipping shortly" instead of a stuck "Waiting for
…". It is advisory only: a quiet player can still take their turn, and the flag
clears itself either when they check back in or when the turn is handed on.

```
 t=0.0  Waiting for Anna…
 t=3.0  Anna has stopped responding — skipping shortly
 t=10.5 your turn
```

Because a disconnect could otherwise stall the game with nobody submitting
anything, every read re-checks presence and moves the clock off a player who is
no longer there. Two consequences follow:

- Someone being offline never stalls the players who are still present: a round
  ends when nobody **can** play, not when nobody is nominally active.
- If *everyone* disconnects the game **freezes** instead of racing through the
  remaining rounds to a meaningless winner. It resumes when anyone comes back.

**Coming back** works two ways. The same browser still has the player id in
`localStorage`, so reopening the link resumes automatically. From a fresh
browser, joining with the same nickname reclaims the seat, score and place in
the turn order — matching is case- and whitespace-insensitive. A *connected*
player's nickname cannot be taken. The nickname is the only credential, which
is fine for a party game but does mean anyone with the code and a name can
claim a disconnected seat.

```
POST /lobbies                     {nickname}                 -> {code, player_id}
POST /lobbies/{code}/join         {nickname}                 -> {code, player_id}
                                  (also reclaims a disconnected seat)
GET  /lobbies/{code}?player_id=   poll + heartbeat           -> LobbyView
POST /lobbies/{code}/start        {player_id, subject_slugs[], round_count}
                                                             -> LobbyView  (host)
POST /lobbies/{code}/turns        {player_id, item_id, category_id}
POST /lobbies/{code}/next-round   {player_id}                -> LobbyView
                                  ("I have read the answers" — half of those
                                   present starts the three-second countdown)
POST /lobbies/{code}/away         {player_id}                -> 204  (tab closing)
POST /lobbies/{code}/leave        {player_id}                -> 204  (permanent)
POST /lobbies/{code}/restart      {player_id}                -> LobbyView  (host)
```

`category_id: null` on a turn means "I say this one is a fake". The frontend
polls `GET /lobbies/{code}` every 1.5s; each response carries a `version` that
increments on every mutation, so a poll that overtakes a turn response is
discarded rather than showing stale state.

The player id doubles as the turn secret and is kept in `localStorage` per lobby
code, so a refresh mid-game does not drop you out.

**The lobby view never reveals an unplaced answer.** Only items already placed
correctly carry a `category_id`; everything else is `{id, label}`.

> Lobbies need a single long-lived process. They do **not** work on Vercel's
> serverless runtime, where each request may hit a different instance with its
> own empty dict. See [Deploying](#deploying).

## Layout

```
├── api/                   FastAPI backend -- all business logic
│   ├── app/
│   │   ├── main.py          app wiring, CORS, error handling
│   │   ├── config.py        env-driven settings
│   │   ├── db.py            Supabase client (service-role)
│   │   ├── schemas.py       Pydantic models = the API contract
│   │   ├── routers/         HTTP layer, thin
│   │   └── services/
│   │       ├── quizzes.py     reads + grading orchestration
│   │       ├── lobbies.py     ephemeral multiplayer state + turn loop
│   │       ├── drafting.py    balanced question draw across subjects
│   │       └── scoring.py     <- the rules live here
│   ├── tests/
│   ├── index.py           Vercel entrypoint
│   └── vercel.json
├── web/                   Next.js frontend -- presentation only
│   └── src/
│       ├── app/quizzes/[slug]/quiz-player.tsx   solo assignment board
│       ├── app/play/                            create or join a lobby
│       ├── app/lobby/[code]/lobby-room.tsx      live multiplayer game
│       ├── components/      shadcn/ui + app components
│       └── lib/api.ts       the only module that calls the backend
├── tools/ingest/          Wikipedia -> local model -> Supabase generator
│   └── README.md          how it works, and what it rejects
├── supabase/
│   ├── migrations/        forward-only SQL
│   └── seed.sql           9 subjects x 3 German questions, all with fakes
└── docker-compose.yml     api + web (database is separate, see below)
```

## Why the database is not in docker-compose

`supabase start` runs its own Docker stack (Postgres, PostgREST, Studio).
Duplicating that as a plain `postgres` service would give you a local
environment that behaves differently from hosted Supabase.

The cost is that the two stacks are on separate Docker networks, so the API
reaches Supabase via `host.docker.internal` rather than a service name. That is
what `SUPABASE_URL` in `.env` points at.

## API surface

| Method | Path                       | Purpose                                       |
| ------ | -------------------------- | --------------------------------------------- |
| GET    | `/health`                  | liveness + database reachability              |
| GET    | `/subjects`                | quiz-pool areas with question counts          |
| GET    | `/quizzes?subject=slug`    | questions, optionally filtered by subject     |
| GET    | `/quizzes/{slug or id}`    | one question; items shuffled, **no solution** |
| POST   | `/quizzes/{slug}/check`    | grade an assignment; stores nothing           |

`/check` takes `{"assignments": [{"item_id": "...", "category_id": "..." }]}`.
A `category_id` of `null` means "this is a fake". Items you omit are treated as
unassigned, which is correct only if they really were fakes.

## Common tasks

```bash
# Database
npm run db:start / db:stop / db:status
npm run db:reset                     # re-apply migrations + reseed
npm run db:diff add_new_topic        # generate a migration from Studio changes

# Backend
docker compose exec api pytest
docker compose exec api ruff check .

# Frontend
docker compose restart web           # after any frontend edit
docker compose exec web npx tsc --noEmit
docker compose exec web npx eslint src
```

To change the schema: add a **new** file in `supabase/migrations/` and run
`npm run db:reset`. Never edit an applied migration.

**Generating questions** from Wikipedia — most-read articles in, validated
Zuordnungsfragen out, with a difficulty rating and a source link. Runs entirely
on your machine against a local model in the project's Ollama container; no API
key, no data leaving the host:

```bash
pip install -r tools/ingest/requirements.txt
docker compose up -d ollama                       # port 11435
docker compose exec ollama ollama pull gemma4:12b  # ~7.6 GB, once

python -m tools.ingest --limit 10            # dry run + JSON report
python -m tools.ingest --limit 10 --commit   # write to Supabase
```

Dry run is the default. Generated questions land in `quizzes` with
`origin = 'ingest'` and are **not dealt** until somebody reads one and sets its
origin to `seed`. **[POPULATING.md](POPULATING.md)** is the runbook — every
command from an empty database to a reviewed pool, plus the verification
queries and what to do when a run goes wrong. [tools/ingest/README.md](tools/ingest/README.md)
explains why the pipeline is built the way it is.

**Adding a question by hand** means adding one row to the `spec` table in
`supabase/seed.sql`:

```sql
('musik', 'genres-instrumente', 'Genres & Instrumente',
 'Welches Instrument prägt das Genre?',
 'medium', 'Musikgenre', 'https://de.wikipedia.org/wiki/Musikgenre',
 '[["Jazz", ["Saxophon"]], ["Blues", ["Mundharmonika"]]]'::jsonb,
 array['Dudelsack', 'Sitar']),        -- belong to no category: the fakes
```

Then `npm run db:reset`. Everything else — quiz, categories, items, positions —
is derived from that row. Or edit rows directly in Supabase Studio; the API
reads whatever is there.

> The seed is one large statement rather than a PL/pgSQL helper because the
> Supabase CLI's seed runner cannot execute a `$$`-quoted function body. It
> works fine through `psql`, so the constraint is the tool, not the SQL.

> Run `next build` on the host or via `docker build --target production ./web`,
> not inside the running dev container. That container sets
> `NODE_ENV=development`, which breaks the production build in confusing ways.

## Design decisions

**The source is hidden until the question is over.** `source_url` points at the
material a question was written from, so during play it is a link straight to
the answers. The service layer keeps two column sets — `QUIZ_COLUMNS` for
players, `QUIZ_SOLUTION_COLUMNS` (source included) for grading — so the source
is physically absent from every mid-game payload, the same way `category_id` is.
It appears in the response to `/check`, and on the multiplayer scoreboard once a
round has ended.

**Solutions never reach the browser mid-game.** `schemas.py` defines `ItemPublic`
(id + label) separately from `ItemSolution` (with `category_id`). The player
route can only return the former, so a frontend bug cannot leak the answer — the
field simply is not in the payload. Verified by test, not by convention.

**Only hand-written questions are played.** `quizzes.origin` separates the
`seed` pool — written by a person, checked against its source, worded to be read
out — from what `tools/ingest` generated. `PLAYABLE_ORIGIN` in
`api/app/services/quizzes.py` is the one place that says which is dealt, and it
governs the subject counts a host picks from as well as the draw itself, so the
number on the picker is the number that will be played. Generated rows stay in
the table; they are worth reading through and promoting, not deleting.

**Items are shuffled server-side.** Seed rows are stored grouped by category, so
the stored order would give the grouping away.

**Fakes need no special case.** A fake has `category_id = NULL`; a player
declaring an item fake sends `null`. Grading is `assigned == correct`, and
`None == None` handles it.

**Grading iterates the answer key, not the submission.** An item the player
never touched counts as unassigned, and an unknown item id in the submission
cannot inflate the score.

**Services never import FastAPI.** `app/services/` raises `AppError` subclasses
that `main.py` maps to status codes, so business logic is unit-testable without
a request context — see `tests/test_scoring.py`.

**Row level security is on with no policies.** The backend uses the service-role
key, which bypasses RLS; `anon` and `authenticated` are granted nothing. A leaked
publishable key reads zero rows — including `items.category_id`.

**Two API URLs, on purpose.** Server components run inside the container and use
`API_URL=http://api:8000`; the browser uses
`NEXT_PUBLIC_API_URL=http://localhost:8001`. `lib/api.ts` picks between them.

## What is deliberately unfinished

- **Single API process only.** Lobbies are an in-memory dict. Two uvicorn
  workers means two independent sets of lobbies. Scaling out needs Redis or
  Supabase Realtime behind the same `lobbies.py` interface.
- **Polling, not push.** 1.5s polling is fine for a party game and needs no
  infrastructure. Websockets or Supabase Realtime would tighten it.
- **No turn timeout.** Presence handles a player who *disappears*, but one who
  sits there doing nothing still holds the turn indefinitely. A per-turn
  deadline that auto-passes would close this.
- **Content editing.** No admin UI or write endpoints beyond `create_quiz`.
  Edit through Supabase Studio or `seed.sql` for now.
- **Other question types.** The schema is shaped for Zuordnungsfragen. Adding a
  second type means a `kind` column on `quizzes` and a matching branch in
  `scoring.py`; nothing in the current model blocks it.
- **Difficulty is stored but not used to pick questions.** Every question has an
  easy/medium/hard rating, shown in the UI, but the draw balances across
  subjects only — so a round's difficulty is still luck. Filtering or laddering
  by difficulty is a change to `drafting.py`.
- **Frontend types are hand-written.** `web/src/lib/types.ts` mirrors
  `schemas.py` manually. Generate them once the shapes churn:
  `npx openapi-typescript http://localhost:8001/openapi.json -o src/lib/api-types.ts`

## Deploying

Two Vercel projects from the same repository.

**Frontend** — root directory `web`, framework preset Next.js. Environment
variables: `NEXT_PUBLIC_API_URL` and `API_URL`, both pointing at the deployed
API.

**Backend** — root directory `api`; `vercel.json` routes everything to
`index.py`. Environment variables: `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS` (the frontend's URL),
`ENVIRONMENT=production`.

**Database** — create a Supabase project, then:

```bash
npx supabase link --project-ref <ref>
npx supabase db push          # applies migrations; does NOT run seed.sql
```

### Multiplayer does not work on Vercel

Vercel runs Python as **serverless functions**: cold starts, no shared memory
between instances. Reading topics and the solo `/check` endpoint are fine there.
**Lobbies are not** — the in-memory dict would be empty on whichever instance
handles the next request, so players would get "No lobby with code …" at random.

Host the API on a container platform instead (Fly.io, Render, Railway — all have
free tiers). The `production` stage in `api/Dockerfile` already builds that
image; only `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` change. The frontend can
still sit on Vercel.

Never put `SUPABASE_SERVICE_ROLE_KEY` in a `NEXT_PUBLIC_*` variable — those are
inlined into the client bundle at build time.





### CLI Commands

docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d ollama

python -m tools.ingest --limit 10 --trace