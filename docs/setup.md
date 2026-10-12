# Set up on a new machine

Needs Docker, Python 3.12 and the Voyage and Gemini keys. The source transcripts are in `data/raw/`; everything else is
rebuilt, nothing from the database is stored in git.

```bash
git clone git@github-personal:Shashikumar599/keleven.git office-rag && cd office-rag
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env            # fill in passwords and the two API keys
scripts/bootstrap.sh            # database, migrations, clean, load, chunk (no API calls); a few minutes
```

Then the one step that costs tokens (Voyage embeddings for 4,658 chunks), run by hand:

```bash
set -a; source .env; set +a
python ingest/embed.py --dry-run
python ingest/embed.py
```

Link the evaluation skill for Claude Code (local only: `.claude/` is not in git, the skill lives in `eval/skills/`):

```bash
mkdir -p .claude/skills && ln -sfn ../../eval/skills/evaluate-answers .claude/skills/evaluate-answers
```

Check against the original machine: 57,973 lines, 4,658 chunks (chunk set `pack_300t_3s_80min`), all embedded with
`voyage-4-large@1024`. Then `.venv/bin/uvicorn app.server:app --port 8000` (see commands.md).

## The graph (v3)

The migrations create the graph tables empty. The extracted facts are not in git, so a new machine gets them in one of two ways:
- **Restore a dump** from the original machine (about 26 MB, no API calls): `bash deploy/export_data.sh` there, then
  `TARGET_URL=... bash deploy/import_data.sh` here (see `docs/hosting.md` for the details; the target needs the migrations applied and empty tables).
- **Rebuild it** (about 6M input and 1M output Gemini tokens, 20 minutes; the extraction is not exactly reproducible):

```bash
python -m graph.run_extraction --label v3-extract-001 --all --run          # extraction + review, stored in Postgres
python -m graph.link_certain --label v3-extract-001                         # character linking, writes graph/out/*.json
python -m graph.link_tiers --label v3-extract-001
python -m graph.build_graph --label v3-extract-001 --build v3-graph-001 --run
```

## What does not carry over
- The question history, feedback, reviews and stored answers (tables `qa_runs`, `qa_reviews`, ...) are database rows.
  The eval results themselves are in git (`eval/runs/*.jsonl`, `eval/grading/`), but the app's History view starts empty
  and memory answers reused across versions are not in the new database until an eval run is imported or rerun.
- Embeddings are recomputed (same model, near-identical vectors; query embeddings already vary slightly run to run).
- The graph rows and the extraction JSON (see above); the grading sets and run files are in git.
