# Architecture

How the whole system fits together: the offline pipelines that prepare the data, the online path that answers a question,
the evaluation machinery, and how it is meant to be hosted. For the reasoning behind each choice see
`findings/decisions.md`; for results see `findings/phase-3.md`.

## 1. What it is

A question-answering system over the complete transcripts of *The Office (US)* (186 episodes, 57,973 lines). It answers
with citations to exact scenes, and it was built as a measured study: three pipeline versions, each added on top of the
last and graded against the same question set.

| Version | What it adds | Answers a question by |
|---|---|---|
| v1 | vector search | finding the 8 scene-chunks closest in meaning to the question |
| v2 | an enhancer, keyword search, SQL | rewriting the question, merging vector and BM25 results, optionally counting with SQL |
| v3 | a graph of relationships and events | v2, plus an LLM-written query over facts extracted from every episode |

All three stay runnable side by side: a question can be asked with any version, and each version keeps its own prompt files.

## 2. The big picture

```
OFFLINE (run once, rerunnable)                                   ONLINE (per question)

 raw transcripts (data/raw)                                       browser (app/static)
   │ ingest/clean.py                                                  │  POST /api/ask
   ▼                                                                  ▼
 episodes, lines ──► chunks ──► embeddings                        app/server.py (FastAPI)
   (Postgres)       ingest/    ingest/embed.py                        │
   ingest/load.py   chunk.py   (Voyage)                               ▼
   │                                                           ┌─ 1. ENHANCER (1 Gemini call, v2/v3)
   │ graph/run_extraction.py (Gemini, 2 passes/episode)        │     question → search text, SQL, graph SQL
   ▼                                                           │
 episode_extractions (JSON per episode)                        ├─ 2. RETRIEVE, in parallel
   │ graph/link_certain.py, link_tiers.py                      │     • hybrid search: Voyage query embedding →
   │ graph/build_graph.py                                      │       pgvector cosine + in-memory BM25 → RRF
   ▼                                                           │     • SQL over the transcript tables (read-only)
 graph_* tables ──► views (014-016)                            │     • graph SQL over graph views (read-only)
   characters, events, relations,                              │
   timelines, entities                                         ├─ 3. ANSWER (Gemini, up to 3 answers)
                                                               │     rag (transcripts only), hybrid (+ labelled
 evaluation (eval/)                                            │     memory), memory (reused if stored)
   questions.jsonl, references,                                │
   batch runs, council grading                                 ├─ 4. CHECK  citations vs what was sent
                                                               │
                                                               └─ 5. LOG   qa_runs, qa_answers (Postgres)
```

External services: **Postgres 17 with pgvector** (one database for everything), **Gemini** (`gemini-3.8-flash`) for the
enhancer, the answers and the graph extraction, **Voyage** (`voyage-4-large`, 1024 dimensions, reached through the
MongoDB Atlas endpoint) for embeddings. Nothing else.

## 3. Offline pipelines

### 3.1 Transcripts to chunks and vectors
`ingest/clean.py` normalises speaker names and artefacts, `load.py` fills `episodes` and `lines`, `chunk.py` packs
scenes into chunks of up to 300 tokens and 3 scenes (min 80 tokens; the set `pack_300t_3s_80min`, 4,658 chunks), and
`embed.py` stores one vector per chunk (`chunk_embeddings`, 1024 dims). Search is exact cosine in pgvector: at this size
an approximate index is not needed. `scripts/bootstrap.sh` runs all of this on an empty database (the embedding step is
run by hand because it costs API calls).

### 3.2 The graph (v3)
One Gemini call per episode extracts characters, places, events and relationships as JSON with line ids as evidence, and a
second call corrects it (removes details no line shows). Code validates the result. Then:
1. `link_certain.py` / `link_tiers.py` decide which characters are the same person across episodes, using only the data
   (no LLM): **certain** (name recurs in 40+ episodes), **probable** (full name, 3+ episodes), **possible** (one-word name).
   A weak link is stored with its tier and is never merged.
2. `build_graph.py` loads the `graph_*` tables from the stored JSON.
3. Views (`graph_relations_now`, `graph_events_now`, `graph_timeline_now`, `graph_characters_now`, function `graph_lines`)
   resolve ids to names and entities. `graph_timeline_now` turns begins/ends/revealed rows into relationship intervals.

Everything after the extraction can be rebuilt without an LLM call. Design: `docs/graph-design.md`, tables:
`docs/graph-schema.md`.

### 3.3 Evaluation
`eval/questions.jsonl` (92 questions), transcript-only references (`eval/grading/references`, built independently of the
system, reviewed by the owner), batch runs through the Gemini Batch API (`eval/run.py`; v3 uses two batch jobs, enhancer
then answers), and a **council grading** (`eval/grade.py` + the `evaluate-answers` skill in `eval/skills/`): three lens
members (fact, faithfulness, reader) judge each answer and a chair decides. A grading set can hold several runs shuffled
together so the same graders judge both versions blind.

