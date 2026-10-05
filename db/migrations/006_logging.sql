-- Logging: every question asked (web, CLI, eval), its three answers, and reviews of them.
-- Design and reasoning: findings/decisions.md ("Logging and evaluation design").
-- Prompts are not stored: they are rebuilt from the pipeline version, the chunk ids sent and the prompt file
-- (whose hash is recorded per answer).

-- What each pipeline version is. Registered by the admin; the app only reads it.
CREATE TABLE IF NOT EXISTS pipeline_versions (
  version      text PRIMARY KEY,               -- 'v1', 'v2', ...
  description  text NOT NULL,
  config       jsonb NOT NULL,                 -- everything that defines the version
  created_at   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO pipeline_versions (version, description, config) VALUES (
  'v1',
  'Cosine-only vector retrieval with neighbour expansion; three answers (RAG, LLM, LLM + RAG) from Gemini Flash',
  '{"chunk_set": "pack_300t_3s_80min",
    "embedding_model": "voyage-4-large@1024",
    "retrieval": {"method": "cosine", "k": 8, "expand": 1, "filters": null, "keyword_search": false},
    "prompts": {"rag": "rag_v1.md", "llm": "memory_v1.md", "hybrid": "hybrid_v1.md"},
    "llm": {"provider": "gemini", "model": "gemini-3.8-flash", "temperature": "model default",
            "thinking": "model default"}}'
) ON CONFLICT (version) DO NOTHING;

-- One row per question asked.
CREATE TABLE IF NOT EXISTS qa_runs (
  run_id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  asked_at        timestamptz NOT NULL DEFAULT now(),
  source          text NOT NULL CHECK (source IN ('web', 'cli', 'eval')),
  mode            text NOT NULL DEFAULT 'dev' CHECK (mode IN ('user', 'dev')),   -- display mode when asked; all three answers are always computed
  eval_label      text,                        -- eval runs only, e.g. '2026-10-20-v1-dev'
  question_id     text,                        -- eval runs only: id from eval/questions.jsonl
  question        text NOT NULL,
  version         text NOT NULL REFERENCES pipeline_versions,
  -- what retrieval actually did (may differ from the version defaults, e.g. k changed in the web page)
  chunk_set_id    int NOT NULL REFERENCES chunk_sets,          -- RESTRICT: a chunk set with logged runs can't be deleted
  model_id        int NOT NULL REFERENCES embedding_models,    -- the embedding model
  k               int NOT NULL,
  expand          int NOT NULL,
  hits            jsonb NOT NULL,              -- [{"rank": 1, "chunk_id": 123, "distance": 0.466}, ...]
  sent_chunk_ids  int[] NOT NULL,              -- the chunks sent to the LLM, in prompt order
  query_tokens    int,
  retrieval_ms    jsonb                        -- {"connect": .., "embed": .., "search": .., "expand": .., "total": ..}
);
CREATE INDEX IF NOT EXISTS qa_runs_asked_at_idx ON qa_runs (asked_at DESC);   -- History view: newest first
CREATE INDEX IF NOT EXISTS qa_runs_version_idx ON qa_runs (version);

-- One row per system (rag / llm / hybrid) per run.
CREATE TABLE IF NOT EXISTS qa_answers (
  answer_id       bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  run_id          bigint NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
  system          text NOT NULL CHECK (system IN ('rag', 'llm', 'hybrid')),
  prompt_file     text NOT NULL,
  prompt_sha256   text NOT NULL,               -- hash of the prompt file used, so an edited prompt is noticed
  provider        text,
  model           text,                        -- what we asked for
  model_version   text,                        -- what answered
  output          jsonb,                       -- the structured answer (evidence, answer, ...)
  raw_text        text,                        -- only when the output couldn't be parsed
  error           text,                        -- only when the call failed
  citation_check  jsonb,
  usage           jsonb,                       -- input / output / thinking tokens
  latency_ms      int,
  attempts        int,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, system)
);

-- Reviews of answers, from two kinds of reviewer:
--   reviewer = 'me'                 the project owner, marking answers by hand in the web app's History view
--   reviewer = 'claude:<model id>'  the Claude Code evaluation skill, writing an automated verdict
-- system = 'rag' / 'llm' / 'hybrid' reviews one answer; system NULL reviews the whole run (comparing the three).
CREATE TABLE IF NOT EXISTS qa_reviews (
  review_id     bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  run_id        bigint NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
  system        text CHECK (system IN ('rag', 'llm', 'hybrid')),
  reviewer      text NOT NULL,                 -- 'me', or 'claude:<model id>'
  verdict       text CHECK (verdict IN ('correct', 'partial', 'wrong', 'refused')),
  grounded      text CHECK (grounded IN ('yes', 'partly', 'no', 'n/a')),
  failure_type  text,                          -- e.g. retrieval_miss, generation_error, memory_leak, over_refusal
  notes         text,
  details       jsonb,                         -- anything else the reviewer reports
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (run_id, system, reviewer)   -- one review per answer per reviewer
);

-- Feedback from whoever uses the web app: quick, optional reactions (separate from careful reviews above).
--   kind 'satisfied'   user mode: was the LLM + RAG answer satisfactory? (yes / no)
--   kind 'preference'  dev mode: which is better, RAG or LLM? (LLM + RAG isn't rated: it would usually win)
-- Any combination is possible: none, either, or both. Clicking again updates the row.
CREATE TABLE IF NOT EXISTS qa_feedback (
  feedback_id  bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  run_id       bigint NOT NULL REFERENCES qa_runs ON DELETE CASCADE,
  kind         text NOT NULL CHECK (kind IN ('satisfied', 'preference')),
  satisfied    boolean,
  preferred    text CHECK (preferred IN ('rag', 'llm', 'both_good', 'both_bad')),
  comment      text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, kind),
  CHECK ((kind = 'satisfied'  AND satisfied IS NOT NULL AND preferred IS NULL) OR
         (kind = 'preference' AND preferred IS NOT NULL AND satisfied IS NULL))
);

-- The app (office_app) may write logs, and nothing else. It already has SELECT on everything.
-- Note: office_app sessions default to read-only transactions, so logging code must open a READ WRITE
-- transaction explicitly; the grants below are what actually limits it.
GRANT INSERT, UPDATE ON qa_runs, qa_answers, qa_reviews, qa_feedback TO office_app;
GRANT USAGE ON SEQUENCE qa_runs_run_id_seq, qa_answers_answer_id_seq, qa_reviews_review_id_seq,
                        qa_feedback_feedback_id_seq TO office_app;
