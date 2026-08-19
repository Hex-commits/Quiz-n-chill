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
docker compose exec ollama ollama pull gemma4:e4b-it-q4_K_M   # ~9.6 GB download, once

python -m tools.ingest --limit 2 --workers 4              # dry run — read the report
python -m tools.ingest --limit 20 --workers 8 --commit     # write it
```

**Pull the tag with the `-it-q4_K_M` suffix, not bare `gemma4:e4b`.** They happen
to be the same build today (identical digest), but the suffix is what pins the
quantisation — the family does not quantise every tag alike, and `gemma4:12b` is
a 7.6 GB download against this one's 9.6 GB.

The download is 9.6 GB and the *resident* size is 3.4 GB: the tag ships several
nested weight sets and only the active slice is loaded. Judge VRAM by
`ollama ps`, never by `ollama list`.

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

Measured on the 12 GB RTX 4070 this was built against, with the eight parallel
slots and a 16k context: **3.9 GB resident, 100% GPU, 4.4 GB still free.** That
is the whole reason the run model is a 4B — `gemma4:12b` took 8.6 GB for the same
job at half the tokens per second.

Confirm rather than assume: `ollama ps` prints what it actually took and whether
all of it landed on the card.

If a game or an overlay is holding VRAM, Ollama falls back to CPU and every
model call goes from ~12s to ~3min. The ingest header prints `[100% GPU]` or
`[100% CPU]` at startup — read it. The fix is fewer slots, not a smaller model:
halve `OLLAMA_NUM_PARALLEL` and `--workers` together — they are independent and
the smaller wins, so moving one alone does nothing.

No NVIDIA card:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d ollama
```

---

## 3. Populate

### The everyday command

```bash
python -m tools.ingest --limit 20 --workers 8 --commit
```

`--workers 8` matches `OLLAMA_NUM_PARALLEL=8` in the compose file. The two are
independent and the smaller wins, so raising one alone does nothing.

Each article is drafted **five** ways in one `extract` call, and `select` keeps
the ones worth playing — so one article regularly yields more than one question,
and the report and the console both number them. That is where most of the
throughput comes from: `extract` is the expensive call and the only one that
reads the whole article, so the way to make a run cheaper per question is to get
more questions out of the one call. `--drafts 1` is the way back to one question
per article, and it skips `select` entirely.

An article the model declines as too thin is not dropped on the spot: `broaden`
searches Wikipedia for pages similar to it, reads two, and runs the extract call
again with them attached — a single article about one army post yields nothing,
three of them yield a board. It costs a search and one extra model call per
declined article, only ever runs once per article, and `--no-broaden` turns it
off. Questions written that way name the extra pages under **Also read** in the
report, because the source link alone will not settle every pairing.

The questions kept beyond the first run through the rest of the pipeline
concurrently, on their own worker pool. A run can therefore have up to twice
`--workers` requests in the air; Ollama serves `OLLAMA_NUM_PARALLEL` of them and
queues the rest, which is what stops a slot idling while an article sits in
`check` — a step that makes no model call at all.

### Pick what it reads

```bash
# Balanced across all nine subjects — the best default for a fresh pool
python -m tools.ingest --limit 30 --source subjects --workers 8 --commit

# List articles: already tabulated into pairings, highest yield for pictures
python -m tools.ingest --limit 20 --source lists --workers 8 --commit

# Peer-reviewed articles, so the facts hold up
python -m tools.ingest --limit 20 --source vetted --workers 8 --commit

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
python -m tools.ingest --limit 40 --no-review --workers 8 --commit   # ~half the time
python -m tools.ingest --limit 40 --no-pictures --workers 8 --commit # no Wikidata/Commons calls
python -m tools.ingest --limit 40 --no-explain --workers 8 --commit  # no per-answer reasons
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

# Who wrote them: 'seed' = by hand in supabase/seed.sql, 'ingest' = the model
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "select origin, count(*) from quizzes group by 1;"

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

# Every machine-written question, leaving the hand-written pool alone
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "delete from quizzes where origin = 'ingest';"

# Everything (categories and items cascade)
docker exec supabase_db_Quiz_Quiz psql -U postgres -d postgres \
  -c "truncate quizzes cascade;"
```

Deleting a quiz cascades to its categories and items. Subjects are seeded by
migration and survive.

`origin` is what makes the third command safe. Both kinds of question carry a
Wikipedia `source_url` and fill the same columns, so before that column existed
there was no way to clear a bad ingest run without hand-listing slugs — and
`created_at` is no help, since `db reset` re-stamps the seeded rows.

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

### The hand-written questions

`supabase db push` carries migrations only and `seed.sql` never runs against a
hosted project, so the files under `supabase/questions` need a way in that is
not `psql` — reaching the database directly wants the database password, while
the service-role key is already in `.env`.

```bash
python -m tools.questions.apply                     # every file, dry run
python -m tools.questions.apply --commit            # add what is missing
python -m tools.questions.apply --replace --commit  # rebuild the pool from the files
```

Boards whose slug already exists are skipped, so a second run adds only what is
new and an interrupted run is resumed by running it again. `--replace` deletes
every `origin = 'seed'` quiz first and writes them all back — the way to pick up
edits to a file that is already applied, since a board that exists is otherwise
left alone. Generated questions are never touched by it: they are `origin =
'ingest'` and exist in no file.

Use `psql < file.sql` instead wherever it is available. It runs the real
statement with the real constraints in one transaction; this tool parses the
file and writes over PostgREST, one board at a time.

---

## Settings, and where they come from

**Precedence: command line > environment > repo-root `.env` > default.**

| Variable | Flag | Default |
| --- | --- | --- |
| `SUPABASE_SERVICE_ROLE_KEY` | `--supabase-key` | — |
| `INGEST_SUPABASE_URL` | `--supabase-url` | `SUPABASE_URL` with `host.docker.internal` → `127.0.0.1` |
| `OLLAMA_URL` | `--ollama-url` | `http://localhost:11435` |
| `INGEST_MODEL` | `--model` | `gemma4:e4b-it-q4_K_M` |
| `INGEST_VET` | *(none)* | `false` |
| `INGEST_JUDGE_MODEL` | *(none)* | whatever `INGEST_MODEL` is |

The last two have **no command-line form on purpose** — they describe the
machine rather than the run. `INGEST_VET=true` turns on the step that judges
each borrowed pair against the board and rejects the ones asking a different
question; a rejection sends the question back to search another article.

It is off by default because the judgement measured at roughly chance on
`glm4:9b`, the model the pipeline was built and tuned on. That verdict has not
been re-taken on `gemma4:12b`, and it is the kind of judgement a stronger model
plausibly changes — so it is worth running a batch with `INGEST_VET=true` and
reading the rejections before deciding, rather than leaving it off on the
strength of a measurement about a model that is no longer installed. Point
`INGEST_JUDGE_MODEL` at something larger if you have it, and check the run
header — it prints `Vetting on` when it is active, since a setting in `.env` is
one you can forget about.

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
python -m tools.ingest --limit 40 --source subjects --workers 8 --commit
```

**Re-running is safe.** An article whose URL is already a `source_url` is
skipped, so a second run adds new questions rather than duplicates.

---

## Tests

```bash
python -m pytest tools/ingest/tests -q     # ingest, no network or database
docker exec quiz_api python -m pytest -q   # API contract
```
