-- Graph extraction storage (v3), layer 1 only: the JSON of each pass, per episode, exactly as produced.
-- The graph tables (characters, events, relations, links) are NOT here: they are designed afterwards, on top of these
-- rows, and can be rebuilt from them without calling the LLM again. Design: docs/graph-design.md.
--
-- Stages stored per episode:
--   raw        what the first pass (extract_v1.md) returned, as text parsed to JSON
--   validated  after graph/validate.py (rows dropped or flagged); issues holds the validator's findings
--   review     the reviewer's corrections (review_v1.md) and what was applied or skipped
--   reviewed   the corrected extraction after the review, validated again (the version used downstream)

CREATE TABLE IF NOT EXISTS extraction_runs (
  run_id            serial      PRIMARY KEY,
  label             text        NOT NULL UNIQUE,           -- e.g. 2026-10-10-pilot
  model             text        NOT NULL,                  -- the model that answered (gemini-3.8-flash)
  extract_prompt    text        NOT NULL,                  -- file name and first 8 chars of its sha256
  review_prompt     text        NOT NULL,
  extract_schema    text        NOT NULL,
  review_schema     text        NOT NULL,
  params            jsonb       NOT NULL DEFAULT '{}',     -- thinking level, max output tokens, concurrency, ...
  note              text,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS episode_extractions (
  run_id      int         NOT NULL REFERENCES extraction_runs (run_id) ON DELETE CASCADE,
  season      int         NOT NULL,
  episode     int         NOT NULL,
  stage       text        NOT NULL CHECK (stage IN ('raw', 'validated', 'review', 'reviewed')),
  status      text        NOT NULL CHECK (status IN ('ok', 'flagged', 'failed')),
  payload     jsonb,                                       -- the JSON of this stage; null when the call failed
  issues      jsonb       NOT NULL DEFAULT '[]',           -- validator findings (validated and reviewed stages)
  usage       jsonb       NOT NULL DEFAULT '{}',           -- input / output / thinking tokens, latency_ms, attempts
  error       text,                                        -- the error message when status = failed
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, season, episode, stage),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode)
);

CREATE INDEX IF NOT EXISTS episode_extractions_status_idx ON episode_extractions (run_id, stage, status);
