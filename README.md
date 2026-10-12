# Keleven: a RAG study over The Office (US)

A personal research project that answers questions about *The Office* with citations to exact scenes, built step by step
and **measured at every step**. Three pipeline versions were added one on top of the other and graded against the same
92 questions:

| | What it adds | Mean score /10 (rag, transcripts only) | Mean score /10 (hybrid, transcripts + labelled memory) |
|---|---|---|---|
| v1 | vector search | 7.6 | 8.9 |
| v2 | + question rewrite, keyword search (BM25), SQL | 8.7 | 9.4 |
| v3 | + a graph of relationships and events | 8.9 on the original 80 (graph questions: 6.3 → 7.7) | 9.2 (graph questions: 8.1 → 8.5) |

The v1 → v2 numbers come from separate grading sessions; the v2 → v3 comparison was graded blind in one session. Full
results, failures and caveats: `findings/phase-3.md`. The honest summary: each step fixed what the previous one measurably
got wrong (v2: exact facts and counts; v3: lists, histories and false-premise questions that need many scenes), and none
of them changes questions the step does not touch.

## Where to read

| You want | Read |
|---|---|
| How it all fits together | `docs/architecture.md` |
| What was found, with numbers | `findings/phase-3.md`, `findings/v1-v2-grading-analysis.md` |
| Why each choice was made | `findings/decisions.md`, `findings/experiment-log.md` |
| The graph design and tables | `docs/graph-design.md`, `docs/graph-schema.md` |
| The database schema | `docs/schema.md` |
| Run it on a new machine | `docs/setup.md` |
| Commands for everything | `docs/commands.md` |
| Host it publicly | `docs/hosting.md` |

## Quick start

```
docker compose -f docker-compose.db.yml up -d      # Postgres 17 + pgvector
cp .env.example .env                               # add your keys (Gemini, Voyage), see docs/setup.md
bash scripts/bootstrap.sh                          # tables, transcripts, chunks (embeddings: by hand, see setup)
set -a; source .env; set +a
.venv/bin/uvicorn app.server:app --port 8000       # open http://localhost:8000
python ask.py "who said that's what she said first"        # v1 / v2 from the command line
python ask_v3.py "Whom did Michael date?" --answer         # v3
```

## Repository layout

`ingest/` transcripts to vectors · `retrieval/` search, SQL, graph · `generation/` models, prompts, answer builders ·
`graph/` extraction and graph tables · `eval/` questions, references, runs, grading · `app/` web server and page ·
`db/migrations/` schema (001-017) · `docs/` design · `findings/` decisions and results.

## Notes

- The transcripts are fan-written and copyrighted. `data/raw/` is committed so a new machine can rebuild everything:
  **keep the repository private**, and never show full transcripts on a public page (the hosted demo shows short excerpts only).
- Secrets live in `.env` (git-ignored). `.claude/` is git-ignored; the evaluation skill lives in `eval/skills/` and is linked
  into `.claude/skills/` locally (see `docs/setup.md`).
- Models: Gemini `gemini-3.8-flash` for the enhancer, the answers and the graph extraction; Voyage `voyage-4-large` (1024 dims)
  for embeddings.
