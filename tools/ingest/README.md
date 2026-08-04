# Question ingestion

Fills the question pool from Wikipedia: read a popular article, have a local model turn
it into a Zuordnungsfrage, validate it, write it to Supabase.

Everything runs on this machine — the model is served by the project's own
Ollama container, so nothing leaves the host, there is no API key and no
per-token cost.

```
Wikipedia pageviews API  ──▶  most-read articles (de)
Wikipedia REST/Action    ──▶  article text + canonical URL
      ▼
   the graph  (LangGraph — see "The pipeline" below)
      ▼
Supabase                 ──▶  quizzes / categories / items
```

## Setup

```bash
pip install -r tools/ingest/requirements.txt

docker compose up -d ollama                       # port 11435
docker compose exec ollama ollama pull glm4:9b    # ~5.5 GB, once
```

The model lives in the `ollama_models` named volume, so `docker compose down`
does not cost a re-download.

**The GPU is doing the work, and it matters more than anything else here.** The
compose file hands the NVIDIA card to the container; Ollama finds CUDA on its
own and offloads what fits in VRAM. Measured on this project with glm4:9b (9.3 GB
resident) on an RTX 4070:

| | one extraction | per accepted question |
| --- | --- | --- |
| CPU | ~2m 49s | ~7 min |
| RTX 4070, 1 worker | ~12s | ~25s |
| RTX 4070, 4 workers | — | **~18s** |

Measured when `extract` wrote one question per call. It now writes `--drafts` of
them (default 2) and `select` chooses, so the extract call is longer and the
per-*article* cost is higher — but an article that yields two keepers pays for one
extraction across both, and these numbers have not been re-measured since.

Four parallel slots is the measured sweet spot on a 12 GB card: 8.6 GB resident
with 4.4 GB still free, and 18s per accepted question against 32s at two. The
compose file sets `OLLAMA_NUM_PARALLEL=4` plus flash attention and a `q8_0` KV
cache — the last two are what shrink the cache enough for the slots to fit.
Match it with `--workers 4`; the two numbers are independent and the smaller one
wins.

That is the difference between a ten-question run taking an evening and taking a
few minutes. Check it landed with `docker compose exec ollama ollama ps` — the
`PROCESSOR` column should read `100% GPU`, not `100% CPU`.

Docker treats the reservation as a hard requirement, so on a machine with **no
NVIDIA GPU** the container will refuse to start rather than fall back. Use the
override:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d ollama
```

If a model is larger than free VRAM, Ollama splits it and runs the remainder on
the CPU — no configuration needed, just proportionally slower.

Precedence is the same for every setting: **command line > environment >
repo-root `.env` > default.**

| Variable | Flag | Default | Notes |
| --- | --- | --- | --- |
| `SUPABASE_SERVICE_ROLE_KEY` | — | — | Same key the API uses; RLS is on with no policies |
| `INGEST_SUPABASE_URL` | `--supabase-url` | see below | The stack **as reachable from this machine** |
| `OLLAMA_URL` | `--ollama-url` | `http://localhost:11435` | 11435, not 11434, to avoid clashing with another project's Ollama |
| `INGEST_MODEL` | `--model` | `glm4:9b` | Any tag you have pulled |

**Why the Supabase URL has its own variable.** `.env` sets `SUPABASE_URL` for
the *containers*, where the stack answers to `host.docker.internal`. This tool
runs on the host, where that name usually does not resolve — so it reads
`INGEST_SUPABASE_URL` instead.

Leave it unset and it falls back to `SUPABASE_URL` with `host.docker.internal`
swapped for `127.0.0.1`. That is right for the default compose setup and wrong
for everything else, so set it explicitly to fill a different database — a
second local stack, a tunnel, or a hosted project:

```bash
INGEST_SUPABASE_URL=https://<project>.supabase.co
# or, for one run:
python -m tools.ingest --supabase-url https://<project>.supabase.co --commit
```

The URL is echoed at startup (`Supabase at …`) and named in the error if the
connection fails, because writing questions into the wrong database is a quiet
kind of wrong.

## Running

