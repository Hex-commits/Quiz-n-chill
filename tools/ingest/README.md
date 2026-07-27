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
  Supabase   http://127.0.0.1:54321
  Source     mixed, 24 months
  Pipeline   extract -> check -> review -> explain   (3 attempts per article)
  Mode       dry run -- nothing is written
========================================================================
40 candidates; aiming for 10 questions.

[  1/40] Periodensystem
        127,578 chars from https://de.wikipedia.org/wiki/Periodensystem
        extract    10.5s  5 categories, 10 real + 3 fakes
        check       0.0s  ok
        review      1.8s  ok
        explain     7.1s  13/13 answers explained
        ACCEPTED  19s  periodensystem-zuordnung (5 cat / 13 items, medium)
        -> 1/10 accepted  |  0 dropped  |  0 skipped  |  ~3m01s left  |  20s elapsed
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
| `ingest-<stamp>.md` | **Reading.** Each question laid out with its categories, answers, source link and a checklist of its fakes. Rejected articles are tabled with the reason. |
| `ingest-<stamp>.json` | The machine record — the exact payload, for re-processing or diffing. |

The Markdown is built for the one question nothing automatic can answer: **is
each fake really a fake?** A model will happily list a genuine member of a
category among the fakes, and that produces a question which marks a correct
player wrong. `validate.py` cannot see it; a person with the source open can, in
about ten seconds per question.

## Which articles it tries

The goal is general knowledge worth learning, not whoever is in the news this
week, and the default source is built for that.

A Zuordnungsfrage needs several categories, each holding two or more members of
the same kind. That single requirement is what separates a good source article
from a bad one, and `sources/strategies.py` attacks it from four directions.
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
  question needs several categories each holding two or more members of the same
  kind, and a life story has no such structure — asked for one anyway, the model
  either declines or invents categories to fill the shape. German Wikipedia
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

One article goes in; a question that passed both gates comes out, or a list of
reasons it did not.

```
START ─▶ extract ─▶ check ──(clean)──▶ review ──(clean)──▶ END
            │         │                   │
            │     (problems)          (problems)
            │         │                   │
            └─────────┴──▶ repair ◀───────┘
                             │        (if attempts left, else END)
                             └──▶ back to extract
```

| node | what it does | cost |
| --- | --- | --- |
| `extract` | one model call: categories, items, fakes, subject, difficulty | slow |
| `check` | `validate.py` — is it well-formed? | free |
| `review` | second model call, fresh context — is it *true*? | slow |
| `repair` | re-ask with the previous answer and the complaints attached | — |

**Why a graph and not one long chain.** The interesting behaviour here is not
"call the model, parse the answer" — it is *what happens when the answer is
wrong*. Both gates feed the same repair edge, repair loops back into extract,
and the attempt budget decides whether that edge exists at all. LCEL composes
each step beautifully but cannot express a conditional loop *between* steps;
written as a `for` loop it worked, but the control flow was spread across a loop
counter, two `if`s and an early `return`. As edges, the control flow is the
thing you read.

**The repair loop is a `MessagesPlaceholder`.** `EXTRACT` ends with one, and the
graph state carries `repairs` under an `add_messages` reducer. Each rejected
attempt appends the model's own answer plus the complaints about it, so attempt
three still sees everything that went wrong in attempts one and two — the repair
node returns only the two new turns and LangGraph does the accumulating. The
rejected answer has to go back in: without it the model is being asked to fix
something it can no longer see, and it starts over and reintroduces the fault.

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
        extract    11.2s  3 categories, 8 real + 3 fakes
        check       0.0s  1 problem(s): 16 items, playable range is 8-14
        repair      0.0s  retrying, attempt 2
        extract     9.8s  3 categories, 6 real + 2 fakes
        check       0.0s  ok
        review      2.1s  ok
        explain     6.9s  8/8 answers explained
        ACCEPTED   30s  kaffee-zuordnung (3 cat / 8 items, medium)
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

One call produces the whole question — categories, items, fakes, the subject it
belongs to, and a difficulty rating. Those are one judgement, not four.

Two things make a 9B model workable here:

**Constrained decoding.** The JSON Schema goes to Ollama in `format`, which
restricts token sampling to strings that satisfy it. The reply parses by
construction and always has the right keys. Without it a small model returns
prose wrapped around its JSON, or trailing commas, or a plausible object with
invented field names.

**A repair loop.** Schema-valid is not the same as correct. `validate.py` checks
the rules and, when something fails, the complaints are fed back to the model
with its own previous answer for another attempt (`--attempts`, default 3).
This is the difference between the local model being usable and not: against a
hosted frontier model most questions pass first time, but a 9B model needs a
second pass often enough that without the loop the accept rate is poor.

The model can also decline outright: `usable: false` with a reason, for articles
that hold no clean set of pairings. That is a verdict, not a defect, so it stops
immediately rather than burning the remaining attempts arguing with it.

