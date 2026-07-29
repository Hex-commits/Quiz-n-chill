# Populating the database

Every command needed to get from an empty database to a playable pool of
questions. Run from the repo root.

For *why* the pipeline works the way it does, see
[`tools/ingest/README.md`](tools/ingest/README.md). This file is the runbook.

---

## TL;DR

```bash
npm run db:start                                   # Supabase on 54321/54322/54323
docker compose up -d ollama                        # model server on 11435
docker compose exec ollama ollama pull glm4:9b     # ~5.5 GB, once

python -m tools.ingest --limit 20 --workers 4              # dry run — read the report
python -m tools.ingest --limit 20 --workers 4 --commit     # write it
```

Dry run is the default **on purpose**. These questions are machine-written and
go straight into a game; skimming a batch first costs one command and catches
the ones that are technically valid but poor.

---

## 1. Bring the stack up

```bash
npm run db:start          # Supabase (its own docker stack, not compose)
npm run db:status         # prints the URLs and the anon key
docker compose up -d      # api on 8001, web on 3000, ollama on 11435
```

| | where |
| --- | --- |
| Game | http://localhost:3000 |
| API | http://localhost:8001 |
| Supabase Studio | http://localhost:54323 |
| Postgres | `postgresql://postgres:postgres@localhost:54322/postgres` |

Migrations run automatically on `db:start` for a fresh stack. To replay them
over an existing one — **this wipes every question**:

```bash
npm run db:reset
```

To apply new migrations without wiping:

```bash
docker exec -i supabase_db_Quiz_Quiz psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  < supabase/migrations/<file>.sql
```

### Required environment

The repo-root `.env` needs at least:

```bash
SUPABASE_URL=http://host.docker.internal:54321
SUPABASE_SERVICE_ROLE_KEY=<from `npm run db:status`>
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from `npm run db:status`>
```

The last two are what enable realtime in the browser. Without them the lobby
silently falls back to polling and still works — which is why a missing key is
easy not to notice.

`.env` is gitignored. The ingest tool reads it too.

---

## 2. Check the GPU is doing the work

This is the difference between a 20-question run taking four minutes and taking
an evening.

```bash
docker compose exec ollama ollama ps      # PROCESSOR must read 100% GPU
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

`glm4:9b` needs roughly 9 GB free. If a game or an overlay is holding VRAM,
Ollama falls back to CPU and every model call goes from ~12s to ~3min. The
ingest header prints `[100% GPU]` or `[100% CPU]` at startup — read it.

No NVIDIA card:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d ollama
```

---

## 3. Populate

### The everyday command

```bash
python -m tools.ingest --limit 20 --workers 4 --commit
```

`--workers 4` matches `OLLAMA_NUM_PARALLEL=4` in the compose file. The two are
independent and the smaller wins, so raising one alone does nothing.

### Pick what it reads

```bash
# Balanced across all nine subjects — the best default for a fresh pool
python -m tools.ingest --limit 30 --source subjects --workers 4 --commit

# List articles: already tabulated into pairings, highest yield for pictures
python -m tools.ingest --limit 20 --source lists --workers 4 --commit

# Peer-reviewed articles, so the facts hold up
python -m tools.ingest --limit 20 --source vetted --workers 4 --commit

# Named articles, nothing sampled
python -m tools.ingest --titles Sonnensystem Bundesliga Periodensystem --commit
```

| `--source` | draws from |
| --- | --- |
| `mixed` (default) | round-robin over the five below |
| `subjects` | category members, evenly across the nine subjects |
| `lists` | popular "Liste der …" articles |
| `vetted` | `Wikipedia:Exzellent` / `:Lesenswert` |
| `evergreen` | sustained popularity over `--months` (default 24) |
| `recent` | today's top list — half of it is people in the news |

**Use `subjects` when filling an empty database.** The game deals rounds evenly
across subjects, so a pool that is four-fifths geography makes a poor game
however good the individual questions are.

### Faster, rougher

```bash
python -m tools.ingest --limit 40 --no-review --workers 4 --commit   # ~half the time
python -m tools.ingest --limit 40 --no-pictures --workers 4 --commit # no Wikidata/Commons calls
python -m tools.ingest --limit 40 --no-explain --workers 4 --commit  # no per-answer reasons
python -m tools.ingest --limit 20 --quiet                            # one line per article
```

`--no-review` drops the second model pass that checks the question against the
article. It roughly halves the time and measurably lowers the quality — fine for
filling a dev database, not for anything anyone plays.

---

## 4. Read the report before you trust it

Every run writes to `tools/ingest/out/`:

