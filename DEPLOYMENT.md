# Deploying to Vercel

Two Vercel projects from one repository, plus the Supabase project they share.

```
  browser ──► web (Next.js)  ──► api (FastAPI)  ──► Supabase Postgres
                   │                                    questions
                   └──── Supabase Realtime ◄────────────  lobbies
                          "something changed"
```

The frontend never talks to the database. It calls the API for everything and
listens to Realtime only to hear *that* a lobby changed — never *what* changed.
That is what keeps the answer key server-side, and it is the constraint to
preserve if any of this is rearranged later.

---

## 1. Two projects, not one

This is a monorepo, so each Vercel project needs its **Root Directory** set in
the dashboard. Vercel builds only that directory.

| Project | Root Directory | Framework |
| --- | --- | --- |
| `quiz-n-chill-api` | `api` | Other |
| `quiz-n-chill-web` | `web` | Next.js |

The API's routing lives in `api/vercel.json`: every path goes to `index.py`,
which exposes the FastAPI app. Nothing about local development uses that file —
Docker runs `uvicorn app.main:app` directly.

---

## 2. Environment variables

### API project

| Variable | Value | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | |
| `SUPABASE_SERVICE_ROLE_KEY` | the service-role key | **Never** on the web project |
| `SHARED_LOBBIES` | `true` | Required. See §3 |
| `REALTIME_BROADCAST` | `true` | Lets clients stop polling |
| `ENVIRONMENT` | `production` | Makes `ADMIN_TOKEN` mandatory |
| `ADMIN_TOKEN` | a long random string | Guards the admin routes |
| `CORS_ORIGINS` | *(optional)* | Defaults already allow the deployed frontend. See §4 |
| `CORS_ORIGIN_REGEX` | *(optional)* | Defaults already allow this project's previews |
| `FIRST_TURN_BONUS_SECONDS` | *(optional)* | Extra seconds for whoever opens a round. Default `10`, `0` disables |

### Web project

| Variable | Value | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://<your-api-domain>` | Inlined at **build** time |
| `API_URL` | same as above | Used by server components |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` | |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **anon / publishable** key | Never the service-role key |

Two traps worth naming:

**`NEXT_PUBLIC_*` is baked into the bundle at build time**, not read at runtime.
Changing one means redeploying, not just editing the variable.

**Do not attach the Vercel↔Supabase integration to the web project.** It injects
a service-role key into the environment, and a Next.js project is one careless
`NEXT_PUBLIC_` reference away from shipping that to the browser. The frontend
needs no database access at all. Attach it to the API project only, or set the
variables by hand.

---

## 3. `SHARED_LOBBIES` is not optional here

Left `false`, the API keeps lobbies in process memory. On Vercel every request
may land on a different instance, so:

- Anna creates lobby `TR3X` → instance A holds it
- Ben joins → instance B → **"No lobby with code TR3X"**

With it `true`, lobbies live in `public.lobbies` and every instance sees the same
game. Locking is handled by two SQL functions (`lobby_acquire`, `lobby_release`)
so two players submitting at the same instant cannot overwrite each other.

Nothing durable is kept: rows carry an expiry and `sweep_lobbies()` removes them.
The database stores questions and games in progress — never a record of who
played.

---

## 4. CORS, and why previews break without it

Vercel gives every preview deployment its own hostname, which does not exist when
you configure the API. `CORS_ORIGINS` is an exact list, so previews fail CORS —
the API answers fine and the browser discards the response, with nothing in the
server log to say why.

`CORS_ORIGIN_REGEX` covers them. Anchor it and include your project prefix:

```
^https://quiz-n-chill-web-[a-z0-9-]+\.vercel\.app$
```

Not `.*\.vercel\.app` — credentials are allowed, so a loose pattern would let
**anyone's** Vercel project call your API as the player.

Both of these already **default** to the right values in `app/config.py`, so a
fresh deploy needs no CORS configuration at all. They are defaults rather than
environment variables because a CORS failure is invisible from the server: the
API answers normally, the browser discards the response, and nothing appears in
any log. The setup that requires no step is the one that should be correct.

Set the environment variables only when the frontend moves to a different
domain. `api/tests/test_cors.py` pins the shipped defaults — including that
`someone-elses-app.vercel.app` and `quiz-n-chill-web.vercel.app.evil.example`
are refused.

### If a preflight fails with "Redirect is not allowed"

That is not CORS. It means the request URL had a double slash — `API_URL` ending
in `/` plus a path starting with `/` — which the server answers with a 308, and
browsers will not follow a redirect on a preflight. `baseUrl()` in
`web/src/lib/api.ts` strips trailing slashes so it cannot happen; the tests in
`web/src/lib/api.test.ts` keep it that way.

---

## 5. Deploy order

1. **Database first.** `npx supabase db push` — the API expects the `lobbies`
   table and its functions to exist.
2. **API next.** It has no dependency on the web project. Check
   `https://<api>/health` returns `"database": "connected"`.
3. **Web last**, once you know the API's URL, since `NEXT_PUBLIC_API_URL` is
   inlined at build time.
4. Set `CORS_ORIGINS` on the API to the web domain and redeploy the API.

---

## 6. Checks that actually catch things

```bash
# Schema matches the repo. Both columns populated for every row.
npx supabase migration list --linked

# The API is up and can reach the database.
curl https://<api>/health

# A player cannot read the answer key. Must return [].
curl "https://<ref>.supabase.co/rest/v1/items?select=category_id,explanation&limit=1" \
     -H "apikey: <anon key>"
```

That last one is the one not to skip. RLS filters rows rather than refusing the
request, so a `200` on its own proves nothing — what matters is that the body is
empty. Check it against a table that actually has rows in it.

Then open the game in two browsers: a move in one should appear in the other
within a second or so. If it takes ten, Realtime is not reaching the browser and
the room is falling back to its poll — check `NEXT_PUBLIC_SUPABASE_*` on the web
project and `REALTIME_BROADCAST` on the API.

---

## Known limits

**Free-tier Realtime** caps concurrent connections and messages. One connection
per open tab, one message per move.

**Cold starts.** A serverless API that has been idle takes a second or two on the
first request. The lobby's 10s poll keeps a busy game warm; the first player into
an empty lobby may wait.

**`maxDuration`.** Acquiring a lobby waits up to 3s for another writer before
giving up, well inside Vercel's default limit — but if you lower that limit,
keep it above `LOCK_WAIT` in `api/app/services/lobby_store.py`.