```bash
# Dry run (the default): generate and validate, write a JSON report, touch nothing
python -m tools.ingest --limit 10

# Read the report, then commit
python -m tools.ingest --limit 10 --commit

# Specific articles instead of the popularity list
python -m tools.ingest --titles Sonnensystem Bundesliga --commit

# One article, start to finish
python -m tools.ingest --titles Kaffee

# One line per article instead of one per pipeline step
python -m tools.ingest --limit 10 --quiet

# What is being read *today* -- mostly people in the news
python -m tools.ingest --source recent
```

### Following a run

Every step prints as it happens, timed, with a running tally after each article:

```
========================================================================
  Model      glm4:9b  via http://localhost:11435  [100% GPU]
  Vetting    off  (INGEST_VET)  borrowed pairs are unjudged -- read the report
  Supabase   http://127.0.0.1:54321
  Source     mixed, 24 months
  Pipeline   extract x2 -> select -> check -> review -> explain   (3 attempts per article)
  Mode       dry run -- nothing is written
========================================================================
40 candidates; aiming for 10 questions.

[  1/40] Periodensystem
        127,578 chars from https://de.wikipedia.org/wiki/Periodensystem
        extract    18.2s  2 drafts, 12 pairs
        select      2.4s  kept 2/2 -- beide fragen echtes Detailwissen ab
        check       0.0s  ok
        review      1.8s  ok
        explain     7.1s  12/12 answers explained
        check       0.0s  ok
        review      2.0s  ok
        explain     6.8s  11/11 answers explained
        ACCEPTED  30s  periodensystem-zuordnung (12 pairs, medium)
        ACCEPTED  39s  elementsymbole (11 pairs, hard)
        -> 2/10 accepted  |  0 dropped  |  0 skipped  |  ~2m36s left  |  39s elapsed
```

The per-step timings are the useful part: `check` is free, the three model calls
are not, and when a run drags it is always one of them. The header's `[100% GPU]`
is read from Ollama at startup — if it says `100% CPU`, that is the whole
explanation for a slow run.

`ACCEPTED` becomes `WRITTEN` under `--commit`, and `DROPPED` carries the reason.
The estimate extrapolates from accepted questions only, since skips are nearly
free and rejections are not.

**Dry run is the default on purpose.** These questions are machine-written and
go straight into a game; reading a batch before committing costs one command and
catches the ones that are technically valid but poor.

Every run writes two files to `tools/ingest/out/`:

| File | For |
| --- | --- |
| `ingest-<stamp>.md` | **Reading.** Each question laid out as its pairings, with the source link and each answer's explanation. Rejected articles are tabled with the reason. |
| `ingest-<stamp>.json` | The machine record — the exact payload, for re-processing or diffing. |

The Markdown is built for the one question nothing automatic can answer: **is
each pairing actually true?** A model will happily pair a plausible answer with
the wrong category, and the result is a question that marks a correct player
wrong. `validate.py` cannot see it; a person with the source open can, in about
ten seconds per question.

## Which articles it tries

The goal is general knowledge worth learning, not whoever is in the news this
week, and the default source is built for that.

A Zuordnungsfrage needs ten or more things of one kind, each paired with exactly
one thing of another — countries and their capitals, elements and their symbols.
That single requirement is what separates a good source article from a bad one,
and `sources/strategies.py` attacks it from four directions.
`--source` picks one:

| strategy | draws from | why |
| --- | --- | --- |
| **`mixed`** (default) | round-robin over the four below | no single source is best |
| `subjects` | category members, evenly across the quiz's nine subjects | a Wikipedia category **is** the grouping |
| `lists` | popular list articles | already tabulated into pairings |
| `vetted` | `Wikipedia:Exzellent` / `:Lesenswert` | peer-reviewed, so the facts hold up |
| `evergreen` | popularity across `--months` (24) | read for years, so worth knowing |
| `recent` | the current top list | topical, but half of it is people in the news |

**`subjects` is the only one that controls balance.** It maps each of the nine
database subjects onto German Wikipedia categories that hold articles *directly*
— verified against the live API, not guessed, because German Wikipedia uses many
pure container categories whose members are all subcategories and which come
back empty (`Kategorie:Epoche`, `Kategorie:Speise` and `Kategorie:Säugetier` are
all absent for that reason). Subjects are interleaved, so a six-article run
touches all nine rather than spending itself on geography.

The game deals rounds evenly across subjects, so a pool that is four-fifths
geography makes a poor game however good the individual questions are — and
popularity sampling gives no say in that at all.

