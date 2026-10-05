-- v2 gains the enhancer: one fast LLM call before retrieval that rewrites the question for search and may write
-- one SQL query over the transcript tables. Its output is logged per run in qa_runs.plan.
-- Design: findings/decisions.md (2026-10-05, "enhancer"). Prompt: generation/prompts/enhance_v1.md.

-- What the enhancer produced and what its SQL returned; null for v1 runs.
--   {"search_text", "sql", "assumptions",
--    "sql_result": {"columns", "rows", "truncated", "error", "retried", "ms"},
--    "enhancer": {"model_version", "usage", "latency_ms"}}
ALTER TABLE qa_runs ADD COLUMN IF NOT EXISTS plan jsonb;

-- v2 = hybrid search + enhancer + SQL. No run was logged as v2 before this, so redefining it is safe.
UPDATE pipeline_versions SET
  description = 'Enhancer (question rewrite + optional SQL), hybrid retrieval (vector + BM25, RRF), SQL scenes as '
                'extra passages; three answers from Gemini Flash',
  config = jsonb_set(config, '{enhancer}', '{"prompt": "enhance_v1.md", "thinking_level": "low",
      "max_output_tokens": 1024, "outputs": ["search_text", "sql", "assumptions"],
      "on_failure": "request fails",
      "sql": {"role": "office_app (read-only, 5 s timeout)", "max_rows": 50, "max_cell_chars": 300,
              "retry_on_error": 1, "on_failure": "answer from search, error logged",
              "scene_rows_to_passages": 4}}')
WHERE version = 'v2' AND NOT EXISTS (SELECT 1 FROM qa_runs WHERE version = 'v2');
