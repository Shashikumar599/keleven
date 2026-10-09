# Decision log

Short, dated record of every project decision: what was decided and why. Newest last.

## Phase 0: Data

**2026-10-02: Use the Hugging Face dataset (`jxm/the_office_lines`) as the base.**
Kaggle and HF are the same transcript. HF keeps stage directions and deleted scenes, which can't be recovered
from Kaggle; HF's gaps (encoding, titles) can be filled from Kaggle. Details in `phase-0.md`.

**2026-10-02: Keep the raw data as downloaded Parquet; don't convert to CSV.**
Parquet keeps column types and UTF-8 encoding. CSV is only used for human-readable previews.

**2026-10-02: Repair mojibake (`���`) from Kaggle's version of the same line.**
The original bytes are lost, so a second source is the only reliable fix. Lines with no Kaggle match get a
context-based guess and are flagged `mojibake_guessed`.

**2026-10-02: No multi-speaker column.** Labels like `Michael and Dwight` stay as one speaker value.

**2026-10-02: Leave repeated identical lines unchanged** (363 rows). No flag, no removal.

**2026-10-02: Speaker fixes go through a hand-reviewed map (`ingest/speaker_map.csv`), not fuzzy matching.**
Only `status=ok` rows are applied, so ambiguous names (Molly/Holly, David/David Wallace) need a human decision.

**2026-10-02: Every cleaned line keeps `text_raw` and `fix_flags`.** Any answer can be traced back to what
cleaning changed.

**2026-10-03: Data model for a line: one speaker, one dialogue, 0..n stage directions in place.**
Directions sit inside the dialogue and often describe other people or events (`[phone rings]`), so their
position matters.

**2026-10-03: Store `text` (dialogue with directions in place) as the single source of truth.**
`dialogue` and `directions` are derived from it, never stored as independent copies, because splitting loses
where each direction happened. In Postgres, `dialogue` is a generated column.

**2026-10-03: Keep the 402 direction-only lines** (e.g. `Michael: [laughs]`). They are part of the scene.

**2026-10-03: Preview CSV drops the `dialogue` column** to make it easier to scan.

## Phase 1: Postgres schema (under discussion, see `docs/schema.md`)

**2026-10-03: Don't store deleted scenes in Postgres.** Drops 312 scenes / 1,936 lines (Seasons 1–2 and one
Season 3 episode only, so coverage was uneven anyway). The `deleted` column goes away. The processed Parquet
keeps them; the filter is applied at load.

**2026-10-03: No `scenes` table; `lines` carries `season, episode, scene` directly.** A scene has no attributes
of its own (no location or summary in the data, `deleted` is gone), so a table would only add a join and a
`scene_id`. It can be built later from `lines` if scene-level attributes are needed.

**2026-10-03: No denormalization.** Episode title is stored once in `episodes`; the `lines_full` view joins it
in. Speed comes from indexes, not duplicated columns.

**2026-10-03: Indexing is deferred** to a separate discussion.

**2026-10-03: Postgres holds clean data only.** `speaker_raw`, `text_raw`, `fix_flags` and `title_inferred` are
cleaning history; they stay in `data/processed/*.parquet`. Tracing a line back goes through its `id`.

**2026-10-03: Speaker stays plain text on `lines`.** No speakers table yet; revisit in Phase 3 (graph) if
characters get attributes or relationships.

**2026-10-03: `directions` is derived in the `lines_full` view**, not stored. A separate per-direction table is
the option to revisit if action questions turn out to matter.