**`evergreen`** samples one day per month and ranks by **how many of those
months an article appears in**, views only breaking ties. That ordering is the
trick: a news story spikes enormously in one month and vanishes, while
`Deutschland` and `Periodensystem` appear in all 24.

| `--source recent` | `--source evergreen` |
| --- | --- |
| Jürgen Klopp, Philipp Amthor, Evelyn Burdecki, Nina Warken… | Deutschland, Periodensystem, Vereinigte Staaten, Zweiter Weltkrieg… |

**`lists`** is the intersection of those two ideas. Raw prefix search over every
"Liste der …" page is dominated by the hyper-specific (`Liste der
.NET-Sprachen`); ranking the same articles by staying power leaves `Liste der
Staaten der Erde` and `Liste der Präsidenten der Vereinigten Staaten` on top —
popular *and* pre-tabulated.

Two filters then run **before** any model call, because that is still where
the time goes — roughly 12s per call on a GPU, minutes on CPU:

- **Biographies are skipped** (`--include-people` to keep them). A matching
  question needs ten or more clean pairings of the same kind, and a life story
  has no such structure — asked for one anyway, the model either declines or
  invents pairings to fill the shape. German Wikipedia
  files every biography under `Kategorie:Mann`/`Frau`/`Geboren`, which makes this
  a reliable test that costs no extra request. It also excludes Mozart, which is
  a real cost, not an oversight.
- **Adult topics are dropped.** They sit permanently near the top of the German
  charts; this is a general-audience quiz. The blocklist is deliberately narrow
  and will not catch everything.

On a live run of the top 25 evergreen candidates, 18 survived and 7 were skipped
— all 7 biographies (Trump, Musk, Schumacher, Hitler, Ronaldo, Jackson, Putin).

Past pageview counts never change, so each sampled day is cached under
`out/.cache/`. The first evergreen scan costs 24 API calls with rate-limit
backoff; every run after that is free.

## The pipeline

Built on LangChain: each step is one LCEL chain, and LangGraph decides which
step runs when.

```
tools/ingest/
├── config.py          settings: flag > env > .env > default
├── cli.py             flags, the article loop, the only place that prints
├── domain/            what a question IS, and what makes one valid
│   ├── rules.py         the bounds, defined once
│   ├── models.py        Pydantic shapes + the JSON Schemas Ollama is held to
│   └── validate.py      the structural gate
├── pipeline/          turning an article into a question
│   ├── llm.py           the local model as a LangChain chat model
│   ├── prompts.py       every word sent to it, as prompt templates
│   ├── chains.py        one LCEL chain per step
│   └── graph.py         the LangGraph state machine
├── sources/           where articles come from
│   └── wikipedia.py
└── output/            where a finished question goes
    ├── store.py         Supabase, ordered inserts with rollback
    └── report.py        the Markdown a person reads
```

**Dependencies only point inwards.** `domain` imports nothing else in the
package, which is what keeps the rules cheap to test and impossible to break by
editing a prompt. `pipeline` depends on `domain` and on the `Article` type, and
knows nothing about Supabase or Markdown. `sources` and `output` are the two
edges, and neither knows the other exists.

Within `pipeline`, the split between `chains.py` and `graph.py` is the one worth
preserving: a step takes domain objects in and gives domain objects back — an
`Extraction`, a list of complaints, a `Review` — with prompt rendering, the model
call and parsing as links in that one chain rather than three things a caller has
to remember to do in order. `chains.py` knows how to run a step and nothing about
what comes next; `graph.py` knows what comes next and never touches a prompt or a
schema.

One article goes in; every question that passed both gates comes out, or a list of
reasons it did not.

```
START ─▶ extract ─▶ select ─▶ check ──(clean)──▶ review ──(clean)──▶ END
            │                   │                   │
            │               (problems)          (problems)
            │                   │                   │
            └───────────────────┴──▶ repair ◀───────┘
                                       │      (if attempts left, else END)
                                       └──▶ back to extract
```

| node | what it does | cost |
| --- | --- | --- |
| `extract` | one model call: `--drafts` questions, each with pairings, subject, difficulty | slow |
| `select` | one model call: which drafts are worth playing — may keep several, or none | slow |
| `check` | `validate.py` — is it well-formed? | free |
| `review` | second model call, fresh context — is it *true*? | slow |
| `repair` | re-ask with the previous answer and the complaints attached | — |

