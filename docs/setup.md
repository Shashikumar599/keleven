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

Check against the original machine: 57,973 lines, 4,658 chunks (chunk set `pack_300t_3s_80min`), all embedded with
`voyage-4-large@1024`. Then `.venv/bin/uvicorn app.server:app --port 8000` (see commands.md).

## What does not carry over
- The question history, feedback, reviews and stored answers (tables `qa_runs`, `qa_reviews`, ...) are database rows.
  The eval results themselves are in git (`eval/runs/*.jsonl`, `eval/grading/`), but the app's History view starts empty
  and memory answers reused across versions are not in the new database until an eval run is imported or rerun.
- Embeddings are recomputed (same model, near-identical vectors; query embeddings already vary slightly run to run).
