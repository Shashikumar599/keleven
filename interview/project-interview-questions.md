# Interview questions about my RAG project

A project walkthrough: "A study of RAG over *The Office (US)* transcripts: vector search (v1), then hybrid + SQL (v2), then a
relationship graph (v3), each measured against the same question set."

Answers are written in first person so you can say them out loud. Numbers come from `findings/phase-3.md`,
`findings/v1-v2-grading-analysis.md`, `findings/experiment-log.md` and `findings/decisions.md`; re-check them there before an
interview. Part 9 lists the skeptical questions, which are where interviews are won or lost.

Contents: [1 Overview](#1-overview-and-motivation) · [2 Data](#2-data) · [3 Chunking and embeddings](#3-chunking-and-embeddings) ·
[4 v1 and v2](#4-retrieval-v1-to-v2) · [5 Graph v3](#5-the-graph-v3) · [6 Evaluation](#6-evaluation) · [7 Failures](#7-failures-and-lessons) ·
[8 Production](#8-production-and-hosting) · [9 Skeptical questions](#9-skeptical-questions) · [10 Cheat sheet](#10-numbers-cheat-sheet)

---

## 1. Overview and motivation

### Q1. Give me a 60-second overview of the project.
I built a question-answering system over the full transcripts of *The Office*: 186 episodes, about 58,000 lines. It answers with
citations to the exact scene. I ran it as a study rather than a product: three versions, each added on top of the last, all graded
on the same questions. v1 is vector search. v2 adds a question enhancer, keyword search merged with vector search, and SQL for counts.
v3 adds a graph of characters, relationships and events extracted from every episode, queried through a model-written read-only SQL
query. I compared each version on 92 questions with a council of model graders, and I deployed v3 publicly on AWS.

### Q2. Why this dataset, and why a study instead of just building the best system?
Transcripts are a good stand-in for a company's private documents: the model half-remembers the show, which makes the "what does retrieval
add" question visible, and the data is large enough to need real retrieval. Doing it as a study meant that every component had to
earn its place: I only added SQL or a graph after I saw specific questions that the previous version failed on, and I could show the
before and after.

### Q3. What are the research questions you set?
Where does a model's own memory fail on detailed questions? How much does retrieval over the real transcripts improve accuracy, and on
which question types? And what does each method (vector, keyword, SQL, graph) contribute, and what does it cost in complexity and latency?

### Q4. What was your role and what did you personally decide?
I made the design decisions and logged each one with its reason in a decision log (about a thousand lines): dataset choice, chunking,
embedding model, when to add each retrieval method, the grading method, what to publish. I used an AI coding assistant for implementation,
and I reviewed and measured everything it produced. *(Say this plainly. It is true, and interviewers prefer it to a vague "I built it".)*

---

## 2. Data

### Q5. How did you choose and clean the data?
I compared two public copies (Kaggle and Hugging Face). They turned out to be the same fan transcript, so the choice was about
processing: Hugging Face kept stage directions and deleted-scene flags, while Kaggle had better encoding. I used the Hugging Face data
and repaired about 2,200 corrupted characters from Kaggle's copy of the same lines; the other 348 were fixed by context rules. I also
normalised 700+ speaker spellings with a hand-checked mapping, dropped deleted scenes, and renumbered scenes per episode. Every
line keeps its raw text and a flag listing what cleaning changed, so any answer can be traced back.

### Q6. What data-quality problems affected your results?
Fan transcripts are incomplete: some punchlines are simply missing, and much of the show's humour is visual. One question ("I do not miss
him") could not be answered because the words are not in the data. Speaker names needed human judgement (Joan vs Jan, David vs
David Wallace). I recorded these limits rather than hiding them, because they cap the achievable accuracy.

### Q7. Copyright: the transcripts are copyrighted. How do you handle that?
The raw data is never committed or served whole. In the public app, sources appear only as short excerpts (three lines per scene, each
cut to 160 characters), the repository stays private, and the page says that questions are logged.

---

## 3. Chunking and embeddings

### Q8. How did you chunk, and why?
I chunk by whole scenes, packed together up to about 300 tokens and at most 3 scenes, merging anything under 80 tokens into a neighbour and
never crossing an episode. Scenes are short (median about 50 words) and many are one-line talking heads that make no sense without the
scene before them, so a scene is the natural unit. The token cap limits cost, the scene cap limits how many topics one vector has to represent,
and the minimum avoids chunks too tiny to embed. That gave 4,658 chunks.

### Q9. How did you tune chunk size?
Honestly, the values were reasoned starting points rather than tuned by sweep. At retrieval time I also add one neighbouring chunk on each side,
which repairs a story that was cut at a chunk boundary. The evaluation is the safety net: I measured whether the right scene reaches the model
(44 of 55 for v1), not the chunk size in isolation. A proper sweep over chunk sizes is something I would do next.

### Q10. Which embedding model, and why?
Voyage `voyage-4-large` at 1,024 dimensions. The honest reason is practical: it is a strong retrieval model, I had access to it through my MongoDB Atlas key with a large free token
allowance (200M tokens, and embedding the whole corpus used about 1.2M), and a test call worked on the first try. Cost and access are real criteria for a personal project. Its vectors come
back normalised, so cosine and dot product are identical. What I did **not** do is benchmark it against other embedding models, so I would not claim it is the best choice. If I were choosing for
production I would compare two or three candidates on my own question set (recall@k), and weigh price, latency, vector size and language support. Changing the model means re-embedding everything.

### Q11. Why no vector index (HNSW etc.)?
At 4,658 vectors an exact scan takes milliseconds and gives perfect recall, so an approximate index would only add complexity and the risk of silently missing a result. It would also have muddied my
measurements, because I would not know whether a miss came from retrieval or from the index. The schema is ready for one (an index per model and chunk set), and pgvector offers both `ivfflat` and `hnsw`.

An index is a trade: a little recall for a lot of speed. The main families:

| Method | How it works | Costs |
|---|---|---|
| Exact (flat) | Compare the query with every vector | Time grows linearly with the data |
| IVF | Cluster the vectors (k-means); at query time scan only the nearest clusters (`nprobe`) | A neighbour in an unprobed cluster is missed; clusters go stale as data changes |
| HNSW | A layered graph of near neighbours; start at a sparse top layer and hop towards the query, then descend to the dense bottom layer | More memory, slow build, awkward deletes; knobs `M`, `efConstruction`, `efSearch` |
| Quantisation (PQ, scalar, binary) | Compress each vector (PQ replaces parts with codebook ids; binary keeps one bit per number) | 4x to 30x+ less memory, lower accuracy, often re-scored with the full vectors; usually combined with IVF or a graph |

Others worth naming: DiskANN/Vamana (a graph built for SSD, for billions of vectors), ScaNN and Faiss (libraries combining these ideas), and LSH (the older hashing approach, now mostly replaced by graphs).

**Rule of thumb.** Under about 100k vectors, exact search is fine. Around a million with latency limits, use HNSW (or IVF if memory is tight). At tens or hundreds of millions, use IVF-PQ or DiskANN, usually with a
re-scoring step. Filters are a hidden problem: indexes find neighbours first and filter after, so strict filters can leave too few results.

**My answer in one line.** "At my size an exact scan costs milliseconds and gives perfect recall, so an index would only add risk. Past roughly a million vectors I would use HNSW, and past tens of millions IVF-PQ or DiskANN,
and I would measure recall against the exact scan every time." If the data grew 1000x, I would start with `hnsw` in pgvector and tune `efSearch` until recall matched the exact scan.

---

## 4. Retrieval: v1 to v2

### Q12. What did v1 do and where did it fail?
v1 embeds the question, finds the 8 closest chunks by cosine, adds neighbours, and asks the model to answer from them with citations. It put
the right scene in the top 8 for 44 of the 55 questions where I knew the scene. It failed on exact wording (a rare phrase gets diluted inside
a long chunk's embedding), on counts (it counted from 8 chunks: "6 or 7" when the truth was 24), and on questions mentioning two events.

### Q13. What did you add in v2 and what was the measured effect?
Three things: a question enhancer (a model call that rewrites the question into search text and optionally writes SQL), BM25 keyword search
fused with the vector results by reciprocal rank fusion, and SQL over the lines table for counts. The right scene reached the model for 53 of
55 questions (v1: 44). Transcript-only answers went from 7.62 to 8.65 out of 10 and the answer that may also use labelled memory from 8.88 to 9.36.
Count questions went from 2.3 to 9.7 because SQL returns the exact number.

### Q14. Why hybrid search? Show me a case for each side.
The two fail on different questions. Keyword search rescued exact phrases: "identity theft", "Cornell sweater" and "Beyoncé" went from missing to rank 1.
Vector search won where the question's words are not the transcript's: "start a fire" matches a scene about smoke and fire safety. On my 55 questions vector alone
found 44, BM25 46 and either 49. Fusing them with reciprocal rank fusion (k = 60, untuned) gave 48-49 at k = 8.

### Q15. Why reciprocal rank fusion, and what are its downsides?
RRF uses only ranks, so I did not need to calibrate vector distances against BM25 scores. Its downside showed up in my data: a chunk found
by only one list can sink. One chunk was vector rank 1 and ended at hybrid rank 11. I also found that raising k from 8 to 10 added nothing and
12 added one question for 46% more prompt tokens, so I kept 8.

### Q16. How did you choose k?
I measured retrieval only (no model calls) at 8, 10 and 12. k = 8 sent about 5.3k tokens on average; 10 added 23% tokens for no gain; 12 added one
question for 46% more. The remaining misses were not near misses (they were rank 16, 50, or outside the top 50), so a larger k would not fix them.

### Q17. How does the enhancer work, and how do you keep model-written SQL safe?
The enhancer returns JSON: search text, optional SQL, assumptions, and (in v3) a graph query. The SQL runs as a separate read-only database role, must be a single
SELECT, is wrapped with a 50-row limit and has a 5-second timeout. If it errors, the model gets one chance to correct it. SQL was written for 51
of 80 questions in v2 with no failures. One weakness I found: a query that returns zero rows is not retried (q071 searched for "hit" when the text says "hits").

### Q18. Did you use a re-ranker? Why not?
No. I would be careful not to claim otherwise. My bottleneck was different: failures were mostly retrieval misses on whole-show or relationship
questions, where the answer is spread over many scenes, so re-ordering eight chunks would not help. A cross-encoder re-ranker is a sensible next experiment
(retrieve 30-50, re-rank to 8), and I have the question set to measure it.

---

## 5. The graph (v3)

### Q19. Why add a graph? What did you see that justified it?
After v2, the failures that remained were whole-show and relationship questions: "Whom did Kelly marry?", "list Michael's managers", "what happened to
Karen after Jim". The answer is spread across scenes, and no single chunk says it. A graph of facts extracted per episode puts those facts in one place.
I only built it because the v2 grading pointed at exactly those failures.

### Q20. How did you build it?
One model call per episode extracts characters, places, events and relationships as JSON, each fact citing transcript line ids. A second call corrects the first, removing details no
line supports. Code validates the result. 186 episodes, no failures, about 5.5M input tokens. I then load it into Postgres tables
(3,883 characters, 1,698 events, 325 relation rows, 793 places) with views that resolve ids and build relationship timelines.

### Q21. How do you decide that two characters in different episodes are the same person?
Only from the data, with tiers. **Certain:** a name that recurs in 40+ episodes. **Probable:** a full name in 3+ episodes. **Possible:** a one-word name. Weak links are stored but never merged,
because a wrong merge silently corrupts every answer that touches that character. That produced 104 entities. No model is involved in that step.

### Q22. How does a question use the graph?
The enhancer, in the same call that writes the search text, may also write a read-only SQL query over the graph views. The rows come back with
the transcript lines they were extracted from, so the answer prompt can cite real scenes. Questions that name nobody (for example "who manages the branch") get no graph query. That is a known limitation.

### Q23. How do you stop the graph from containing things the model made up?
Every fact must cite line ids, a second pass removes unsupported details, and I told it to keep outside knowledge out (job titles, "married" without a line).
I sampled 50 items by hand: 45 correct, 5 partly right, none wrong, and the errors were over-reach rather than invention. The graph is incomplete though: 31 episodes have no relation rows.

### Q24. What did v3 actually improve?
On the 12 new graph-shaped questions, the transcript-only answer went from 6.0 to 7.58 (ten graph-shaped: 5.6 to 7.6). On the original 80, only the 15 questions that received a graph query
moved (6.33 to 7.73). Examples: "Whom did Kelly marry?" 2 to 9; the women Michael dates 5 to 9; Karen after Jim 2 to 7. The 65 questions the graph did not touch were unchanged (about -0.05 to -0.11), so it did no harm.

---

## 6. Evaluation

### Q25. How did you evaluate? Walk me through the setup.
92 questions, grouped by type (quotes, who-said, counts, lists, order, judgment and so on). For each I built a transcript-only reference answer independently of the system, and
I reviewed those myself. Each version produces three answers: memory only (no transcripts), transcript only, and transcript plus labelled memory. A council of three
model graders (a fact check, a faithfulness check and a reader view) scores each answer 0-10 and a chair resolves disagreements. Memory-only answers are generated once and reused, so they act as a control.

### Q26. Why a council and why a memory control?
A single judge is noisy and biased. I measured the noise: identical memory answers scored differently on 37 of 80 questions across two grading sessions, a mean difference of 0.66
and up to 4 points on one answer. The memory control turned that into a number I could subtract. And because separate sessions drifted, I regraded v2 and v3 together in one blind session
with the answers shuffled, so the same graders judged both versions without knowing which was which.

### Q27. What metrics did you use for retrieval and for answers?
Retrieval: whether the gold scene appears in the top 8, computed with no model calls, which is cheap and deterministic. Answers: the 0-10 council score, plus how many answers were correct (8-10),
wrong or refused, and whether the answer was fully grounded in the sources. I also ran an automatic citation check (are quoted lines actually in the sent passages), which turned out to be stricter than
the real grading and flagged some real quotes.

### Q28. How do you know the improvement is real and not noise?
By treating small differences as nothing: I set the rule that a mean difference under 0.5 or a single-answer difference under 2 points is noise. v1 to v2 (+1.0 on transcript-only) passes. v2 to v3 on the original
80 (+0.22) does not on its own. That is why I added 12 new questions I had not designed against, and the independent evidence is those twelve (+1.58).

### Q29. Did you tune on your test set?
Partly, and I say so. The original 80 questions were used to find v2's problems, so fixes aimed at them are tuned to them. Most of the apparent v3 gain on the old set came from four
questions I had studied while designing. On the other ten graph-query questions the score moved from 8.1 to 8.3. The twelve new questions are the cleaner test, though I chose them to suit list and arc queries, so
+2.0 is a best case.

---

## 7. Failures and lessons

### Q30. Give me two concrete failures and what you learned.
**"Whom did Mose hit?"** The scene exists (Mose hits Andy) but the extraction recorded no such event, and the SQL searched for "hit" while the transcript says "hits". Every version failed it. Lessons: lexical search needs
word-form handling, and an empty SQL result should trigger a retry. **q070** v3 refused (score 5 to 0) although its passages held candidates. No graph row could cause that, so it was a prompt-level regression, which taught me to check for
prompt-level effects separately from retrieval ones.

### Q31. Where does the system still hallucinate?
In the answer that may use labelled memory. Memory-based details creep in: it added a "campaign manager Thomas" for a senator's affair where the show says Chief of Staff Wesley Silver. With sparse graph rows (Stanley's marriages: 3 rows) it filled gaps with an invented affair. The labelling
makes these visible, but stricter control of unsupported memory claims remains unfinished.

### Q32. What surprised you?
The graph helped the transcript-only answer much more than the memory-allowed one, because the model already remembers famous relationships. Also: grading was harder to keep honest than building. Memory answers with fixed text drifted 0.44 between sessions, and only one blind
combined session removed that.

### Q33. What would you do next?
A re-ranker; a graph query for questions that name nobody; show more than two transcript lines per graph row; stricter handling of memory claims; an automatic citation check that understands graph rows; an extraction pass with higher recall for minor characters; and a sweep of chunk size and embedding
models, which I did not do.

---

## 8. Production and hosting

### Q34. How is it deployed?
One AWS EC2 `t3.small` (kept inside the free tier) running Docker Compose with two containers: the app, and Postgres 17 with pgvector. CloudFront sits in front for HTTPS on a cloudfront.net address, since I did
not buy a domain. Secrets live in an environment file on the server, not in the image or the repository. A single script builds the image for the server's CPU, ships it over ssh and restarts only the app.

### Q35. How do you protect a public endpoint that spends money per request?
A shared site password (login page and a signed cookie that expires, with limited attempts), per-IP rate limits, a hard daily question cap counted in the database so it holds across instances, spending limits on the model keys, and
excerpt-only sources. History is admin-only because it contains other people's questions, and the model-written SQL runs under a read-only role.

### Q36. What did you hit while deploying, and how did you fix it?
Several real things. The database role's password did not match the app's because the database was empty and the load step had never completed, which I diagnosed by comparing hashes of the values and checking the roles. The
History page retried failed requests in an endless loop, which I fixed by stopping on the first error and showing a retry button. The image had to be built for amd64 because my laptop is ARM. CloudFront returned a 504 until the
origin protocol and security group allowed it.

### Q37. Latency and cost per question?
A question costs one enhancer call and up to three answer calls, roughly 3.7k input tokens for the enhancer and 8k for each transcript answer, so about 20-30k input tokens in all. A v2 enhancer call had a median of 2 seconds. I would reduce cost by
running only the answer variants the user needs, which is what the public mode does.

### Q38. How would you scale this to 100x the data?
Add an approximate index (HNSW) and quantisation, keep keyword search in a proper search engine instead of in memory, move extraction to a queue, and rebuild the graph incrementally per document instead of per run. I would also separate the app from the
database and cache embeddings and repeated answers.

---

## 9. Skeptical questions

### Q39. "v3 is only +0.4 better than v2 overall. Was the graph worth it?"
For the questions it is meant for, yes: +2.0 on the ten graph-shaped transcript-only questions, +1.4 on the 15 original ones that got a graph query. Overall it looks small because most questions need no graph, and there it neither helps nor
hurts. The honest summary is that it is a targeted tool. The cost is real too: an extraction run, a second query to maintain, and more failure modes.

### Q40. "Your graders are language models. Why trust them?"
Partly I don't, and I designed around it: a fixed rubric, three lenses plus a chair, a control answer to measure noise, blind combined sessions so both versions face identical graders, and owner-reviewed references built without looking at the system. Remaining caveats are a single grader model family,
scores noisy by one to two points on a single answer, and answers that can reveal their version ("according to the graph").

### Q41. "Why not just use a bigger model or a long context window?"
Two reasons for the small model, one practical and one scientific. Practical: Gemini Flash has a free tier, which is what made 90+ questions times three answers times several versions affordable for a personal study. Scientific: a smaller model
remembers less of the show, which is closer to private company data, so the benefit of retrieval is easier to see. A bigger model would probably narrow the gap RAG fills; that is an open question in my notes and I have not tested it. For the
long-context question, the whole corpus is far larger than a window, and even if it fit, sending it with each question would be slow and expensive.

### Q42. "Isn't a graph over-engineering for this problem?"
It might be for many deployments, and I would say so. I built it because measurement showed a class of failures (whole-show and relationship questions) that more chunks and better search could not fix. A cheaper alternative I noted but did not try first is hierarchical summaries (scene to episode to
season). I would compare the two before recommending a graph.

### Q43. "What did you get wrong?"
I assumed one batch job per version would be fine, then split v3 into two (enhancer first, then answers) because the answers depend on the enhancer output. I also trusted an automatic citation check that turned out stricter than the real grading. And my first
fixed-form graph request was too limited, so I replaced it with a model-written query over the graph views. Each is in the decision log with the reason.

### Q44. "How would you apply this to a company's documents?"
The same pipeline, with different risks. Replace the transcripts with the company's documents, keep chunking tied to the document structure, add per-user permission filters at retrieval time (not in the prompt), redact personal data at ingestion, and build the evaluation set from real questions with a
frozen golden set and a regression run on every change. I would start with hybrid search and a re-ranker and add SQL or a graph only if the failure analysis asks for it.

---

## 10. Numbers cheat sheet

| Fact | Value |
|---|---|
| Data | 186 episodes, 57,973 lines, 4,658 chunks (about 300 tokens, up to 3 scenes, minimum 80) |
| Embeddings / generator | `voyage-4-large` at 1,024 dimensions / `gemini-3.8-flash`, k = 8, one neighbour each side |
| Retrieval hit (right scene in top 8, 55 questions) | vector 44 · BM25 46 · hybrid 48-49 · v2 53 |
| v1 → v2 mean score (80 questions) | transcript-only 7.62 → 8.65 · with labelled memory 8.88 → 9.36 · memory-only control about 7 |
| Count questions | 2.3 → 9.7 after SQL |
| v2 → v3, original 80 | transcript-only 8.65 → 8.88 · with memory 9.21 → 9.19 |
| of which the 15 that got a graph query | 6.33 → 7.73 (transcript-only) |
| New 12 graph-shaped questions | 6.00 → 7.58 (ten graph-shaped: 5.60 → 7.60) |
| All 92 | 8.30 → 8.71 (transcript-only) · 9.00 → 9.04 (with memory) |
| Grading noise | same memory text scored differently on 37 of 80 questions, mean difference 0.66, up to 4 points |
| Graph size | 104 entities, 3,883 characters, 1,698 events, 325 relation rows, 793 places; 50-item sample: 45 correct, 5 partly, 0 wrong |
| Extraction cost | 186 episodes, about 5.5M input and 0.76M output tokens |
| Hosting | EC2 t3.small + Docker Compose (app + Postgres 17/pgvector) + CloudFront, site password, rate limits, daily cap |
