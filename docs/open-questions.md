# Open questions and deferred work

Things we decided to postpone, with where they belong. Decisions themselves are in `findings/decisions.md`;
this list is what's still open. Move an item to the decision log when it's settled, and delete it here.

**Versions:** **v1** = the pipeline working end to end with vector search only (store → chunk → embed → retrieve →
generate). **v2** = hybrid search (vector + keyword) and retrieval improvements.

## Learning topics (to study at the end)

- **Vector search indexes and how vector search works at scale.**
  - Exact search vs approximate nearest neighbour (ANN): why exact is fine at 4,658 vectors and impossible at
    hundreds of millions.
  - How HNSW (graph-based) and IVFFlat (cluster-based) indexes work, their build time, memory and recall
    trade-offs, and their settings (`m`, `ef_construction`, `ef_search`, `lists`, `probes`).
  - Filtering with ANN: why filtering after the search can return fewer than k results, and how partial indexes,
    pgvector's iterative scans or partitioning avoid it.
  - Storage at scale: `halfvec`, binary quantization, shorter Matryoshka vectors, re-ranking with full vectors.
  - Beyond one Postgres: dedicated vector databases, sharding, and when pgvector stops being enough.
  - Practical: add one HNSW index per experiment here (partial expression index on `embedding::vector(1024)
    WHERE model_id = X AND chunk_set_id = Y`) and measure recall@k and latency against exact search.

## v2: Hybrid search

- **Keyword index** (migration 006 draft): generated `tsvector` column on `chunks.content` (`english` config) +
  GIN index. Without it, a keyword query re-processes every chunk (~293 ms); with it, ~1 ms.
