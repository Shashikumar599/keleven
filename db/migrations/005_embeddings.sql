-- Embeddings: one vector per chunk per embedding model. Design and reasoning: docs/schema.md
-- An experiment is (chunk set x model); several can live side by side without overwriting each other.

CREATE TABLE IF NOT EXISTS embedding_models (
  model_id    int  PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name        text NOT NULL UNIQUE,        -- e.g. 'voyage-4-large@1024'
  provider    text NOT NULL,               -- e.g. 'voyage (mongodb atlas)'
  model       text NOT NULL,               -- the provider's model id, e.g. 'voyage-4-large'
  dimensions  int  NOT NULL CHECK (dimensions > 0),
  settings    jsonb NOT NULL DEFAULT '{}', -- everything else that changes the vectors (input_type, dtype, ...)
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Target for the two-column foreign key below (chunk_id alone is already unique).
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_chunk_set_id_chunk_id_key;
ALTER TABLE chunks ADD CONSTRAINT chunks_chunk_set_id_chunk_id_key UNIQUE (chunk_set_id, chunk_id);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  model_id        int    NOT NULL REFERENCES embedding_models ON DELETE CASCADE,
  chunk_set_id    int    NOT NULL,
  chunk_id        int    NOT NULL,
  content_sha256  text   NOT NULL,         -- hash of the exact chunks.content that was embedded
  embedding       vector NOT NULL,         -- no fixed size: different models have different dimensions
  embedded_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, chunk_set_id, chunk_id),        -- one experiment's rows sit together in the index
  FOREIGN KEY (chunk_set_id, chunk_id)                   -- the chunk must belong to the stated chunk set
    REFERENCES chunks (chunk_set_id, chunk_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chunk_embeddings_chunk_idx
  ON chunk_embeddings (chunk_set_id, chunk_id);          -- fast cascade deletes when a chunk set is rebuilt

-- Embeddings whose chunk content has changed since they were computed (should be empty).
CREATE OR REPLACE VIEW stale_embeddings AS
SELECT e.chunk_set_id, e.chunk_id, m.name AS model
FROM chunk_embeddings e
JOIN chunks c USING (chunk_set_id, chunk_id)
JOIN embedding_models m USING (model_id)
WHERE e.content_sha256 <> encode(sha256(convert_to(c.content, 'UTF8')), 'hex');

-- No vector index yet: at ~4,700 chunks an exact scan of one experiment's rows takes milliseconds.
-- An HNSW index per experiment comes with the indexing discussion: a partial expression index on
-- embedding::vector(N) WHERE model_id = X AND chunk_set_id = Y. Keeping the filter inside the index means
-- approximate search never returns other experiments' rows and then discards them.