**One article can yield more than one question.** `extract` writes several drafts
from the same article and `select` says which are worth a board — before either
gate, because "does answering this teach the player anything?" is worth knowing
before paying to review it. The first kept draft goes on down the graph; the rest
come back in `Outcome.spares`, and `run_all` puts each of those *back into the
same graph* through a conditional `START` edge that lands at `check`. So a spare
is written on the strength of passing the same gates, not of having been chosen.
A spare gets one attempt: the repair edge leads to `extract`, which would
regenerate the whole batch and discard the spare.

`select` keeping nothing is a verdict on the article, like `usable: false` — the
drafts were well-formed and just not interesting, and asking the same model again
gets the same drafts. So it stops rather than repairing.

**Why a graph and not one long chain.** The interesting behaviour here is not
"call the model, parse the answer" — it is *what happens when the answer is
wrong*. Both gates feed the same repair edge, repair loops back into extract,
and the attempt budget decides whether that edge exists at all. LCEL composes
each step beautifully but cannot express a conditional loop *between* steps;
written as a `for` loop it worked, but the control flow was spread across a loop
counter, two `if`s and an early `return`. As edges, the control flow is the
thing you read.

**The repair loop is a `MessagesPlaceholder`.** `EXTRACT` ends with one, and the
graph state carries `repairs` under the `recent_repairs` reducer. Each rejected
attempt appends the model's own answer plus the complaints about it, so attempt
three still sees everything that went wrong in attempts one and two — the repair
node returns only the two new turns and LangGraph does the accumulating. The
rejected answer has to go back in: without it the model is being asked to fix
something it can no longer see, and it starts over and reintroduces the fault.

The reducer is `add_messages` with a window: the last `KEEP_REPAIRS` attempts,
whole ones only. The transcript is the one part of that prompt with no bound of
its own — it sits on top of a system prompt and 6000 characters of article — and
unbounded, `--attempts 10` runs the extract call out of context, where the
truncated reply is reported as a schema mismatch and reads like the model's
fault. Two is what the default `--attempts 3` accumulates anyway.

The graph state is a Pydantic model, so a node returning a key that does not
exist is an error rather than a silent no-op.

Three edges stop early rather than repairing, because nothing a repair prompt
could say would help: the model declining (`usable: false` — a verdict, not a
defect), a transport failure, and running out of attempts.

With `--no-review` the review node is left out of the graph entirely rather than
added and routed around, so the smaller run *is* the smaller graph.

### Debugging it

Each step is recorded as it runs — `run_article` streams the graph rather than
invoking it — and lands in two places: the `Pipeline steps` block in the
Markdown report, and stdout as the run goes (`--quiet` reduces it to one line
per article).

```
[  7/40] Kaffee
        88,932 chars from https://de.wikipedia.org/wiki/Kaffee
        extract    11.2s  16 pairs
        check       0.0s  1 problem(s): 16 pairs, playable range is 10-14
        repair      0.0s  retrying, attempt 2
        extract     9.8s  11 pairs
        check       0.0s  ok
        review      2.1s  ok
        explain     6.9s  11/11 answers explained
        ACCEPTED   30s  kaffee-zuordnung (11 pairs, medium)
```

That is enough to tell a bad article from a bad prompt from a flaky model, which
is the question you actually have when a batch comes back half-empty.

**LangSmith is off, deliberately.** `langsmith` arrives as a langchain-core
dependency and would upload every prompt and every generated question to
LangChain's cloud the moment `LANGSMITH_TRACING` appeared in the environment.
This tool exists to run locally, so `tools/ingest/__init__.py` sets that
variable to `false` at import time, before langchain-core loads. The trace above
is the local replacement.

## What the model is asked for

One call produces the whole question — the pairings, the subject it belongs to,
and a difficulty rating. Those are one judgement, not three.

Two things make a 9B model workable here:

**Constrained decoding.** The JSON Schema goes to Ollama in `format`, which
restricts token sampling to strings that satisfy it. The reply parses by
construction and always has the right keys. Without it a small model returns
prose wrapped around its JSON, or trailing commas, or a plausible object with
invented field names.

It enforces array bounds too, and that cuts both ways — worth knowing before
adding one. `minItems: 10` on `pairs` did not produce ten good pairs from a thin
article, it produced ten pairs: measured on glm4:9b with a four-fact article, the
model padded the board by repeating the same answers (up to eight of twelve
duplicated) and still claimed `usable: true`, because a short reply was
*unrepresentable* and the prompt's way out was therefore closed. Without the
floor, four clean pairs every time.