**2026-10-03: The evaluation set will include whole-dataset questions** (e.g. "What are the major storylines of
Season 5?"), not only single facts. These are the questions that could justify Phase 3.

**2026-10-03: If Phase 3 is built, the graph is event-centred** (characters, episodes/scenes, events,
storylines, organizations) with a fixed list of types, cited and timed edges, and hierarchical summaries as the
baseline to beat. Draft in `docs/graph-design.md`.

**2026-10-03: The system will eventually be hosted for public use; start simple but keep the path open.**
- Local Postgres runs in Docker (`pgvector/pgvector`, pinned major version), not the Homebrew Postgres.
- Only standard extensions that managed hosts support (pgvector, later possibly pg_trgm).
- Code reads one `DATABASE_URL`; moving to a hosted database is a config change.
- Schema lives in numbered SQL files, applied the same way locally and hosted.
- Two database roles: admin for loading, read-only for the app.
- Public app never exposes the database and shows short cited excerpts, not full transcripts (copyright).

**2026-10-03: Local Postgres runs from `docker-compose.db.yml` (pgvector/pgvector:0.8.7-pg17, port 5433, named
volume `pgdata`); credentials in `.env`.** pgvector pinned so benchmark numbers stay comparable across phases.

**2026-10-03: Database and app are deployed separately.** The DB compose file holds only the database; the app
gets its own compose file/deployment and connects through `DATABASE_URL`. Mirrors hosting, where the DB is
managed infrastructure and the app is deployed against it.

**2026-10-03: Local DB container pinned to `platform: linux/arm64`.** `~/.zshrc` sets
`DOCKER_DEFAULT_PLATFORM=linux/amd64`, which ran Postgres under x86 emulation on Apple Silicon and would have
inflated latency measurements. The pin only affects this compose file.

**2026-10-03: Migrations live in `db/migrations/NNN_name.sql`, applied in order with psql.** `001_extensions.sql`
enables pgvector (0.8.7). Statements are written to be safe to re-run (`IF NOT EXISTS`).

**2026-10-03: App role `office_app` (migration `002_app_role.sql`): read-only by permissions, plus session
safeguards.** Grants: CONNECT, USAGE on `public`, SELECT on all tables/views, default SELECT on future tables.
Safeguards: `default_transaction_read_only = on`, `statement_timeout = 5s`. Password comes from `.env`
(`APP_DB_PASSWORD`), never from the migration file.
Tested: reads work (including tables created later); writes and CREATE are refused by permissions even with
read-only switched off. **The role can raise its own `statement_timeout` with `SET`**, so the session settings
are safeguards, not limits. Phase 2 must not run LLM-written SQL as-is: allow a single SELECT only and set the
timeout from the app (`SET LOCAL`) inside each transaction.

**2026-10-03: Local DB port bound to `127.0.0.1` only; passwords replaced.** `0.0.0.0:5433` exposed the database
(with a guessable superuser password) to anyone on the same network. Now localhost only, and the user set new
passwords in `.env`. Rebuilt from scratch: migrations 001–002 recreate everything from an empty volume.
Passwords contain URL-special characters, so any `DATABASE_URL` must percent-encode them (or pass connection
parameters separately).

**2026-10-03: Migration `003_transcript_schema.sql` applied: `episodes`, `lines` (generated `dialogue`),
`lines_full` view.** Migrations are forward-only and safe to re-run (`IF NOT EXISTS`, `CREATE OR REPLACE VIEW`),
with no `DROP` statements. Tables are still empty; loading is the next step.

**2026-10-03: Data loaded with `ingest/load.py`: 186 episodes, 57,973 aired lines, 8,849 scenes (396
direction-only lines).** Full refresh in one transaction (TRUNCATE + COPY, rolled back on count mismatch); rows
streamed with `itertuples`. Postgres's generated `dialogue` matches the cleaning step's dialogue on every line
(0 mismatches). Load takes ~3 s.

## Phase 1, Part 2: Chunking

**2026-10-03: Baseline chunking = pack consecutive whole scenes, with three limits.** Start a new chunk when the
next scene would exceed **250 tokens** or **3 scenes**; merge chunks under **80 tokens** into a neighbour; never
cross an episode; split a single scene over the embedding model's limit by lines with overlap.
Why: scenes are short (median 51 words, 35% single-line talking heads) and talking heads need their setup
(S3E20: Jim's "eleven dollars" only mentions Dwight in the neighbouring scene). The token cap limits size and cost;
the scene cap limits the number of topics per vector (dilution); the minimum avoids chunks too small to embed.
On S3E20 the mixed rule kept Creed's blame and excuse together and removed a 5-scene chunk that tokens-only made.

**2026-10-03: Neighbour expansion (±1 chunk, same episode) at retrieval time.** Repairs stories cut at a chunk
boundary when answering. Limitation: only helps once one half has matched. Overlap or topic-aware boundaries
are the fallback if evaluation shows split stories failing to match.

All values (250 / 3 / 80, ±1) are starting points to tune on the dev split once the question set exists.
Alternatives kept for comparison: single scene + expansion; contextual headers (LLM context sentence per chunk);
plot-thread grouping and multi-level indexes for storyline questions.

**2026-10-03: Chunk storage (migration `004_chunks.sql`, drafted).**
- `chunk_sets` keeps several chunking strategies side by side, each with its settings in `params`.
- A chunk points to its source by **line range** (`first_line_id..last_line_id`), exact even for split scenes.
  Verified that line ids follow script order and episodes don't interleave.
- `content` is stored as a snapshot of exactly what was embedded:
  `S3E20 Product Recall | scenes 6-8`, blank line, then `Speaker: text` lines (directions included).
- Speakers and scene range are derived in the `chunks_full` view, not stored.
- Embeddings go in a separate table in Part 3 (several models to compare).

**2026-10-03: Clarification: 250 tokens is a packing target, not a split point.** A single scene larger than 250
tokens stays whole as its own chunk (581 scenes, 6.6%). A scene is split by lines only if it exceeds the
embedding model's input limit (est. 38 scenes over 512 tokens, 2 over 1,024, largest ~1,321). A chunk under the
80-token minimum still merges into a neighbour even if that exceeds 250, so talking heads stay attached to long
scenes. Part 3 criterion: prefer an embedding model accepting at least ~1,500 tokens, so no scene is ever split.

**2026-10-03: Migration 004 applied** (`chunk_sets`, `chunks`, `chunks_full`). Tested in a rolled-back
transaction: the view derives title, scene range (6-8), speakers and line count from the line range; duplicate
positions and backwards ranges are rejected. `office_app` has read access through default privileges.

**2026-10-03: Chunk once with a general tokenizer (`tiktoken`), before choosing the embedding model.**
Largest chunk ≈ 1,400 tokens; even ±20% tokenizer difference stays far below current models' 8k+ limits, so one
chunk set stays valid for every model compared in Part 3 (same chunks → fair model comparison). Tokenizer is
recorded in `chunk_sets.params`. **No scene splitting is implemented**; the chunker stops with an error if a chunk
exceeds the hard limit. Part 3 only considers embedding models accepting ≥ 2,048 tokens, and re-checks every
chunk with the model's own tokenizer before embedding.

**2026-10-03: Token budget counts the full `content`** (header + `Speaker: text` lines), measured with tiktoken on
the exact stored string, because that is what gets embedded. Content format: header
`S{season}E{episode} {title} | scene(s) {first}-{last}`, blank line, lines in script order joined by newlines,
stage directions included. All formats and limits are recorded in `chunk_sets.params`. A chunk set is written in
one transaction (chunk_sets row + COPY of chunks).

**2026-10-03: Correction: aired scene numbers have gaps.** In 24 episodes, deleted scenes are numbered between aired
scenes (e.g. S1E2: aired 29, 33, 35; deleted 30-32, 34), so the aired-only data has 73 gaps (up to 9 wide).
Phase 0 claimed deleted scenes always come after aired ones; corrected in phase-0.md. Consequences: scenes are
never renumbered (citations keep source numbers); any "next scene" lookup must use the next existing scene, not
`scene + 1`; chunk neighbours use `position`, which is unaffected.

**2026-10-03: Known limitation of the chunking algorithm (`ingest/chunk.py`), kept as is for the baseline.**
The 3-scene cap applies only while packing. Merging (chunks under 80 tokens) joins **whole neighbouring chunks**,
with **no scene limit**, and repeats while a chunk is still under 80. With very short scenes the two limits
conflict and the minimum wins: e.g. S5E19 Two Weeks scenes 15-21 (a montage of 26-47-token shots) packed into
[15-17] 74t, [18-20] 169t, [21] 35t, then merged into one 7-scene, 254-token chunk. Whole-chunk merging can also
overshoot (74 → 243 in one step). Dry run at 300 tokens: 97 chunks above 3 scenes, max 7.
Accepted for now because such chunks are mostly montages of tiny shots (one idea, few tokens). Alternatives if
evaluation shows a problem: cap scenes during merging (4 → 15 chunks left under 80; strict 3 → 36), or borrow
scenes one at a time from the neighbour until 80 is reached.

**2026-10-03: Finding: two causes of scene-number gaps; one episode is badly incomplete.**
- Deleted scenes numbered between aired scenes (S1: 3 episodes, S2: 13, S3E12). Aired content is complete; only
  numbers are missing.
- Numbers absent from the dataset itself (S4E9 23-26; S5E18, S5E21, S6E14, S6E16 one each; S5E22 3, 4, 44):
  numbering slips or a few lost lines, unverifiable without another source.
- **S7E16 Threat Level Midnight is mostly missing**: 72 lines / 26 scenes (starts at scene 2, 34 numbers missing)
  vs a median episode of 305 lines; Kaggle has 150 lines. Questions about this episode cannot be answered from
  the data; useful for testing whether the system says "I don't know".
Decisions on scene numbering and on backfilling S7E16: pending.

**2026-10-03: Deleted scenes are dropped in `clean.py` (not at load), and scenes are renumbered 1..N per episode.**
Processed data is now aired-only (57,973 lines); the raw files still have the deleted scenes. `renumber_scenes()`
dense-ranks scene numbers within each episode, keeping order; the original number is kept in `scene_raw` in
`lines.parquet` (1,183 lines renumbered, flag `scene_renumbered`). Scene numbers are an artifact of the fan
transcript, so internal consistency matters more than matching HF numbering; lines trace back by `id`.
Example S1E2: raw 29, 33, 35, 41 → 29, 30, 31, 32. S7E16 Threat Level Midnight now starts at scene 1 (still
incomplete: 26 scenes). `load.py` refuses to load if any episode has gaps or doesn't start at 1.

**2026-10-03: Reloading lines clears all chunk sets.** Chunks are built from lines and go stale when lines are
reloaded, so `load.py` truncates `chunks, chunk_sets, lines, episodes` (listed explicitly, not CASCADE) and prints
how many chunk sets it removed. Re-run `ingest/chunk.py` after every load.

**2026-10-03: S7E16 Threat Level Midnight is documented as a known gap, not backfilled from Kaggle.** Questions about
it are expected to fail retrieval; the eval set can use it to test whether the system says "I don't know".

**2026-10-03: Primary chunk set = `pack_300t_3s_80min`** (300-token target). Compared with 250: fewer single-scene
chunks (40% vs 49%), more 3-scene groups, median 240 vs 212 tokens, p90/p99 nearly unchanged. Only this set is
stored; 250 can be created later for comparison.

**2026-10-03: Chunk set `pack_300t_3s_80min` stored (chunk_set_id 2): 4,540 chunks, 1.13M tokens.** Verified:
every line in exactly one chunk (0 uncovered, 0 overlaps), all 186 episodes. On S3E20 the chunks match the
earlier analysis: scenes 1-3 (Jim's Dwight costume with its talking head), 4-5 (complaint calls + watermark),
6-7 (Creed blamed + his excuse together).

**2026-10-03: Chunk content marks scene boundaries with a `Scene N` line; scenes separated by a blank line.**
Without markers a chunk reads as one continuous scene: in S1E1 scenes 11-13 Michael promises the downsizing news
"will not leave this office", then the cut to Phyllis asking about downsizing is the joke; unmarked, Phyllis
appears to ask in the meeting. Chosen over a scene number on every line (~3% vs ~12% extra tokens, less noise in
the embedding). Chunk set rebuilt with `chunk.py --replace` (now chunk_set_id 3): 4,658 chunks, 1.17M tokens,
median 241, max 1,601; every line in exactly one chunk. `--replace` deletes and rebuilds in one transaction.

**2026-10-03: Hosting scope is a demo for friends, not a production service.** Free API tiers are acceptable for
embeddings (and query-time embedding), within their rate limits and terms. Generation will need an Anthropic API
key (the user currently has a Claude subscription only; to be sorted out before Part 5).

## Phase 1, Part 3: Embeddings

**2026-10-03: Embedding provider = Voyage AI via MongoDB Atlas key** (endpoint `https://ai.mongodb.com/v1/embeddings`,
key in `.env`). Test call OK with voyage-4-large: 1024-dimension vectors, already normalized (length 1.0), 46 tokens
used. Query "Who imitates Dwight and talks about bears?" scored 0.446 against Jim's "Bears. Beets..." line and
0.156 against Michael's watermark line. Free-trial limits without a payment method: 3 requests/min, 10K tokens/min.

**2026-10-03: Payment method added to the Voyage (Atlas) account** → Tier 1 rate limits (voyage-4-large: 2,000
requests/min, 3M tokens/min). Usage stays within the 200M free tokens, so no charge is expected.

**2026-10-03: Migration 005 applied: `embedding_models`, `chunk_embeddings`, `stale_embeddings`.**
An experiment is (chunk set × model): `chunk_embeddings` carries `chunk_set_id` with a two-column foreign key to
`chunks (chunk_set_id, chunk_id)`, primary key `(model_id, chunk_set_id, chunk_id)` so one experiment's vectors
are read from the index without a join (model first, as searches filter by model), plus an index on
`(chunk_set_id, chunk_id)` for cascade deletes. Untyped `vector` column so models of different sizes share the
table. `content_sha256` + `stale_embeddings` detect vectors describing old text. No HNSW index yet (exact search
is milliseconds at this size); later one partial index per experiment. Tested in a rolled-back transaction:
stale detection, experiment-scoped search, wrong-set and duplicate rows rejected.

**2026-10-03: Chunk set `pack_300t_3s_80min` embedded with `voyage-4-large@1024`** (`ingest/embed.py`): 4,658/4,658
chunks, 1,182,510 tokens by Voyage's count (5,024 in the 20-chunk trial + 1,177,486), ~2 min, 0 stale. Voyage's
token count is within ~1% of tiktoken on this data, so the chunk budgets hold for this model. A rerun finds
nothing to embed and makes no API calls (resumable, incremental).

**2026-10-03: v1 = the pipeline working end to end with vector search only; hybrid search moves to v2.** The
keyword index, BM25 comparison and rank merging are postponed. Vector search needs no index at this size (exact
scan). Vector indexes and search at scale are a learning topic for the end. Postponed items are tracked in
`docs/open-questions.md`.

**2026-10-03: Roadmap and system shape.** Order: Part 4 retrieval module + CLI → exploration questions → Part 5
generation → v2 hybrid search → Phase 1b question set + baselines → web demo. One core function
`answer(question, system, settings)` serves three systems (Claude without tools, Claude + web search, RAG) and
three front ends (CLI for exploration, eval harness writing `eval/runs/*.jsonl`, web app for the demo, deployed
separately and connecting as `office_app`). Every answer is logged with model, prompt version, retrieved chunk ids
and distances, citations, tokens, cost and latency. All three systems use the same Claude model. Generation and
evaluation need an Anthropic API key (the chat can't be used: not reproducible, can't run at scale).

**2026-10-03: LLM = Gemini Flash (free tier) instead of Claude, for generation, baselines and the demo.** One pinned
model version for all three systems (memory, memory + Google Search grounding, RAG), recorded with every run;
generation behind a provider-swappable interface so Claude or larger models can be compared later.
Why it suits the research: a smaller model remembers less of the show, which is closer to a company's private
data (where memory is zero). Caveats to state in findings: Flash still knows famous moments (report results by
popularity tier; the obscure tier is the best stand-in for private data); web search can find the actual
transcripts online, so the web baseline is unrealistically strong compared with a company setting, where it would
score near zero. Free tier: ~10-15 requests/min, 500-1,500/day (eval harness must throttle and resume); prompts
may be used by Google. Open question for later: does RAG matter less with a bigger model?

## Phase 1, Part 4: Retrieval (v1, vector only)

**2026-10-04: Shared code lives in `common/`** (`db.py`: connections for the `admin` and read-only `app` roles;
`voyage.py`: the Voyage call). The project is installed in editable mode (`pyproject.toml`, `uv pip install -e .`)
so ingest, retrieval and later generation import the same code. Ingest scripts were switched over; their commands
and behaviour are unchanged (dry runs give identical results).

**2026-10-04: Retrieval module `retrieval/vector.py` + CLI `ask.py`.** `retrieve(question, k=8, expand=1,
chunk_set, model, seasons=None)`: embeds the question in query mode with the experiment's own model and size,
exact cosine search over one experiment (no index), then neighbour expansion (±1 position, same episode) with
overlapping/adjacent chunks merged into passages ordered by their best hit. Connects as `office_app`
(read-only). Optional manual season filter (exploration showed questions naming a season). Returns hits,
passages, query tokens and timings. Typical timing: embed ~0.6 s (API), search ~20 ms, expansion ~4 ms.
Smoke test (Andy/Angela): same hits as the manual run; expansion added context around *The Duel* (Angela: "I will
respect the results of the duel") but not the breakup itself, which is further away in the episode.

**2026-10-04: v1 retrieval stays simple: cosine similarity only** (top-k by cosine distance + ±1 neighbour
expansion). No filters by default (the manual `--season` option stays off unless passed), no keyword search, no
re-ranking, no automatic metadata filters; those are v2 / Phase 2.

**2026-10-04: The manual season filter is removed from v1** (`retrieve()` and `ask.py`). Retrieval is pure cosine
top-k + neighbour expansion. Automatic metadata filtering stays a Phase 2 router question.

**2026-10-04: Context size measured; keep k=8, ±1 for v1, tune in Phase 1b.** Tokens of retrieved passages (tiktoken,
chunk content incl. headers), mean over 8 exploration questions:
k=5: 1.4k (±0) / 3.5k (±1) / 5.1k (±2); **k=8: 2.3k / 5.2k / 7.7k**; k=10: 2.8k / 6.3k / 9.2k.
±1 multiplies context by ~2.3, not 3, because neighbouring hits merge (k=8 ±1: 20 chunks in 5.6 passages).
Far below Gemini Flash's context window and free-tier token limits; the cost of larger contexts is noise and
latency, not limits. k and expand are tuned together on the dev split once the question set exists (recall@k and
answer accuracy), not by eye.

**2026-10-04: Prompt context design (Part 5): passages ordered best-first, each with a citation label, no numeric
relevance scores.** Order matters because models use the start of a long context best ("lost in the middle").
Raw cosine distances are uncalibrated (0.47 is not "47% relevant", ranges differ by model and question), so the
LLM judges relevance by reading; scores go to the logs only. Marking matched chunks vs added neighbour context is
an option to test. Context budget: ~10k tokens is a comfortable ceiling (Flash context ~1M; free tier limits bind
on requests/min, not tokens); current k=8 ±1 averages ~5.2k. Larger contexts cost noise and latency, so the size
is tuned on the dev split.

## Phase 1, Part 5: Generation

**2026-10-04: LLM access through the official SDK (`google-genai` for Gemini), behind a provider-agnostic layer**
(`generation/llm.py`) so other models (e.g. Claude) can be added as providers without changing callers. Each
request is stateless: the model sees only that request (no conversation history is ever sent), so answers can't
be biased by earlier questions; training knowledge can't be switched off and is what the memory baseline measures.
Passages are ordered by their best hit's rank and sent with per-passage headers (`[P1] S2E1 The Dundies, scenes
27-51`) and `Scene N` blocks; per-chunk headers dropped. Logging design is deferred until a working
question → answer loop exists.

**2026-10-04: Three outputs per question: RAG (strict), LLM (memory only), LLM + RAG (both, labelled).**
Same model, temperature and output structure; only the information differs. Comparing them isolates what the
transcripts add (LLM vs RAG), what memory adds (RAG vs LLM + RAG), and where they conflict. LLM + RAG must label
every claim's source: scene citation for passage claims, `[memory]` for remembered ones (listed separately).
The fourth system from the research plan (LLM + web search) stays in Phase 1b.
Prompts v1 in `generation/prompts/` (`rag_v1.md`, `memory_v1.md`, `hybrid_v1.md`), built on exploration lessons:
strict grounding with **evidence first** (short exact quotes with season/episode/scene) and the answer written only
from that evidence, explicit "not in the passages" (`answerable`), clear positions on opinion questions, no
repeating of loaded labels, handling of ambiguity and of similar passages from different seasons, short quotes.

**2026-10-04: Generation implemented: `generation/llm.py` (provider layer, Gemini via `google-genai` 2.28),
`generation/answer.py` (rag / llm / hybrid with pydantic output schemas, evidence before answer), `ask.py --answer`.**
Pinned model `gemini-3.8-flash` (free key; `gemini-2.5-flash` is already retired for new users, so the exact
version is recorded with every answer). Model defaults kept for temperature and thinking (thinking tokens recorded
separately); automatic function calling disabled. Retries on 429/500/503 (503 "overloaded" occurred on the first
run). A citation check verifies every evidence quote appears in the sent passages at a scene that was sent, and
every inline citation points to a sent scene.
First run (Dundies): RAG correct and fully cited (6 quotes, 0 problems), covered both Season 2 and Season 7;
LLM-only confidently wrong on two points; hybrid matched RAG and labelled one unverifiable memory claim.
Latency 10-18 s per answer (mostly model thinking + retries), ~5.3k input tokens for RAG.

**2026-10-04: Local web app (`app/server.py` FastAPI + `app/static/index.html`, plain HTML/JS, no build step).**
`POST /api/ask` retrieves once, then runs RAG, LLM and LLM + RAG **in parallel**, and returns retrieval (hits,
passages with matched/neighbour chunks) plus the three structured answers. The page shows the three answers side
by side with badges (answerable / claims to know / from memory), evidence with ✓/✗ from the citation check,
memory claims, conflicts and uncertainties, model/token/latency info, and the passages, where each citation chip
jumps to its scene (red chip = scene not sent). Same shape as the planned demo API; runs on localhost only
because it shows full passages (the public demo must show short excerpts). Fixes made alongside: the citation
check now parses multi-scene citations (`[S2E1 sc.45, sc.46]`); reported latency includes retries and the number
of attempts (Gemini 503 "overloaded" errors are frequent and were hiding ~10 s of waiting).

**2026-10-04: v1 is declared ready.** v1 = chunk set `pack_300t_3s_80min`, embeddings `voyage-4-large@1024`, cosine top
k=8 + ±1 neighbour expansion (no filters, no keyword search), prompts `rag_v1` / `memory_v1` / `hybrid_v1`, LLM
`gemini-3.8-flash` (model defaults for temperature and thinking), three answers per question (RAG, LLM, LLM + RAG).
Later features are recorded as v2, v3...; every logged answer will carry its pipeline version.

**2026-10-04: The study uses Gemini Flash only** (no bigger-model comparison), so differences between versions come
only from pipeline changes. Risk: Google retires model versions (2.5 Flash already gone for new users); stored
answers stay comparable even if the model can no longer be called.

**2026-10-04: Logging capacity is not a constraint.** The whole show with embeddings is 55 MB; one logged question
with three answers and full prompts is ~50 KB raw (Postgres compresses large text), so 10,000 questions are
~250-500 MB.

## Logging and evaluation design

**2026-10-04: Logging: Postgres tables for every question asked (web, CLI), JSONL files for formal eval runs.**
A History view in the web app shows past questions with their three answers and right / partial / wrong marking
(nice-to-have). Full prompts are **not** stored: they're rebuilt from the pipeline version, so each logged answer
records the chunk ids sent and a hash of the prompt file, and chunk sets used by logged answers are never
`--replace`d (a changed strategy gets a new chunk-set name). `office_app` gets INSERT/UPDATE on the log tables only
(confirmed 2026-10-04).

**2026-10-04: Claude as the evaluator (LLM judge).** A different model from the generator avoids Gemini grading
Gemini. Per question it gets the question, the passages sent and the three answers (and the gold answer once it
exists) and returns per-answer verdicts (correct / partial / wrong / refused), groundedness, failure type
(retrieval miss, generation error, memory leak, over-refusal) and a comparison. Preferred route: Anthropic API
paid with the user's $100 credits (pinned model, reproducible); Claude Code headless (`claude -p`) on the user's
subscription for ad-hoc reviews. Cautions: without gold answers the verdict partly rests on Claude's own memory,
so "supported by passages" is reported separately from "correct about the show"; the user's marking is final and
Claude never marks gold answers verified.

**2026-10-04: Fun UX ideas tracked separately in `docs/ux-ideas.md`** (first: a dodging video cutout).

**2026-10-04: Correction: evaluation runs as a Claude Code skill on the user's subscription, not via the API.** The
$100 credit is for Claude Code **cloud sessions** (runs on a GitHub repo and returns a pull request; Pro/Max
promotion, expires 2026-11-05), not API credit, and a cloud session can't reach the local database or the
git-ignored transcripts. The evaluator is a project skill (`.claude/skills/evaluate-answers/`) with a fixed rubric,
procedure and output format, run locally; each verdict records the Claude model that wrote it. The cloud credit
suits coding tasks on the repo (e.g. History view, logging) once the project is a GitHub repo with `data/`,
`.venv/` and `.env` git-ignored. Order: migration 006 → logging → evaluation skill → History view.

**2026-10-04: Theme music on page open (UX idea 2).** `app/static/audio/office-theme.mp3` (downloaded manually by the
user; copyrighted, kept out of the repo, replaced or dropped for the public demo) plays once per page open at 50%
volume; browsers block sound until the visitor interacts, so it falls back to the first click or key press. Mute
button in the corner, remembered in the browser; hidden if the file is missing. FastAPI now serves `/static`.
Random sound bites (idea 3) are postponed. Migration 006 (logging) is written but not applied yet.

**2026-10-04: Dwight backdrop (UX idea 4).** `app/static/image/dwight.png` as a fixed page background at 7% opacity
(5% in dark mode), 40% desaturated; panels stay opaque so it never sits behind text. One CSS variable
(`--backdrop-opacity`) tunes it. Copyrighted still: local only, kept out of the repo.

**2026-10-04: Web app modes and feedback.** User mode (default) shows only the LLM + RAG answer; dev mode shows all
three. Feedback is optional and separate from reviews: user mode asks "satisfactory?" (yes / no, about LLM + RAG);
dev mode asks "which is better, RAG or LLM?" (`rag` / `llm` / `both_good` / `both_bad`; LLM + RAG isn't rated since
it would usually win). New table `qa_feedback` (one row per run per kind, updated on change, CHECKs keep each kind
consistent), so no feedback, either kind, or both are all valid. `qa_runs.mode` records the mode. Proposed cost
rule (superseded below): user mode computes only LLM + RAG. Reviews (`qa_reviews`) stay on-demand: the owner's marking in the History view, and
Claude's verdicts when the evaluation skill is run; nothing is reviewed automatically.

**2026-10-04: Every question always gets all three answers; user/dev mode is only a display choice.** Switching to
dev mode is instant and every question (including friends' questions in user mode) is fully logged for comparison.
`qa_runs.mode` records the display mode at the time of asking. Cost: three model calls per question (~3 questions
per minute on the Gemini free tier).

**2026-10-04: All answers appear together, not one by one.** Showing answers as they finish was rejected: it feels
jumpy and makes side-by-side comparison awkward. The page waits for all three and shows them at once.

**2026-10-04: Migration 006 applied** (`pipeline_versions` with v1, `qa_runs`, `qa_answers`, `qa_reviews`,
`qa_feedback`). Tested as `office_app` in a rolled-back transaction: a default (read-only) session can't insert;
an explicit READ WRITE transaction can log a run, three answers, reviews (own, Claude's, whole-run) and both feedback
kinds, and update feedback; a duplicate whole-run review, a feedback row mixing kinds, DELETE on log tables, writes
to transcript data and registering a pipeline version are all refused. Known follow-up: `ingest/load.py` truncates
`chunk_sets`, which `qa_runs` now references, so it must refuse to reload while logged runs exist (next step).

**2026-10-04: Logging implemented (`common/qalog.py`): `log_run()` writes the run and its answers in one READ WRITE
transaction as `office_app`; `log_feedback()` upserts feedback (for the page step).** `ask.py --answer` logs with
source `cli` (`--no-log` to skip); `POST /api/ask` logs with source `web` and the display mode, and returns `run_id`.
Each answer records its prompt file hash (`generation/answer.py` now returns `prompt_sha256`). A logging failure is
printed and never breaks answering. Tested: run 2 (CLI, dev) and run 3 (web, user mode) each logged with all three
answers; hashes match the prompt files. `ingest/load.py` reload protection is postponed (chunks treated as static).

**2026-10-04: Dev-mode preference is a forced choice, "Which answer is better?" RAG or LLM, with randomized
positions.** "Both good / both bad" removed: an easy middle option gets picked too often and hides the comparison;
feedback stays optional, so someone who likes neither simply doesn't vote. RAG and LLM swap sides at random per
question so voting isn't biased towards one side (people favour one position). The aim is unbiased votes, not
measuring bias, so the display order is not recorded. Migration `007_feedback_forced_choice.sql` (written, not
applied).

**2026-10-04: Migration 007 applied.** `qa_feedback.preferred` now allows only `rag` / `llm`. Tested as `office_app`
(rolled back): a vote and a changed vote work as an upsert; `both_good` is refused.

**2026-10-04: Web page rebuilt with user/dev modes and feedback (taste-skill used as a checklist, not its React stack).**
Design read: a Q&A research tool for one developer and friends, "basic but not boring", Office-supply language:
cool paper, ink, one copier-toner blue accent; the user-mode answer is an interoffice memo (TO / FROM / DATE / RE);
modes are manila folder tabs; sources read as a screenplay; loading shows a skeleton with rotating Office-flavoured
status lines. Fonts Bricolage Grotesque / IBM Plex Sans / IBM Plex Mono; Phosphor icons instead of emoji; no dashes
in visible text; one radius rule (panels 10px, controls 8px, chips and pills full). User mode: LLM + RAG memo,
"Satisfactory? Yes / No", "Show sources" toggle (citation chips open it). Dev mode: LLM + RAG fixed first, RAG and LLM
in random order, "This one is better" in each of the two cards, settings, hits table, matched/neighbour chunks.
`POST /api/feedback` validates and upserts. Verified in Chrome (light and dark): user-mode answer, dev cards, and a
vote saved end to end (run 5). Dwight backdrop opacity set to 0.2 in light mode by the user.

**2026-10-04: Page updates: dark by default, plain Q&A wording in user mode, dev explainer, locked settings.**
- Dark theme is the default regardless of the OS; a sun/moon toggle switches to light (remembered; applied before
  first paint).
- User mode avoids system words (no "RAG", "chunks", "model"); dev mode opens with a short "How this works" note
  (RAG over 4,658 transcript passages, the pinned Gemini Flash model, why a small model: it remembers little, so
  the transcripts' contribution is visible).
- k and neighbours are locked: shown only in dev mode, disabled until unlocked with `DEV_SETTINGS_PASSWORD`
  (`.env`, not set yet, so always locked). Enforced on the server: without the password `/api/ask` ignores k/expand
  and uses 8 / ±1 (`settings_locked` in the response); `/api/unlock` checks the password (constant-time compare).
  The password is kept in the browser's session storage only.
- Office libraries reviewed (community quote APIs, `office-quotes`): not used, since the full transcript is already
  in the database; character avatars possible later. App name "Office RAG" to be replaced (options proposed).

**2026-10-04: Quote of the minute uses local files, no live API.** 326 offline quotes (gumadeiras/office-quotes-cli,
MIT) plus 10 avatars from AkashRajpurohit/the-office-api, downloaded once and resized (160 px, ~80 KB total);
initials for the 3 characters without an avatar. Refreshes every 60 s in the idle and loading views. The Akash API
itself was rejected for live use (Cloudflare rate limit hit at ~45 requests); its `episodes.json` (air date, IMDb
rating, director, writer per episode) saved to `data/raw/akash_episodes.json` for a later metadata step. Details
in `docs/ux-ideas.md` (idea 5).

**2026-10-04: Quote refresh every 30 s (was 60 s).** Shown quotes: median 16 words (~8 s to read), longest 45 words
(~16 s), so 30 s leaves time for every quote without the card sitting idle.

**2026-10-04: App name: Kevinator (tag "The Office"); superseded the same day by Keleven (below).** Dev mode now always shows
the "How this works" explainer (also before any question), filled from a new `GET /api/info` (LLM model, embedding
model, chunk set, number of passages, defaults, whether a settings password is set).

**2026-10-04: GitHub plan (later): push the whole app including media** (avatars, music, Dwight image, quotes, later
the dodging video) plus a setup README; transcripts, processed data, database, `.venv/` and `.env` stay out.

**2026-10-04: Dev explainer wording corrected.** No "free" (that's the API tier, not the model) and no passage count;
the model is described as small and fast, knowing a fair amount about the show but less than larger models.

**2026-10-04: App renamed to Keleven (tag "The Office"); subtitle "No made-up numbers. Every answer shows the scene it
came from."** Keleven is Kevin's made-up number for balancing the books (series finale), the same thing an LLM does
when it fills gaps from memory; the app's point is the opposite (cited scenes). Browser title "Keleven: The Office".

**2026-10-04: History screen and admin mode.** A separate History view (header button, `#history`) lists every logged
question newest first, loaded one question per request as you scroll (`GET /api/history?before=<run_id>`), with the
three answers and collapsible sources; public, since there is no login. Admin mode (header button) checks
`ADMIN_PASSWORD` on the server (`POST /api/admin/check`, constant-time compare; password kept in the tab's session
storage and sent as `X-Admin-Password`). Admins see feedback per question and per-answer review controls (correct /
partial / wrong / refused + notes) saved via `POST /api/review` (reviewer `me`, upsert; refused without the
password). One admin password replaces the separate settings password: k / neighbours are unlocked only for admins
and still enforced by the server. Page script moved to `app/static/app.js`. Tested in Chrome: scroll-loading to the
end (7 questions), no review controls for the public, wrong password refused, a review saved to `qa_reviews`.

**2026-10-04: Prompts amended in place (no new files, no new pipeline version).** Added to all three: "Characters, not
actors" (read "cast", "girl", "people in the office" as characters; name actors only if asked). Subjective questions
are never refused for lack of a stated verdict: present the candidates/sides with citations, then a view and the
strongest point against it; RAG's `answerable` is true whenever the passages hold relevant evidence, and "not in the
passages" only when nothing relevant was retrieved. Minor prompt amendments are tracked by the prompt-file hash
logged with each answer (`qa_answers.prompt_sha256`), not by new versions. Verified on the same question: run 9
(before) vs run 10 (after).

## Phase 1b: Question set

**2026-10-04: Question set started in `eval/questions.jsonl` (5 owner-provided "finish the quote" questions, q001-q005).**
Gold answers are drafts found by SQL over the transcripts; `verified: false` until the owner checks them (Claude never
marks verified). Fields beyond the CLAUDE.md draft: `tier` (famous / mid / obscure), `source` (owner, friends, llm,
sql, adversarial), `verified`, `episode_title`, `speaker`, `notes`; `split` is assigned later, stratified by category.
q003 ("You miss 100% of the shots you don't take") is written on Michael's whiteboard, never spoken, and absent from
all transcript data: kept as a test of RAG saying "not in the transcripts". Quizlet sets were not scraped (their terms
forbid scraping; public quiz questions also inflate the memory baseline); the owner may paste chosen questions.

**2026-10-04: Question set grows to 16 (q006 fake salesman "Lloyd Gross", owner; q007-q016 ten details chosen to be
hard for Flash).** Pre-test of Flash memory-only on q006-q016: about 6 fully right, 4 partly right, 1 wrong. Flash knows
most core facts even for details assumed obscure (the transcripts are online); it fails on attribution and filler:
wrong episode (q010, q011), invented dialogue (q009), misremembered words (q015 "letter" for "butter"), an invented
answer (q008 "$200 laced cupcake"). Consequences: questions should also ask which episode and who said it, grading
must check supporting details, and tiers are set from the Flash baseline, not by intuition. The set must not be
filtered to Flash failures only (that would make "RAG beats Flash" true by construction).

**2026-10-04: Evaluation plan.** About 40 final questions (separate from exploratory ones), run on each pipeline
version (v1 now; v2, v3 later) plus the memory-only LLM, then a Claude analysis of progress across versions and against
Flash. To confirm: v2 = hybrid search, v3 = SQL + router; which answer per version enters the comparison.

**2026-10-04: Transcript-mined hard questions (q017-q026).** Added 10 questions mined from the transcripts on
minor characters and small details, each screened on both Flash memory and v1 RAG before keeping it. The 3 that
Flash also gets right are kept as neutral questions, and the 1 retrieval miss is kept as a v2 test, so the set isn't
filtered by outcome. Tier comes from the Flash result (obscure = Flash wrong or partly right). All unverified. Episode
numbering: answers may use split (S4E14) or combined (S4E10) numbering, and graders accept either.

**2026-10-04: Version plan confirmed.** v1 = vector RAG (done). v2 = improved RAG: hybrid search (vector +
keyword), SQL and an LLM router. v3 = Graph RAG. Gold answers are not a priority now; questions are collected first
and gold answers are added later (they stay `verified: false` until then).

**2026-10-04: Question set widened to 78 (q027-q078), no size cap.** Added transcript-rooted questions by type:
who said it, which episode, exact counts (SQL over the dataset), lists, order in time, why, outside the transcripts,
multi-hop, and things you see (stage directions), plus the owner's 13 (opinion, counterfactual, false premise,
loaded, story arc). Built with SQL only, no LLM calls. Facts were checked in the scenes; counts are dataset counts
and will shift after the speaker-map review. Some gold answers are drafts or empty; tiers are left empty until a
baseline run. No LLM calls without the owner's go-ahead.

**2026-10-04: Speaker-map review rows stay unapplied.** The 22 `review` rows in `ingest/speaker_map.csv` (David /
David Wallace, Robert / Robert California, Todd / Packer / Todd Packer, Holy / Molly / Holly, ...) are not applied,
and chunks are not rebuilt. Linking name variants to one character is left to the LLM at answer time; where it fails,
that is a finding about data cleaning, not something to patch. Count gold answers use the dataset as loaded.
Consequence for v2: text-to-SQL will see split names, so count questions about these characters test whether the
SQL step finds the variants.

**2026-10-04: No dev/test split; prompts frozen after one fix.** Prompt tuning rounds would be too many
iterations, so all 79 questions are one set (`split: "test"`) and prompts are fixed once now, from question types,
not from results: wrong-premise rule, hypotheticals added to the subjective rule, counts/lists rule (passages are a
sample; say a count may be incomplete). Edited in place (rag, memory, hybrid); the hash in qa_answers records the
change. After the baseline, prompts change only with a logged decision. q079 added (owner): "Jim. False. I do not
miss him" (Dwight, S3E1 sc.3); the transcript line stops before those words, a known gap.

**2026-10-04: Eval answers appear in History.** Eval runs are logged like web runs (`source='eval'`, eval_label,
question_id) and show in History; no filtering.

**2026-10-04: Eval runs use the Gemini Batch API.** Retrieval runs locally for all questions, prompts are built,
one batch job is submitted (about 50% cheaper, asynchronous), and results are written to Postgres and
eval/runs/<label>.jsonl.

**2026-10-04: Output limit raised from 4,096 to 16,384 tokens (web app and eval).** The limit includes thinking.
In the v1 baseline, 232 of 237 answers finished thinking by 2,910 tokens, but 5 hit the cap at about 3,930 thinking
tokens and were cut off or squeezed (q017 llm, q017 hybrid, q019 llm, q037 llm, q047 rag). The limit is a hard stop
the model doesn't see, so answers that finished under it are unaffected; only those 5 were re-run (single online
calls, new limit). With the new limit they used up to 13,261 thinking tokens. Model max output is 65,536.

**2026-10-04: v2 keyword search = BM25, fused with vector search (hybrid).** Postgres built-in full-text ranking
(`ts_rank`) has no IDF, so a rare word ("beyonce", 4 of 4,658 chunks) counts the same as a common one; BM25 weights
by rarity, which is what quote and small-detail questions need. ParadeDB pg_search rejected for now (different DB
image, not offered by most managed Postgres hosts). BM25 runs in Python over the chunks table; results are merged
with vector results by RRF. Fuzzy (typo-tolerant) matching postponed: see docs/open-questions.md.
Motivation measured on the v1 baseline: the right scene was sent for 44 of 55 questions with known scenes; exact
quotes missed (q002, q027, q031, q017). For q027 the right chunk ranked 11th by vector search: dilution (a 10-token
line in a 355-token chunk), question wording ("Who says...") and the accent (Beyoncé vs Beyonce, rank 11 vs 6).

**2026-10-05: v2 retrieval wired in; k stays 8.** Hybrid search (vector top 50 + BM25 top 50, RRF rrf_k 60) is
pipeline version v2 (migration 008). `retrieval.retrieve(question, version)` picks v1 or v2; the web app, ask.py and
eval/run.py use v2 by default, and logging infers the version from the retrieval method. k=10 added no recall and
k=12 one question for +46% prompt tokens (experiment log 2026-10-05), so k stays 8. A chunk found by only one list
can sink in RRF (q048); accepted rather than tuned, since there is no dev split.

**2026-10-05: Dev mode offers a pipeline version picker (v1 Vector, v2 Hybrid, v3 Graph "soon").** For demos:
ask the same question on v1 and v2 and compare. Not locked behind admin (every version costs the same per
question); user mode always uses the current version (v2). v3 is shown disabled and rejected by the server until
it exists. Each logged run records the version it used, so History shows which one answered.

**2026-10-05: No separate router; one fast "enhancer" call before retrieval (v2b).** A router and an always-on
SQL call both cost one extra call per question (about 4 calls instead of 3 with the three answers), so they are
merged: one Flash call with minimal thinking and a short output returns `sql` (or null), `assumptions`,
`search_text` (the question rewritten for search) and `season` (only if the question names one). Hybrid search
uses search_text and the season filter; SQL runs in parallel; the answer calls still get the original question. If
the enhancer fails or is slow, v2 falls back to plain hybrid search on the question, without SQL.
Main risk: memory leaking into retrieval (e.g. adding "Andy" to the Cornell sweater question, which Flash's memory
gets wrong). The prompt (generation/prompts/enhance_v1.md) forbids adding anything not in the question, answering,
correcting premises, or adding synonyms; null is always safe. Its examples are new, not from the eval set.
Two-event splitting (q048) is not included yet. Each run's enhancer output will be logged (new `plan` column).

**2026-10-05: Enhancer without a season filter; the ~2 s accepted.** The first test (exploration log 13) showed no
memory leaks and SQL finding the evidence for all 3 questions, at 1.7-2.6 s per call with thinking "low" (0
thinking tokens; "minimal" is rejected by gemini-3.8-flash). Search waits for the call so it can use search_text;
that delay is accepted. The `season` output and the season filter on search are dropped: a hard filter hides the
right scene whenever the question names the wrong season. Season and episode numbers are left out of search_text
(the transcripts don't contain them); SQL may still filter by a season the question names. The enhancer now returns
search_text, sql, assumptions.

**2026-10-05: v2 = enhancer + hybrid search + SQL, implemented (migration 009).** qa_runs.plan (jsonb) logs per
run: search_text, the SQL actually run, assumptions, the SQL result (columns, rows, truncated, error, retried) and
the enhancer's latency and tokens. v2's pipeline_versions config now includes the enhancer (no v2 runs existed, so
redefining was safe). Enhancer failure fails the request (HTTP 502). SQL failure: one fix attempt with the database
error; if it still fails, the answer uses search only and the error is logged and shown to the answer model. SQL
safety: office_app role (read-only, 5 s timeout) plus one SELECT/WITH statement, no comments or semicolons, wrapped
in LIMIT 51, cells cut to 300 characters. Scenes in an SQL result (season, episode, scene columns) add up to 4
chunks to the passages, so they are cited like any scene; all rows also go to the answer as an "SQL result" block.

**2026-10-05: Answer prompts told how the evidence was found (rag and hybrid).** (First applied to the v1 files
in place; corrected the same day, see "Prompt files are per version" below.) The message now
starts with "The transcripts were searched for: <search_text>" when the enhancer rewrote the question, and may end
with the SQL result block. The prompts explain both: passages match the search text, not the exact question, so
some may be off-topic and the question as asked is what gets answered; the SQL result covers all lines (not a
sample), so its counts are totals for the dataset, cited [SQL], with the counting assumption stated and failed or
empty queries not taken as proof of absence. Counts rule now defers to an SQL result. Memory prompt unchanged.
v1 runs get no search text or SQL block, so these parts don't apply to them.

**2026-10-05: Prompt files are per version; evaluated files are frozen.** Editing rag_v1.md / hybrid_v1.md broke
the link to the v1 baseline, so the v1 files were restored byte for byte (hashes match the baseline job: rag
5ef7191d, hybrid 2f685a0f) and the new rules went into rag_v2.md / hybrid_v2.md, derived from v1. PROMPT_FILES in
generation/answer.py maps each pipeline version to its files (v2 keeps memory_v1.md); answers pick the version of
their retrieval; migration 010 records v2's files in pipeline_versions; generation/prompts/README.md records the
lineage. This replaces the earlier "edit prompts in place" rule for any file a version has been evaluated with;
small edits before a version's first evaluation can still go in place.

**2026-10-05: Model unfaithfulness recorded as a known limitation; no prompt change.** In the v1 baseline the
answer model broke explicit prompt rules in a few cases (exploration log 14): it invented "exact" quotes and gave
them scene numbers (5 quotes in 4 answers), stitched a quote from several lines, set answerable=false while
answering part of the question (3), and mixed [memory] with scene citations (3). The rules are already explicit,
so this is treated as a limit of the model's faithfulness, not unclear wording. The citation check catches the
invented quotes; it is reported per answer and will be part of grading. rag_v2 / hybrid_v2 are unchanged.

**2026-10-05: Dev-mode answer comparison; memory answers reused.** A question asked before (same text after trimming,
ignoring case and repeated spaces) offers every stored answer kind in dev mode: memory, v1 RAG, v1 RAG + memory,
v2 RAG, v2 RAG + memory (v3 later), the latest of each; the user picks any three to show side by side. The memory
answer doesn't depend on the version, so when one is stored for the question it is reused instead of calling the
LLM again (the new run records which run it came from). Computing answers for another version stays a dev-mode
action (the version picker); user mode is unchanged.
Implementation (migration 011): qa_answers.reused_from_run records the run a reused memory answer came from; an
expression index on the normalized question serves the lookups (common/stored.py). /api/ask computes only the
answers it can't reuse; GET /api/compare returns the latest stored answer of each kind. Eval batches skip memory
requests whose answer is stored and fill them in at collect, so a v2 eval run is 158 answer calls (+ 79 enhancer
calls), not 237.

**2026-10-05: "Judgments about characters" rule added to rag_v2 / hybrid_v2 (in place: v2 not evaluated yet).**
From exploration log 15 ("most boring main character"): lines are said by someone for a reason, so insults,
self-deprecation and sarcasm aren't evidence of a label, and a character using a word isn't evidence of the
trait; for series-wide judgments the passages are a few word-matched scenes, used as examples, not the basis. rag
says how narrow the sample is; hybrid may lead with memory for such judgments (labelled [memory]), and its "passages
first" and "conflicts" rules now apply to facts. v1 prompts untouched. q080 added (owner, opinion).

**2026-10-05: Phases follow pipeline versions.** Phase 1 = v1 (vector RAG, locked with the v1 baseline),
Phase 2 = v2 (hybrid search + enhancer + SQL), Phase 3 = v3 (graph). Findings docs follow suit: findings/phase-1.md
covers v1, phase-2.md v2. This replaces the CLAUDE.md phase table (Phase 1 vector + keyword, Phase 2 SQL + router).

**2026-10-05: Evaluation = blind holistic grading by Claude (evaluate-answers skill, rubrics-v1).** Per question,
Claude sees all answers (memory, v1 rag/hybrid, v2 rag/hybrid) shuffled under letters with their type only, builds
a reference from the transcripts first (SQL + scenes; its own memory only as a hint), then judges every answer with
the rubric for the question's kind: fact, count, list, explanation, judgment, plus false-premise and off-camera
rules, and per-type checks (transcripts: grounded / honest refusal; memory: calibration; both: labelling). One
failure type per non-correct answer feeds the v3 design. Verdicts are qa_reviews by claude:claude-opus-5-5, never
gold; the owner spot-checks about 10 questions. Blinding is imperfect: SQL results and [SQL] citations reveal v2.
Summary columns per version (v1 memory / rag / hybrid, v2 ...); a memory answer shared by both versions is graded
once (only q017 differs: v2 reused run 90's memory answer). Files: .claude/skills/evaluate-answers/, eval/grade.py.

**2026-10-05: Grading method: single blind grader for facts, debate for judgment-type questions; scores out of
10.** Fact, count, list, off-camera: one blind grader against the reference. why, story_arc, opinion,
counterfactual, loaded, false_premise: debate, one round: an advocate per answer type (memory, transcripts only,
transcripts + memory; all three, so no type is favoured or left undefended) writes a short brief (concede own
mistakes first, then points with proof, at most two weaknesses of others with proof), then a neutral judge checks
the proofs and decides in one pass. Proof = a checked transcript scene or the reference; the memory advocate must
prove memory's claims in the transcripts too. Advocates on a faster model (Sonnet), judge on the main model; briefs
about 150 words. Every answer gets a score 0-10 with fixed anchors, consistent with the verdict. References: 80,
built blind (63 high, 14 medium, 3 low); owner reviews about 17.

**2026-10-05: Grading sets get random names.** Names like g1 / g2 imply an order and so hint at versions; `init`
now creates a random name (s-xxxxxx) per run, and only the coordinator knows the mapping (config.json, which
graders may not read). The pilot set g1 was renamed s-556ab2 and its 18 reviews re-saved with the new name.

**2026-10-05: Grading by council (option c), replacing single grader + debate.** Three identical graders would
agree for the wrong reason (same model, same prompt), and the pilot's advocates mostly produced one-sided attacks.
So every question is graded by a council of lenses: fact (is it true), faithfulness (honest about its evidence;
memory calibration), reader (understands the show: context, sarcasm, completeness; judgment criteria). Members
work independently (never see each other's notes), each with proof for every finding; a chair (main model) checks
disagreements in the transcripts and gives one final score 0-10 per answer (not an average; fact errors weigh most,
reading most for judgment questions). One agent per lens per batch of about 10 questions (independence between
lenses at about a tenth of the cost of one agent per member per question). Fact and faithfulness on Sonnet, reader
and chair on the main model (model diversity). Council verdicts are saved as reviewer claude-council:<model>.

**2026-10-06: v1 judgment scores corrected.** Ten answers the B7 chair had lowered from 8 to 7 (to fit a mismatch
between the judgment bands in rubrics.md and eval.grade save) were restored to 8; rubrics.md now uses 8-10 / 4-7 /
0-3 for judgment totals too. Originals are kept in each verdict's details.adjusted.

**2026-10-06: v2 graded; next steps for the evaluation.** v2 (set s-bcc971) graded by the same council as v1; results
in experiment-log.md. Memory answers are reused between versions, so their v1 / v2 difference (7.3 / 7.1) is taken as
grading noise and sets the threshold: only differences above about half a point on a mean count. Plan: (1) log
(done), (2) review the biggest per-question changes (done in the log), (3) fix the rubric gaps before the v3 grading
(v1 / v2 verdicts stay as graded), (4) optionally regrade about 10 memory answers to measure noise, (5) use the list
of remaining failures as the v3 design brief, (6) after v3, run the same 80 questions and compare v1, v2 and v3.

**2026-10-06: Owner review of three low-confidence references.** q003 (Gretzky quote, words not in the dataset):
reference confirmed correct. q070 (short appearance, high impact): kept as is; recorded as having no single correct
answer. q080 (most boring main character): reference confirmed, Toby is the universally accepted answer. All three are
marked verified_by_owner in eval/grading/references/. Scores already given are unchanged.

**2026-10-06: v1 vs v2 analysis written** to findings/v1-v2-grading-analysis.md (mechanisms, remaining weaknesses, rubric gaps, v3 lessons, plan A-D). Finding to carry into v3: the enhancer echoes the question (67 of 80 plans add at most one new word), SQL is not retried when it returns 0 rows (q071), and BM25 has no stemming (q073 'marry' vs 'married').

**2026-10-07: Owner review of references (REVIEW.md).** Confirmed correct: q003, q026, q044 (go with the transcripts:
Season 2), q060 (Kelly left Ravi and ran off with Ryan Howard), q080. q046: any character named as a manager is fine,
Creed was also a manager. q054: Michael settled with Holly. q055: transcripts cannot answer it; an answer from general
knowledge is fine. q070: no single correct answer. Marked verified_by_owner with an owner_note in
eval/grading/references/. Questions whose answer is not in the transcripts (q003, q055, q079) stay in the set: the
resulting randomness is accepted. Scores already given are unchanged. Not yet reviewed by the owner: q040, q072, q079.

**2026-10-07: Owner review, remaining references.** q040: the owner's list (eval/grading/references/that's, 48 rows)
is the correct answer: Michael 30 times, +-1 accepted, Dwight second (4). The dataset has only 24 Michael lines, so a
transcript-only answer of 24 with what it counted is also accepted (accepted_alternatives). q072: the show gives no
verified count of Dwight's cousins; "we do not know" is acceptable (the boast of seventy is only a claim). q079: it was
Dwight; the data lacks the punchline words. All marked verified_by_owner. These three references changed or were
clarified after v1 and v2 were graded; existing scores are unchanged and no regrade is planned unless the owner asks
(q040 answers of about 24 would still be accepted; q072 B "no number is ever stated" is now less wrong, still invents Cousin Heiss).

**2026-10-07: Question notes corrected and rubrics-v2.** questions.jsonl (owner yes): q032 gold now Stanley to Ryan, Take
Your Daughter to Work Day S2E18 sc.23 (flashback S5E13 sc.8); q060 Ryan Howard, job not stated in the finale (Ravi is
the pediatrician); q073 premise true, Kelly married Ryan (S7E14 sc.1). rubrics-v2 closes the gaps found in grading:
failure type memory_unsure (honest "don't know" from memory); judgment answers whose better evidence was not sent are
retrieval_miss; "answers only from its sample" is support / reading, not scope; quote-not-in-data rule (q079);
accepted_true outcome for a true premise; owner counts with tolerance (q040); a "how many" list is graded per its
reference (q072); off-camera partly covered by the transcripts (q054). eval/grade.py records rubric rubrics-v2 and
accepts memory_unsure. v1 and v2 verdicts stay under rubrics-v1 and are not regraded. The questions file changed, so
its hash differs from the one stored with the v1 and v2 runs (gold answers are not used by the systems or graders).
