-- Registers pipeline v3: v2 plus a graph query written by the enhancer and run over the graph views (migrations 013 to 016).
-- v1 and v2 rows are not touched. Code: retrieval/hybrid_v3.py, retrieval/graph.py, generation/enhance_v3.py, generation/answer_v3.py.
INSERT INTO pipeline_versions (version, description, config) VALUES (
  'v3',
  'Enhancer (question rewrite + optional SQL + optional graph SQL), hybrid retrieval (vector + BM25, RRF), SQL scenes as extra '
  'passages, graph rows with their transcript lines; answers from Gemini Flash',
  '{"chunk_set": "pack_300t_3s_80min",
    "embedding_model": "voyage-4-large@1024",
    "retrieval": {"method": "hybrid", "k": 8, "expand": 1, "filters": null,
                  "vector": {"metric": "cosine", "depth": 50},
                  "keyword": {"engine": "bm25s 0.3.12", "k1": 1.5, "b": 0.75, "depth": 50},
                  "fusion": {"method": "rrf", "rrf_k": 60}},
    "enhancer": {"prompt": "enhance_v3.md", "thinking_level": "low", "max_output_tokens": 1024,
                 "outputs": ["search_text", "sql", "assumptions", "graph_sql"],
                 "graph_sql": {"views": ["graph_timeline_now", "graph_relations_now", "graph_events_now", "graph_characters_now"],
                               "role": "office_app (read-only, 5 s timeout)", "max_rows": 50, "lines_per_row": 2,
                               "retry_on_error": 1, "on_failure": "answer from search, error logged",
                               "graph_build": "v3-graph-001"}},
    "prompts": {"rag": "rag_v3.md", "llm": "memory_v1.md", "hybrid": "hybrid_v3.md"},
    "llm": {"provider": "gemini", "model": "gemini-3.8-flash", "temperature": "model default",
            "thinking": "model default", "max_output_tokens": 16384}}'
) ON CONFLICT (version) DO NOTHING;
