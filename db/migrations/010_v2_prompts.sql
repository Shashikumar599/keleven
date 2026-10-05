-- v2 answers with its own prompt files (rag_v2.md, hybrid_v2.md = the v1 prompts + how the evidence was found:
-- search text, SQL result block, [SQL] citations). The v1 files stay exactly as the v1 baseline used them.
UPDATE pipeline_versions
SET config = jsonb_set(config, '{prompts}', '{"rag": "rag_v2.md", "llm": "memory_v1.md", "hybrid": "hybrid_v2.md"}')
WHERE version = 'v2';