## What makes a good extra answer

The items with no category are the whole mechanic, and what they should be is
easy to get wrong.

An extra answer is **not nonsense and not invented**. It is a genuinely correct
answer of exactly the same kind as the real ones — from the same subject, the
same shape, the same length — for a category that simply is not on the board:

```
Categories:      Deutschland   Frankreich   Italien
Real answers:    Berlin        Paris        Rom

Good extra:  Madrid      ← a real capital, looks identical to the others,
                           but there is no "Spanien" category to put it in
Bad extra:   Erdbeere    ← nobody hesitates for a second; the slot is wasted
```

The rule the model is given: *"which answer would be correct if there were one
more category — the one that isn't here? Use that."*

Two ways it goes wrong, and they are different problems:

| | what happens | severity | effect |
| --- | --- | --- | --- |
| **`bad_fake`** | secretly belongs to a listed category | breaks the game — marks a correct player wrong | **blocks** — sent round the repair loop |
| **`weak_fake`** | obvious nonsense nobody would pick | wastes a slot, makes the question easier | reported only, for you to judge |

**A weak fake does not reject the question, on purpose.** It is a quality nit,
not a correctness defect, and glm4 judges it badly: on Photosynthese it called
`Oxidation`, then `Phototrophie`, then `Elektronendonatoren` obvious nonsense —
all ordinary terms from the article's own subject. Each rejection made the
generator swap in another perfectly good extra, which the reviewer then rejected
too. Blocking on that costs a sound question every time and never converges, so
it is named in the Markdown report and left to you.

## Two gates before writing

### 1. Structure — `validate.py`

Prompt rules are a request; this is the enforcement. Cheap, local, no model
call. A question is rejected unless:

- 2–10 categories, each with at least one item
- **8–14 answers in total**, at least 2 of them real, 1–6 extras
- no duplicate items or category labels (case-insensitive)
- **no extra answer that is also listed as a real one** (plain string match —
  the semantic version of this check is the reviewer's job)
- no item that reuses a category label
- items of at most 4 words
- a known `subject_slug`, a valid difficulty, a URL-safe slug

**8–14 answers is a design target, not a safety limit** — the one bound here
that is. Fewer than eight and the round is over before the turn has gone round a
lobby of five; more than fourteen and it stops fitting on a phone.

The consequence matters: an article that cannot support eight well-sourced
answers is **not** a small question, it is not a question, and the run moves on.
The prompt says this explicitly and tells the model to answer `usable: false`
instead — because the alternative, a model padding the board to reach the
number, is exactly the failure this is meant to prevent. Rejecting an article is
cheap; a question containing an invented fact is not.

**The two ceilings interact.** Every category needs at least one real answer, so
10 categories means at least 10 real answers — and with 14 the maximum, a full
board leaves room for only 4 fakes. A JSON Schema cannot express "the sum across
these two arrays", so the grammar can emit a 10-category question with 6 fakes
that the validator then rejects. That is what the repair loop is for, and the
prompt warns about it directly.

The category ceiling is 10 rather than something smaller because **one-to-one
question types can only grow sideways.** A country has exactly one capital and
an invention one inventor, so those questions cannot be deepened by adding
answers to a category — at a ceiling of 6 they topped out around 9 answers and
could never reach the top of the range. The cost is real: the frontend stacks
categories in a single column on a phone, and 10 categories also means 11 choices
on every decision, counting "this one is a fake".

`rules.py` holds the bounds once, shared by the JSON Schema and the validator so
the two can never drift apart.

Slug collisions are resolved by the tool, not the model: `-2`, `-3`, and so on.

### 2. Content — `review_step`

Structure says nothing about truth. Whether Chlorophyll really is a *Farbstoff*,
or whether a listed fake is secretly a real member of one of the categories,
needs reading comprehension — so a **second model call** re-reads the article
and judges the finished question.

It runs with **fresh context**: the reviewer sees only the article and the
question, never the generator's reasoning or its earlier attempts. Asking a
model to re-check its own transcript mostly gets you agreement with itself. That
is enforced by the prompt's shape rather than by discipline — `REVIEW` has no
`MessagesPlaceholder`, so there is nowhere for a transcript to be passed.

It judges four things: are the real answers under the right categories; does an
extra answer secretly belong to one of them (`bad_fakes`); is an extra answer
obvious nonsense rather than a near-miss (`weak_fakes`); and is anything simply
untrue.

Its findings are phrased as complaints and feed the same repair loop, so a
failed review costs another generation attempt rather than dropping the article.
It only runs once the structure is sound — reviewing a malformed question is an
expensive way to learn nothing. Skip it with `--no-review` (roughly halves the
time per question).

If the reviewer itself fails to run, the question is kept and marked unreviewed
rather than discarded — a broken reviewer must not throw away work that already
passed the structural checks.

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
