# Postgres schema

Status: **draft, under discussion.** Decisions are recorded in `findings/decisions.md` as they're made.

Scope: the tables needed to store the cleaned data (Part 1). Tables for chunks and embeddings come in
Parts 2–3 and are only sketched here.

## Entities

```
episodes 1 ──< lines
(season, episode)   (season, episode, scene,
 title               one speaker, one dialogue, 0..n directions)
```

- An **episode** has many lines. Two-part episodes are one episode (HF numbering).
- A **scene** is identified by `(season, episode, scene)` on each line. It has no attributes of its own, so it
  has no table. If scene-level attributes are needed later (e.g. summaries), a `scenes` table can be created
  from `lines` with `SELECT DISTINCT season, episode, scene`.
- A **line** is one speaker's turn: one stretch of dialogue with stage directions in place.
- Only aired scenes are stored (8,849 scenes, 57,973 lines). Deleted scenes are filtered out at load.

## Tables

```sql
CREATE TABLE episodes (
  season          int  NOT NULL,
  episode         int  NOT NULL,
  title           text NOT NULL,
  PRIMARY KEY (season, episode)
);

CREATE TABLE lines (
  id           int PRIMARY KEY,            -- original script order from the dataset
  season       int  NOT NULL,
  episode      int  NOT NULL,
  scene        int  NOT NULL,              -- aired scene order within the episode: 1..N, no gaps
  speaker      text NOT NULL,              -- cleaned name
  text         text NOT NULL,              -- single source of truth: dialogue with [directions] in place
  dialogue     text GENERATED ALWAYS AS (
                 btrim(regexp_replace(regexp_replace(text, '\[[^\]]*\]', ' ', 'g'), '\s+', ' ', 'g'))
               ) STORED,                   -- speech only; empty for direction-only lines
  FOREIGN KEY (season, episode) REFERENCES episodes
);

-- Flat view for reading and (later) text-to-SQL: adds the episode title and the directions.
CREATE VIEW lines_full AS
SELECT l.id, l.season, l.episode, e.title, l.scene,
       l.speaker, l.text, l.dialogue,
       array_to_string(ARRAY(SELECT m[1] FROM regexp_matches(l.text, '\[([^\]]*)\]', 'g') m), ' | ') AS directions
FROM lines l
JOIN episodes e USING (season, episode);
```

The episode title is stored once, in `episodes`, and never copied onto lines.

Postgres holds clean data only. Cleaning history (`speaker_raw`, `text_raw`, `fix_flags`, `title_inferred`)
stays in `data/processed/*.parquet`; a line is traced back through its `id`.

## Indexing

To be discussed separately. Candidates: `(season, episode, scene)` for scene lookups and citations, `speaker`,
full-text (`tsvector`) and trigram (`pg_trgm`) indexes for keyword and quote search.

## Chunks (Part 2, migration 004)

```sql
chunk_sets (chunk_set_id, name UNIQUE, params jsonb, created_at)    -- one row per chunking strategy
chunks     (chunk_id, chunk_set_id → chunk_sets, season, episode → episodes, position,
            first_line_id → lines, last_line_id → lines, content, token_count)
            UNIQUE (chunk_set_id, season, episode, position)
view chunks_full                                                    -- + title, scene range, speakers, n_lines
```

- **Several strategies side by side:** each chunking strategy is a `chunk_set` with its settings in `params`,
  so strategies can be compared without rebuilding, and every experiment stays reproducible.
- **Source pointer = line range** (`first_line_id..last_line_id`). Exact even when a long scene is split.
  Verified: line ids follow script order and no episode's id range overlaps another's.
- **Neighbours** = same set, same episode, `position ± 1`.
- **`content` is stored** as a snapshot of exactly what was embedded:
  `S3E20 Product Recall | scenes 6-8` + blank line + one `Speaker: text` line per line (directions included).
  Unlike `dialogue`, it is a deliberate record: if a line is re-cleaned later, the stored content shows what the
  existing embedding represents and that it is stale.
- **Speakers and scene range are derived** in `chunks_full`, not stored. A `speakers` column can be added if
  speaker filters during vector search turn out to matter.
- **Embeddings are not on `chunks`.** Part 3 compares several embedding models (different vector sizes), so they go
  in a separate table (see below).
- Keyword search (`tsvector`) on `content` comes with indexing.

## Embeddings (Part 3, migration 005)

```sql
embedding_models (model_id, name UNIQUE, provider, model, dimensions, settings jsonb, created_at)
chunk_embeddings (model_id → embedding_models, chunk_set_id, chunk_id, content_sha256, embedding vector, embedded_at)
                  PRIMARY KEY (model_id, chunk_set_id, chunk_id)
                  FOREIGN KEY (chunk_set_id, chunk_id) → chunks (chunk_set_id, chunk_id) ON DELETE CASCADE
                  INDEX (chunk_set_id, chunk_id)
view stale_embeddings                                  -- vectors whose chunk content changed since embedding
```

- **An experiment = (chunk set × model).** `chunk_set_id` is on `chunk_embeddings` so one experiment's vectors are
  read straight from the primary-key index, and a future HNSW index can be scoped to one experiment. The
  two-column foreign key guarantees the chunk really belongs to that set, so the copy can't drift.
- **Model first in the primary key**: searches filter by model (and chunk set). The extra index on
  `(chunk_set_id, chunk_id)` keeps cascade deletes fast when a chunk set is rebuilt.
- **`embedding_models.name` includes the dimension** (`voyage-4-large@1024`): the same model at another size gives
  incompatible vectors. `settings` records everything else that changes the vectors.
- **`embedding vector` has no fixed size**, so models of different dimensions share one table. The embedding
  script checks each vector's size against `embedding_models.dimensions`.
- **`content_sha256`** = SHA-256 of the UTF-8 content that was embedded; `stale_embeddings` lists mismatches.
- **No vector index yet**: exact search over ~4,700 vectors takes milliseconds and has perfect recall. Later: one
  partial HNSW index per experiment, `embedding::vector(N) ... WHERE model_id = X AND chunk_set_id = Y`.
- Question embeddings are computed per question and not stored.

## Later layers (migrations 006-017)

Beyond the transcript, chunk and embedding tables above: the question log (`qa_runs`, `qa_answers`, `qa_feedback`,
`qa_reviews`, migrations 006-011), the pipeline registry (`pipeline_versions`), the raw graph extraction
(`extraction_runs`, `episode_extractions`, 012), and the graph itself with its views (013-016). The graph is described in
`docs/graph-schema.md`; the whole picture is in `docs/architecture.md` section 5.

## Settled
- Speaker is plain text (no speakers table until Phase 3 needs one).
- `directions` is derived in the `lines_full` view.
