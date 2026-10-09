# Commands to run

Run everything from the repo root. Load the environment first in every new shell:

```bash
cd /Users/shashikumar/personal/office-rag
set -a; source .env; set +a
```

Steps marked **[LLM]** call Gemini or Voyage and cost tokens: ask before running them (standing rule).
Steps marked **[writes DB]** use the admin role.

New machine: see setup.md (scripts/bootstrap.sh).

## 1. Database

```bash
docker compose -f docker-compose.db.yml up -d          # start Postgres 17 + pgvector on localhost:5433
docker compose -f docker-compose.db.yml ps             # check it is healthy
docker compose -f docker-compose.db.yml down           # stop (data stays in the pgdata volume)
```

Migrations are in `db/migrations/001` to `011`, applied in order (001 extensions, 002 app role, 003 transcript
schema, 004 chunks, 005 embeddings, 006 logging, 007 feedback, 008 pipeline v2, 009 plan, 010 v2 prompts, 011 answer
reuse). They are plain SQL; apply a new one with the admin role (psql or `common.db.connect("admin")`).

## 2. Data pipeline (Phase 0 and chunking / embedding)

```bash
python ingest/clean.py                         # clean and normalise the raw transcripts      (no LLM)
python ingest/load.py                          # load into Postgres                           [writes DB]
python ingest/chunk.py --dry-run               # build chunks, print a summary, write nothing
python ingest/chunk.py                         # store a new chunk set                        [writes DB]
python ingest/embed.py --dry-run               # show what would be embedded
python ingest/embed.py --limit 20              # try 20 chunks first                          [LLM: Voyage]
python ingest/embed.py                         # embed everything missing or stale            [LLM: Voyage] [writes DB]
```

## 3. Ask one question

```bash
python ask.py "why did andy break up with angela"                    # retrieval only (v2 default), shows what would be sent
python ask.py "why did andy break up with angela" --answer           # + three answers: rag, llm, hybrid   [LLM]
python ask.py "..." --answer --systems rag llm                       # only some systems                   [LLM]
python ask.py "..." --answer --no-log                                # do not log the question
python ask.py "..." --k 5 --expand 0 --full                          # other k / neighbours, full passages
```

## 4. Web app

```bash
.venv/bin/uvicorn app.server:app --port 8000      # then open http://localhost:8000
```

`ADMIN_PASSWORD` (in `.env`) unlocks dev mode: version picker, retrieval settings, reviews, feedback.

## 5. Run the question set (eval)

One run = one label. Retrieval first, then one Gemini batch job.

```bash
python -m eval.run prepare --label <label> --version v2     # retrieval for all questions (v2 also calls the enhancer)  [LLM: Voyage + Gemini]
python -m eval.run plan    --label <label>                  # what would be submitted: counts, size, token estimate
python -m eval.run submit  --label <label>                  # build prompts, submit ONE batch job                      [LLM]
python -m eval.run status  --label <label>                  # job state
python -m eval.run collect --label <label>                  # fetch answers, check citations, log, write eval/runs/<label>.jsonl
python -m eval.run rerun   --label <label>                  # re-answer failed answers as single online calls          [LLM]
python -m eval.run online  --label <label> --only q017,q023 # answer questions missing from a run, online              [LLM]
```

Existing runs: `2026-10-04-v1-baseline` (v1), `2026-10-05-v2` (v2). Options: `--only qNNN,...`, `--k`, `--expand`,
`--answers`, `--force`. Memory answers are reused across versions when stored.

## 6. Grading (evaluate-answers skill, council)

References (built once, shared by every version):

```bash
python -m eval.grade ref-question --question q017           # what the reference builder sees
python -m eval.grade ref-save --file ref.json               # store eval/grading/references/q017.json
python -m eval.grade ref-review                             # write REVIEW.md for the owner
```

Grading one run (coordinator creates the set; graders only get packets):

```bash
python -m eval.grade init   --label <label>                              # new random set name, writes key.json + config.json
python -m eval.grade packet --set <set> --question q017                  # the run's answers, blinded A / B / C
python -m eval.grade note-save --set <set> --question q017 --lens fact --file note.md      # lens: fact | faithfulness | reader
python -m eval.grade notes  --set <set> --question q017                  # the three notes, for the chair
python -m eval.grade save   --set <set> --file verdicts.json             # chair verdict ("method": "council")
python -m eval.grade status --set <set>                                  # which questions are still ungraded
```

Council members and chairs are Claude agents (subscription, not API): one agent per lens per batch of about 10
questions, then a chair per batch. One simple save command per file (no shell loops or functions). Pin one model per
role and record it. Current rubrics: `.claude/skills/evaluate-answers/rubrics.md` (rubrics-v2).

Compare versions:

```bash
python -m eval.grade summary --sets s-d99104,s-bcc971       # v1 (s-d99104) and v2 (s-bcc971): mean /10 per version x type x category
```

## 7. Git

```bash
git status
git add -A && git commit -m "<short message>"
git push -u origin main                                     # remote: git@github-personal:Shashikumar599/keleven.git
```

## Where things are

| What | Where |
|---|---|
| Question set | `eval/questions.jsonl` (80 questions) |
| Run outputs | `eval/runs/<label>.jsonl`, `eval/runs/<label>/` |
| References | `eval/grading/references/qNNN.json`, `REVIEW.md` |
| Grading sets | `eval/grading/<set>/` (key.json, notes/, verdicts/) |
| Findings | `findings/` (decisions.md, experiment-log.md, v1-v2-grading-analysis.md) |
| Prompts (frozen per version) | `generation/prompts/` |
| v3 draft design | `docs/graph-design.md` |
