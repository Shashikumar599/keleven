# Keleven: a measured study of RAG over *The Office (US)*

## Intention
Learn retrieval-augmented generation by building it step by step and measuring every step, not just assembling a demo. The
question: where does a language model's own memory fail on detailed questions, and what does each retrieval method (vector,
keyword, SQL, graph) add, at what cost in complexity? The transcripts of a TV show stand in for private company documents:
the model half-remembers them, so the benefit of retrieval is visible, and the collection is large enough to need real search.

## What was built
- **Data:** 186 episodes, 57,973 lines, cleaned and loaded into Postgres (repaired encoding, normalised speaker names, scenes renumbered), cut into 4,658 scene-based chunks.
- **v1, vector search:** the 8 chunks closest in meaning to the question, answered with scene citations.
- **v2, hybrid + SQL:** a question enhancer, keyword search merged with vector search (reciprocal rank fusion), and model-written read-only SQL for counts.
- **v3, graph:** facts (relationships, events, characters) extracted from every episode, linked across episodes only when the data proves it, and queried through a model-written read-only SQL query; each fact carries the transcript lines it came from.
- **Evaluation:** 92 questions with transcript-only reference answers; three answer types per version (memory only, transcripts only, transcripts plus labelled memory); a council of model graders (fact, faithfulness and reader lenses, then a chair); memory answers reused as a control; both versions regraded together in one blind session.
- **App and hosting:** a web app (user and dev views, citation chips that open the cited scene) running on AWS: one EC2 instance, Docker Compose (app + Postgres/pgvector), CloudFront for HTTPS, a site password, per-IP and daily limits, excerpt-only sources.

## Results
| Step | Transcript-only score (0-10) | What changed |
|---|---|---|
| v1 | 7.62 | counts failed (2.3), rare phrases diluted in long chunks |
| v2 | 8.65 | SQL made counts exact (9.7); keyword search found exact phrases; right scene reached the model for 53 of 55 known questions (v1: 44) |
| v3 | 8.88 on the original 80; 5.6 to 7.6 on ten new graph-shaped questions | list, history and relationship questions improved; questions the graph does not touch were unchanged |

The memory-only control (about 7) did not move, so grading noise could be separated from real gains.

## Technologies
Python and FastAPI; Postgres 17 with pgvector (one database for text, vectors and the graph); Voyage `voyage-4-large` embeddings; Gemini Flash for the
enhancer, answers and graph extraction; bm25s keyword search; plain JavaScript front end; Docker, AWS EC2 and CloudFront.

## Decisions and why
- **Measure before adding.** SQL and the graph were built only after specific questions failed without them.
- **Scenes as chunks** (up to 300 tokens, 3 scenes), because talking-head lines make no sense without the scene around them.
- **Hybrid search,** because vector and keyword search failed on different questions (44 and 46 of 55 alone, 49 together).
- **Exact vector search, no index,** at 4,658 vectors: milliseconds, perfect recall, nothing to tune.
- **Never merge uncertain characters.** The graph keeps weak links as "possible" because a wrong merge silently corrupts every answer.
- **Honest grading:** a memory control, independent references, and one blind session for both versions after measuring that separate sessions drifted by up to 4 points on identical text.
- **Free-tier choices, stated plainly:** Gemini Flash's free tier and Voyage's free allowance made the study affordable; hosting stays inside AWS's free tier.
- **Safe public access:** read-only roles for model-written SQL, rate limits, a database-backed daily cap, and transcripts shown only as excerpts.

## Limits
One run and one family of grader; per-answer scores noisy by 1 to 2 points; the graph is incomplete (31 episodes have no relation rows); much of the show is visual and not in the text. No re-ranker, chunk-size sweep or embedding comparison was done. After the study, v3 was changed in place so a matched line brings its scene; the table above measures the earlier v3.