- **Ranking:** Postgres `ts_rank_cd` has no IDF (rare words aren't weighted higher). Compare with real BM25:
  a Postgres extension (`pg_search`, VectorChord-bm25; managed-host support varies) or BM25 in Python
  (`bm25s`, in memory).
- **Query form:** `websearch_to_tsquery` requires every word (AND); retrieval needs OR plus ranking.
- **Merging the two rankings:** Reciprocal Rank Fusion (RRF) or weighted scores; how many results from each.
- **Fuzzy matching** (`pg_trgm`) for misremembered quotes and typos, if exploration shows they fail.
- **Re-ranking** the merged top ~50 with a re-ranker model (Voyage offers `rerank-3`).

## v1: Still to decide while building

- **Retrieval (Part 4):** k (how many chunks), neighbour expansion ±1 chunk (decided) and how to merge overlapping
  hits, how retrieved chunks are formatted for the LLM.
- **Generation (Part 5):** Gemini Flash via a free AI Studio key (`GEMINI_API_KEY`, to be added). Prompt,
  citation format, "I don't know" behaviour, which Flash version to pin.
- **Copyright in answers:** short cited excerpts only, never whole scenes (hosting rule).
- **Prompt changes still open:** quote-first answering, marking matched chunks. (Subjective questions and
  "characters, not actors" were amended in place on 2026-10-04.)
- **Metadata filters (Phase 2 router):** removed from v1 (a manual `seasons` filter was tried and deleted). Options:
  rules ("season 2" → [2]), LLM extraction of structured filters (self-query), or a soft boost instead of a hard
  filter. Risk: a wrong hard filter silently removes the right answer; safeguard = search with and without the
  filter, or fall back when filtered results are weak. Speaker filters would need a speakers column on chunks.

## Chunking (Part 2 follow-ups)

- **250 vs 300 token target:** only 300 is stored; build `pack_250t_3s_80min` and compare once the question set
  exists.
- **Merge-step limitation:** merging small chunks has no scene cap and joins whole chunks (montages up to 6–7
  scenes). Alternatives: scene cap during merge, or borrowing scenes one at a time.
- **Contextual headers:** an LLM-written context sentence per chunk (resolves "this happens"-style references).
- **Plot-thread grouping** and **multi-level indexes** (scene / group / episode summaries) for storyline questions.
- **Overlap or topic-aware boundaries** if split stories fail to match.

## Embeddings (Part 3 follow-ups)

- **Compare models** once the question set exists: a local open-source model (e.g. Qwen3-Embedding-0.6B, BGE-M3)
  vs voyage-4-large; possibly OpenAI if credits are added.
- **voyage-4-lite for queries** with voyage-4-large documents (the voyage-4 family shares one vector space).
- **Dimensions:** 1024 now; test 512 / 256 (smaller, faster) for the quality trade-off.
- **Query-embedding cache** for repeated questions.

## Evaluation (Phase 1b)

- Design the question set from Phase 1 exploration (`findings/exploration-log.md` not started yet).
- Include whole-dataset questions ("major storylines of Season 5") and Threat Level Midnight questions (data
  mostly missing; tests "I don't know").
- Baselines (Gemini Flash, one pinned version): no tools, with Google Search grounding, the Phase 1 system.
- Report by popularity tier; the obscure tier stands in for private company data.
- Web baseline caveat: the transcripts are online, so web search is stronger here than it would be on private data.
- ~~Bigger-model comparison~~ dropped: the study stays on Gemini Flash (decision 2026-10-04).
- LLM-as-judge: Gemini grading Gemini; consider a different judge model and keep human spot checks.
- **Groundedness metric:** "answer only from the passages" is an instruction, not a guarantee; memory leaks by
  filling gaps, winning conflicts, citing scenes for remembered facts, and answering unanswerable questions.
  Measure the share of claims supported by their cited passages: counterfactual tests, a citation support check
  (does the cited scene contain the claim, not just was it sent), unanswerable questions, the `answerable` flag.
  Prompt v2 option: quote the supporting lines first, then answer from them.
- **The Office is very famous**, so memory and web baselines start strong. Two ways to approximate private data:
  - **Deleted scenes** as a separate, little-known slice (dropped from the main data; could be loaded separately
    for a question subset the model has barely seen).
  - **Counterfactual tests:** change one fact in a copy of a few chunks (e.g. Jim's costume costs "fifteen" not
    "eleven") and check whether the answer follows the retrieved text (grounded) or memory.

## Data (Phase 0 leftovers)

- **Speaker map:** 22 rows marked `review` in `ingest/speaker_map.csv` (David → David Wallace, Molly/Holly,
  Joan/Jan, Todd/Packer, Bert, Diane Kelly, ...).
- **Review files** in `data/processed/review/`: 348 guessed mojibake fixes, 3 broken speaker fields, 20 lines with
  unbalanced brackets.
- **Small transcript typos** seen in passing ("we're going to recalling", "It would awesome"): leave unless they
  hurt retrieval.
- **schrute dataset** not evaluated: air dates, writers, directors, IMDb ratings if metadata questions matter.

## Infrastructure

- **GCP $300 free-trial credits** (usually expire after ~90 days; GPUs typically excluded). Best uses: Gemini via
  Vertex AI (paid quotas, fewer 503s, prompts not used for training; same model as a new provider class) and
  later the demo hosting (Cloud Run + Cloud SQL with pgvector). Set budget alerts first. More disk/compute isn't
  needed (55 MB database).

- **Git repo / GitHub (later):** ship the whole app, **including the media** (avatars, music, Dwight image, quotes,
  the dodging video later), per the user's decision; write a setup README. Still excluded: `data/raw/`,
  `data/processed/` and the database (transcripts must not be published, CLAUDE.md), `.venv/`, `.env`.
  Risk noted: the media is from the show (copyright).
- **Migration tracking:** no record of applied migrations (all are re-runnable for now). A `schema_migrations`
  table or a tool (e.g. dbmate) before hosting.
- **App connection settings:** passwords contain URL-special characters, so `DATABASE_URL` must be
  percent-encoded or replaced by separate parameters.
- **LLM-written SQL (Phase 2):** allow a single SELECT only and set `statement_timeout` from the app with
  `SET LOCAL`; the app role can raise its own timeout.
- **Hosting the demo:** where the app and a managed Postgres would run.

## Typo-tolerant keyword search (later)
BM25 matches exact words only: "Beyonse" does not match "beyonce". Standard fix: correct each query word to the
closest word in the index vocabulary (edit distance or trigrams, as Elasticsearch "fuzziness" does), then score
with normal BM25 so the real word's rarity is kept. Risks: short names (Jim/Tim, Pam/Ham), so no correction for
very short words. Vector search already tolerates typos partly. Needs misspelled eval questions to measure.