| File | For |
| --- | --- |
| `ingest-<stamp>.md` | **Reading.** Pairings, source link, picture thumbnails, per-answer explanations. Rejections tabled with the reason. |
| `ingest-<stamp>.json` | The machine record, for diffing or re-processing. |

```bash
ls -t tools/ingest/out/*.md | head -1        # newest report
```

The Markdown exists for the one question nothing automatic can answer: **is each
pairing actually true?** A model will happily pair a plausible answer with the
wrong category, and the result is a question that marks a correct player wrong.

---

## 5. Verify what landed

```bash
# Counts by kind
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "select category_kind, count(*) from quizzes group by 1;"

# Pool balance across subjects — the thing that decides whether the game is fun
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "select s.slug, count(q.id) from subjects s
      left join quizzes q on q.subject_id = s.id group by 1 order by 2 desc;"

# Picture questions: every category must have a file AND a licence
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "select q.slug, count(c.id) pairs, count(c.image_file) imgs, count(c.image_licence) lic
      from quizzes q join categories c on c.quiz_id = q.id
      where q.category_kind = 'image' group by q.slug;"

# The newest questions, with their instruction line
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "select slug, category_kind, description from quizzes
      order by created_at desc limit 10;"
```

`pairs`, `imgs` and `lic` must be equal for every picture question. They cannot
disagree — `categories_image_is_complete` refuses a file without a licence — but
checking is free and a blank card mid-game is not.

---

## 6. Removing things

```bash
# One question
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "delete from quizzes where slug = '<slug>';"

# Every picture question, to regenerate them
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "delete from quizzes where category_kind = 'image';"

# Everything (categories and items cascade)
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "truncate quizzes cascade;"
```

Deleting a quiz cascades to its categories and items. Subjects are seeded by
migration and survive.

---

## Filling a hosted project

Same command, both halves pointed at the same project. **The URL and the key
have to name the same project** — pointing the URL at production while the key
still belongs to the local stack fails with an unhelpful auth error.

```bash
python -m tools.ingest --limit 50 --commit \
  --supabase-url https://<project>.supabase.co \
  --supabase-key <service-role key for that project>
```

The URL is echoed at startup (`Supabase at …`) and named in any connection
error, because writing questions into the wrong database is a quiet kind of
wrong. Read it before you walk away from a 50-article run.

Push the schema first, or the write fails on a missing column:

```bash
supabase link --project-ref <ref>
supabase db push
```

---

## Settings, and where they come from

**Precedence: command line > environment > repo-root `.env` > default.**

| Variable | Flag | Default |
| --- | --- | --- |
| `SUPABASE_SERVICE_ROLE_KEY` | `--supabase-key` | — |
| `INGEST_SUPABASE_URL` | `--supabase-url` | `SUPABASE_URL` with `host.docker.internal` → `127.0.0.1` |
| `OLLAMA_URL` | `--ollama-url` | `http://localhost:11435` |
| `INGEST_MODEL` | `--model` | `glm4:9b` |

`INGEST_SUPABASE_URL` exists because `.env` sets `SUPABASE_URL` for the
*containers*, where the stack answers to `host.docker.internal` — a name that
does not resolve on the host this tool runs on.

Full flag list:

```bash
python -m tools.ingest --help
```

---

## When it goes wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| `[100% CPU]` in the header | something else holds VRAM | close it, `docker compose restart ollama` |
| Every article `DROPPED` with duplicates | the model repeats an answer and the repair loop cannot shake it | `--attempts 4`, or a different `--source` |
| `Unknown subject slug` | database has no subjects | `npm run db:reset` to replay the seed |
| Nothing written, no error | missing `--commit` | it was a dry run |
| Run adds nothing on a re-run | articles already used | expected — `source_url` is deduplicated |
| HTTP 429 mid-run | Wikipedia rate limit | it backs off on its own; leave it |
| Picture questions never appear | not enough resolvable names | expected — needs 10 pairs whose labels resolve on Wikidata |
| The same questions keep coming up | the pool is smaller than the games played | the "already played" preference is soft; it falls back once nothing new is left |

**A note on repeats.** The lobby remembers which questions this browser has
played and asks the server to prefer others. It is a preference, not a filter —
so a small pool still repeats, it just repeats last. Questions with 15 or more
pairs are never counted as played, because the board deals a random 10 and is
different each time. The host's setup card has a **Reset** button.

The practical fix for repeats is more questions:

```bash
python -m tools.ingest --limit 40 --source subjects --workers 4 --commit
```

**Re-running is safe.** An article whose URL is already a `source_url` is
skipped, so a second run adds new questions rather than duplicates.

---

## Tests

```bash
python -m pytest tools/ingest/tests -q     # ingest, no network or database
docker exec quiz_api python -m pytest -q   # API contract
```