## 4. The online path in detail

| Step | v1 | v2 | v3 | Code |
|---|---|---|---|---|
| Enhancer | none | search text + optional SQL | + optional graph SQL | `generation/enhance.py`, `enhance_v3.py` |
| Search | vector | vector + BM25, RRF | same as v2 | `retrieval/vector.py`, `keyword.py`, `hybrid.py` |
| SQL | none | read-only, 50 rows, 5 s | same | `retrieval/sql.py` |
| Graph | none | none | read-only, 50 rows, lines attached | `retrieval/graph.py`, `hybrid_v3.py` |
| Answer prompts | `rag_v1`, `hybrid_v1` | `rag_v2`, `hybrid_v2` | `rag_v3`, `hybrid_v3` | `generation/prompts/`, `answer.py`, `answer_v3.py` |
| Dispatch | `retrieval/__init__.py: retrieve(version=...)` | | | |

In v3 the enhancer also says whether the scenes its queries point at are needed (`context`: scene or none). For "scene" the scenes of the SQL rows and of the graph rows' transcript lines (at most 6 chunks, plus one neighbour each side) join the passages, so a matched line brings its conversation. Counts and rankings (`none`) add nothing.

Safety of generated SQL (transcript and graph): the query runs as the read-only database role `office_app`, must be a single
SELECT, is wrapped with a row limit, and has a 5 s timeout. A failing query gets one correction attempt from the model.

The memory-only answer does not depend on the version, so a stored one is reused instead of calling the model again.

Prompt files are frozen once a version has been evaluated; a change means a new file (`generation/prompts/README.md`).

## 5. Database

One Postgres database (65 MB in total):

| Layer | Tables / views | Migrations |
|---|---|---|
| Transcripts | `episodes`, `lines`, `lines_full` | 003 |
| Chunks and vectors | `chunk_sets`, `chunks`, `embedding_models`, `chunk_embeddings` | 004, 005 |
| Pipeline registry | `pipeline_versions` | 008, 010, 017 |
| Question log | `qa_runs`, `qa_answers`, `qa_feedback`, `qa_reviews` | 006, 007, 009, 011 |
| Graph extraction (raw JSON) | `extraction_runs`, `episode_extractions` | 012 |
| Graph | `graph_builds`, `graph_current`, `graph_entities`, `graph_entity_links`, `graph_characters`, `graph_places`, `graph_events`, `graph_event_participants`, `graph_relations`, `graph_refers_back`, `graph_episode_summaries` | 013 |
| Graph views | `graph_*_now`, `graph_lines()` | 014, 015, 016 |

Roles: `office_admin` loads and builds data; `office_app` is read-only by default and is allowed to write only the question
log tables. The app and every generated query use `office_app`.

## 6. The web app

`app/server.py` (FastAPI) and `app/static` (one page, plain JavaScript). Two modes:
- **User mode:** ask a question, read the answer with citation chips that jump to the cited scene, optional sources.
- **Dev mode:** pick the pipeline version, see the enhancer output, the SQL and graph queries and their rows, the search
  hits, and compare stored answers; admin password unlocks retrieval settings and reviews.

The page asks with v3 by default (`APP_DEFAULT_VERSION`); v1 and v2 are selectable in dev mode. Every question and answer is
logged to Postgres.

## 7. Code map

| Folder | What is in it |
|---|---|
| `ingest/` | clean, load, chunk, embed the transcripts |
| `retrieval/` | vector, keyword, hybrid, SQL and graph retrieval; version dispatch |
| `generation/` | model access, enhancers, answer builders, prompt files |
| `graph/` | per-episode extraction, review, validation, linking, table build |
| `eval/` | questions, references, batch runner, grading tool, grading sets, evaluation skill |
| `app/` | the web server and page |
| `common/` | database connections, Voyage client, question log, stored answers |
| `db/migrations/` | 001-017, applied in order with the admin role |
| `docs/`, `findings/` | design documents, decision log, experiment log, results |
| `scripts/` | `bootstrap.sh` for a new machine |

## 8. Hosting (planned)

Target: a public demo URL without buying a domain. See `docs/hosting.md` for the plan, costs and the controls that keep a
public endpoint safe (excerpt-only sources, no history for visitors, rate limits, a daily question cap).

## 9. Limits worth knowing

- The graph is extracted by a model reading each episode: it is mostly right (a 50-item sample found none wrong) but
  incomplete (325 relation rows; 31 episodes have none). Weak character links stay out of merges.
- Minor recurring characters are not entities; questions that name nobody get no graph query.
- Answers can only be as complete as the fan transcripts; much of the show is visual.
- Grading is by language-model graders: single-answer scores are noisy by 1-2 points.