Nor was the floor holding boards full: on the real leads of `Schach` and `Kaffee`,
three runs each, ten pairs and no duplicates with it and without it. So a bound
whose violation the model needs to be able to express belongs in `validate.py`,
not in the grammar — the ceiling is in both, the floor only in the validator.

**A repair loop.** Schema-valid is not the same as correct. `validate.py` checks
the rules and, when something fails, the complaints are fed back to the model
with its own previous answer for another attempt (`--attempts`, default 3).
This is the difference between the local model being usable and not: against a
hosted frontier model most questions pass first time, but a 9B model needs a
second pass often enough that without the loop the accept rate is poor.

The model can also decline outright: `usable: false` with a reason, for articles
that hold no clean set of pairings. That is a verdict, not a defect, so it stops
immediately rather than burning the remaining attempts arguing with it.

## What makes a good pairing

A question is a **one-to-one pairing**: every category holds exactly one answer,
every answer belongs to exactly one category, and there is nothing else on the
board.

```
Deutschland  ─  Berlin
Frankreich   ─  Paris
Italien      ─  Rom
Spanien      ─  Madrid
```

An earlier version put extra answers on the board that belonged to no category —
`Madrid` with no `Spanien` to put it in. It was removed. The failure was not the
idea but the judging: telling a genuinely plausible decoy from one that secretly
belongs to a listed category is exactly the thing a model gets wrong, and when
it got it wrong the question marked a correct player as wrong. A strict pairing
has no such failure mode, because there is no answer whose correct home is "none
of these".

What it costs is worth knowing: **the last placement of a round is forced.** Once
every answer but one is placed, the last has one home left, and whoever the
rotation lands on takes a point for reading what is left. That is a property of
strict pairing, not a bug in any one question, and it is the game's problem
rather than the ingest's.

## Two gates before writing

### 1. Structure — `validate.py`

Prompt rules are a request; this is the enforcement. Cheap, local, no model
call. A question is rejected unless:

- **10–14 pairs** — categories, answers and pairings are all the same count
- no duplicate answers or category labels (case-insensitive)
- no answer that reuses a category label
- answers of at most 4 words
- a known `subject_slug`, a valid difficulty, a URL-safe slug

**10–14 is a design target, not a safety limit** — the one bound here that is.

The floor is what makes a round worth playing. Turns go round the table one
placement at a time, so at six pairs a lobby of five has barely a turn each
before the board is empty. The ceiling is the phone, where the frontend stacks
categories in a single column, and fourteen answers is already a lot to read at
a glance.

The consequence of the floor matters: an article that cannot support ten
well-sourced pairs is **not** a small question, it is not a question, and the run
moves on — unless `augment` can find the missing pairs in a neighbouring article.
The prompt says this explicitly and tells the model to answer `usable: false`
instead, and the grammar deliberately lets it return a short board so that it can:
with `minItems` in the grammar the model padded instead, which is the failure this
is meant to prevent. Rejecting an article is cheap; a question containing an
invented fact is not.

`rules.py` holds the bounds once, shared by the JSON Schema and the validator so
the two can never drift apart — the ceiling in both, the floor in the validator
alone, for the reason above.

Slug collisions are resolved by the tool, not the model: `-2`, `-3`, and so on.

### 2. Content — `review_step`

Structure says nothing about truth. Whether Chlorophyll really is a *Farbstoff*
needs reading comprehension — so a **second model call** re-reads the article
and judges the finished question.

It runs with **fresh context**: the reviewer sees only the article and the
question, never the generator's reasoning or its earlier attempts. Asking a
model to re-check its own transcript mostly gets you agreement with itself. That
is enforced by the prompt's shape rather than by discipline — `REVIEW` has no
`MessagesPlaceholder`, so there is nowhere for a transcript to be passed.

It judges two things: is every answer under the right category, and is anything
simply untrue. Both are about the pairings, which since the board holds nothing
else is the whole question.

Its findings are phrased as complaints and feed the same repair loop, so a
failed review costs another generation attempt rather than dropping the article.
It only runs once the structure is sound — reviewing a malformed question is an
expensive way to learn nothing. Skip it with `--no-review` (roughly halves the
time per question).

