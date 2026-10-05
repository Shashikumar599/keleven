-- Answer reuse and comparison (dev mode). Design: findings/decisions.md (2026-10-05, "Dev-mode answer comparison").

-- A memory-only answer doesn't depend on the pipeline version, so a question asked again reuses the stored one
-- instead of calling the LLM. The new run keeps a copy of it and records where it came from.
ALTER TABLE qa_answers ADD COLUMN IF NOT EXISTS reused_from_run bigint REFERENCES qa_runs (run_id);

-- "The same question" = same text after trimming, ignoring case and repeated spaces. Used to find stored answers.
CREATE INDEX IF NOT EXISTS qa_runs_question_norm_idx
  ON qa_runs ((lower(regexp_replace(btrim(question), '\s+', ' ', 'g'))));
