-- Pipeline version v2: hybrid retrieval (vector + BM25 keyword search, merged with reciprocal rank fusion).
-- Design and measurements: findings/decisions.md and findings/experiment-log.md (2026-10-04 / 2026-10-05).
-- The BM25 index is built in memory from the chunks table (retrieval/keyword.py); nothing new is stored.

INSERT INTO pipeline_versions (version, description, config) VALUES (
  'v2',
  'Hybrid retrieval: vector + BM25 keyword search fused by RRF, neighbour expansion; three answers from Gemini Flash',
  '{"chunk_set": "pack_300t_3s_80min",
    "embedding_model": "voyage-4-large@1024",
    "retrieval": {"method": "hybrid", "k": 8, "expand": 1, "filters": null,
                  "vector": {"metric": "cosine", "depth": 50},
                  "keyword": {"engine": "bm25s 0.3.12", "k1": 1.5, "b": 0.75, "depth": 50,
                              "tokenizer": "lowercase, accents stripped, all words kept (no stop words), no stemming"},
                  "fusion": {"method": "rrf", "rrf_k": 60}},
    "prompts": {"rag": "rag_v1.md", "llm": "memory_v1.md", "hybrid": "hybrid_v1.md"},
    "llm": {"provider": "gemini", "model": "gemini-3.8-flash", "temperature": "model default",
            "thinking": "model default", "max_output_tokens": 16384}}'
) ON CONFLICT (version) DO NOTHING;