If the reviewer itself fails to run, the question is kept and marked unreviewed
rather than discarded — a broken reviewer must not throw away work that already
passed the structural checks.

### What neither gate judges

Two properties get past both, and it is worth knowing which, because both end up
being caught by a person reading the Markdown report:

**Whether the question is worth playing.** Well-formed, true, unambiguous and
boring passes everything. That is what `select_step` is for, and why it asks about
*knowledge* rather than correctness — but taste is not a gate, so it runs on the
drafts and does not get a second look at the survivors.

Measured on glm4:9b it is not there yet: one run kept both drafts of
`Periodensystem`, one of which was two pairs long with the same answer under both
categories; the next kept *none* of `Kaffee`, under a verdict saying in the same
sentence that some of them asked real questions. So it runs on
`INGEST_JUDGE_MODEL` alongside `vet`, and **an empty selection only condemns the
article when that names a model other than the run's own** — a judge somebody
chose gets to say no, an unproven one only gets to sort, because the cost of the
second reading is a good article deleted on a coin toss. The run says which it is.
`--drafts 1` skips the step and restores one question per article exactly.

**Whether a borrowed pair belongs to this board.** `review` judges pairs one at a
time; drift is a property of the *set*. `Donau -> Schwarzwald` on a board of river
lengths is correctly paired, unambiguous and true, so every check the reviewer
runs passes it. Homogeneity was tried in that prompt and glm4:9b could not do it.
That judgement belongs to `vet`, which is **off by default** because it measures
at about chance on the same model — so with `INGEST_VET` unset, the run says so
out loud and the report names every question that borrowed and from where.

**And the instruction on a picture question.** `reframe` rewrites the title and
the one-sentence instruction after both gates, so nothing checks it — it is prose
a player reads, not data a validator sees. What the schema can do is make the
model state which side is the photograph *before* it writes the sentence that
depends on that (`shown`, `asked`, then `title`, `description`, in decoding
order); a reply that skipped it keeps the old title instead of renaming. The
direction it wrote for goes in the trace, and the report has a checkbox for it.

## Design notes

**Complaints are written for the model, not for a log.** Everything
`validate.py` returns is fed straight back as the repair instruction, so a
complaint that does not name its offender cannot be acted on. Told only
`duplicate items`, glm4 returned the identical answer three times and the
article was dropped; told `these answers appear more than once: ['Wasser']`, it
fixed it on the next attempt. Each complaint also has to state the way out when
the obvious fix breaks another rule — deleting the last item of a category means
deleting the category too, and the model will not infer that.

**Source URLs come back from the API, never constructed.** Titles get
normalised, redirected and percent-encoded in ways that are easy to get subtly
wrong, and a source link that 404s is worse than no link. Every URL in
`seed.sql` was read back from the API the same way.

**Local models are looser, and the design leans on that.** A 9B model needs a
retry more often than a hosted one, so the client timeout is generous (10 min,
sized for the CPU fallback) and the validator is treated as load-bearing rather
than as a safety net. If accept rates are poor, raise `--attempts` before
reaching for a bigger model.

**Wikipedia rate limits are real.** Fetching a few dozen articles back to back
reliably returns 429s, and the response carries no `Retry-After`, so
`WikipediaClient` paces requests and backs off on its own. Without it, a batch
silently loses most of its articles.

**Writes are ordered and rolled back.** PostgREST gives no transaction across
quizzes → categories → items, so a failure part-way deletes the quiz row (which
cascades). Otherwise a question could end up with no answers and still be dealt
into a round.

**Re-running is safe.** Articles whose URL is already a `source_url` are
skipped, so a second run adds new questions rather than duplicates.

## Tests

```bash
python -m pytest tools/ingest/tests -q
```

177 tests: settings resolution, source strategies, the validation rules, slugification (German umlauts spelled out:
`Flüsse` → `fluesse`, not `flusse`), the article/junk-title filter, the prompt
templates, the graph's control flow, the reviewer's verdict handling, and the
Markdown report.

Only the *model* is faked, never the chain — the graph tests swap in a
`FakeChatModel` and let the real `ChatPromptTemplate`, the real parser and the
real validator run. A test that stubbed the whole step would pass with a broken
prompt template. The whole suite stays pure: no network, no database, no Ollama.
