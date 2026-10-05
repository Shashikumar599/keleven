# Office RAG: A Research Project on Retrieval Strategies

## What this project is

A personal research project to learn Retrieval-Augmented Generation (RAG) by building it step by step over the complete transcripts of *The Office (US)*. The system answers questions and generates quizzes, grounded in exact scenes with speaker and episode citations.

This is run as **research, not just a build**. Each retrieval technique is added in its own phase, measured against a question set, and its findings are documented before moving on. The goal is to understand *why* each component exists by seeing where the previous version fails.

## Research questions

1. Where does an LLM's own memory (no tools) fail on detailed questions about The Office?
2. Does general web search fix those failures, or does it have its own blind spots?
3. How much does a domain-specific RAG system over the actual transcripts improve accuracy, and on which question types?
4. What does each retrieval method (vector, keyword, SQL, graph) contribute, and what does it cost in complexity and latency?

## Approach: data first, questions later

The dataset and the question set are **not fixed yet**. Both are decided as part of the research:

1. Start with the data: explore candidate datasets, choose one (or a combination), clean it and load it.
2. Build Phase 1 (basic RAG).
3. Use Phase 1 exploratorily: ask it a variety of questions, note what works and what fails.
4. Use those observations to design the evaluation question set.
5. Run the comparative analysis: Claude without tools vs Claude with web search vs the Phase 1 system.
6. From then on, every new phase is evaluated against the same question set.

## Data (to be decided in Phase 0)

Candidate sources to evaluate:

- Kaggle "The Office (US) - Complete Dialogue/Transcript" (nasirkhalid24): season, episode, title, scene, speaker, line
- Hugging Face `jxm/the_office_lines`: season, episode, scene, speaker, line, deleted-scene flag
- `schrute`: no scene numbers, but has director, writer, IMDb rating, air date, stage directions

Compare them on completeness, scene information, metadata and cleanliness, then record the choice and reasoning in `findings/phase-0.md`.

Notes:
- All sources are fan-transcribed. Ingestion must normalize speaker names and clean artifacts.
- Transcripts are copyrighted. Keep raw data out of version control (`data/raw/` is gitignored) and do not publish full transcripts.

## Phases

Each phase ends with a findings document. Do not start the next phase until the current one's findings are written.

| Phase | What gets built | What we learn |
|---|---|---|
| 0. Data | Explore and compare datasets, choose one, clean, normalize, load into Postgres | Which dataset to use and its quality issues |
| 1. Vector + keyword RAG | Scene-level chunking with metadata, embeddings, hybrid search, answers with citations | How basic RAG behaves; exploratory questions reveal its strengths and failures |
| 1b. Question set + baselines | Design the evaluation question set from Phase 1 observations; run Claude (no tools), Claude + web search, and Phase 1 | First comparative analysis: where transcript retrieval helps and where it doesn't |
| 2. SQL + router | Lines table, text-to-SQL, LLM router choosing vector vs SQL vs both | Whether SQL fixes counting and aggregate questions |
| 3. Graph (optional) | Character and relationship graph as a third retrieval path | Whether it helps multi-hop and relationship questions. Build only if Phase 2 findings show these still fail |
| 4. Quiz generation | Quiz questions from retrieved scenes, every answer verified against its cited source | Whether verification catches hallucinated quiz answers |

## Evaluation dataset (to be designed in Phase 1b)

The question set is built after Phase 1, based on what exploratory questioning shows. Gold answers are written and checked by a human against the transcripts. Claude Code may help draft candidates (for example by running SQL), but must not mark an answer as verified.

Draft format for `eval/questions.jsonl` (may change once the set is designed):

```json
{
  "id": "q001",
  "category": "<category>",
  "question": "<question text>",
  "gold_answer": "<verified answer>",
  "gold_citations": [{"season": 0, "episode": 0, "scene": 0}],
  "difficulty": "easy | medium | hard",
  "split": "dev | test"
}
```

Starting ideas for categories (to be refined): famous moments, exact quotes, who said it, episode lookup, counting, relationships / multi-hop.

Once the set exists:
- `dev` split is used while building and tuning; `test` split is only run at the end of each phase and never used for tuning.
- Metrics: answer accuracy (per category and overall), retrieval recall@k, citation correctness, latency and cost per question.

## Documenting findings

After each phase, write `findings/phase-N.md` using this template:

```markdown
# Phase N: <name>
## What was built
## Setup (models, chunk size, k, parameters)
## Results (once the question set exists: system x category accuracy, vs previous phases)
## Where it worked
## Where it failed (with 3-5 concrete failing examples)
## What surprised us
## Decision: what the next phase should address
```

During Phase 1 exploration, log every question asked and how the system did in `findings/exploration-log.md`. These observations feed the question set design.

Keep `findings/experiment-log.md` with a short dated entry for every eval run: what changed, the scores, and one line of interpretation. Raw run outputs go in `eval/runs/<date>-<label>.jsonl`.

## Suggested stack (defaults, open to change)

- Python
- Postgres with pgvector (one database for tables, embeddings, and later graph tables)
- An LLM for generation, routing and baselines: Gemini Flash (free tier, pinned version) in v1, behind a provider-swappable interface; the same model for all baselines
- An embedding model chosen and compared in Phase 1

## Repo layout

```
data/raw/            # downloaded transcripts (gitignored)
data/processed/      # cleaned tables
ingest/              # cleaning, chunking, embedding
retrieval/           # vector, keyword, sql, graph, router
generation/          # answer and quiz generation, verification
eval/                # questions.jsonl, harness, runs/
findings/            # phase-N.md, exploration-log.md, experiment-log.md
```

## Working agreements for Claude Code

- Stay within the current phase. Suggest future-phase ideas in the findings doc instead of building them.
- Don't fix the dataset or question set early; those decisions are made in Phase 0 and Phase 1b.
- Never edit gold answers in `eval/questions.jsonl` without asking.
- Never tune anything on the `test` split.
- Every eval run gets an entry in `findings/experiment-log.md`.
- When something fails, record concrete examples. Failures are findings, not just bugs.
- Explain retrieval and RAG concepts as they come up. This project is also for learning.