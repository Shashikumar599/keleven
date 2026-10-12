# Phase 3: Graph (v3), and the end of the study

## What was built
A graph of characters, places, events and relationships extracted from every episode, a query layer over it, and a third
pipeline version that lets the question enhancer write a read-only query against it.
- **Extraction:** one Gemini Flash call per episode plus a second call that only corrects (removes details no line shows).
  186 episodes, no failures, 5.5M input and 0.76M output tokens. Every fact cites transcript line ids. A 50-item quality
  sample found 45 correct, 5 partly right and none wrong (the errors are over-reach, not invention).
- **Linking:** characters are the same person across episodes only when the data proves it. 104 entities
  (certain / probable / possible tiers); weak links are stored and never merged. No model call.
- **Tables and views:** 3,883 characters, 1,698 events, 325 relation rows (199 intervals), 793 places, 314 callbacks;
  views resolve ids to entities and build relationship timelines (migrations 013-016).
- **v3 pipeline:** the enhancer prompt (`enhance_v3.md`) also returns `graph_sql`; the rows come back with their transcript
  lines; answer prompts `rag_v3.md` and `hybrid_v3.md` say how to read them. v1 and v2 are untouched and still selectable.

## Setup
`gemini-3.8-flash` (enhancer, answers, extraction), `voyage-4-large@1024` (embeddings), chunk set `pack_300t_3s_80min`
(4,658 chunks), k = 8, neighbour expansion 1, graph build `v3-graph-001` from extraction run `v3-extract-001`.
Evaluation: 92 questions (80 original + 12 added at the end: ten graph-shaped, two controls), transcript-only references,
council grading by Sonnet 5.5 (fact, faithfulness and reader members, then a chair), rubrics-v2.

## Results
Mean score out of 10. **v2 → v3 was graded in one blind session** (both versions' answers shuffled together, so the same
graders judged both; the memory-only answer is one shared text and averages 6.69 on the 80).

| Questions | rag v2 → v3 | hybrid v2 → v3 |
|---|---|---|
| Original 80 | 8.65 → 8.88 (+0.22) | 9.21 → 9.19 (−0.03) |
| of which the 15 that got a graph query | 6.33 → 7.73 (+1.40) | 8.13 → 8.47 (+0.33) |
| of which the other 65 | 9.18 → 9.14 | 9.46 → 9.35 |
| New 12 (ten graph-shaped + two controls) | 6.00 → 7.58 (+1.58) | 7.58 → 8.08 (+0.50) |
| of which the ten graph-shaped | 5.60 → 7.60 (+2.00) | 7.60 → 8.30 (+0.70) |
| All 92 | 8.30 → 8.71 (+0.40) | 9.00 → 9.04 (+0.04) |

v1 → v2 (separate sessions, see `v1-v2-grading-analysis.md`): rag 7.62 → 8.65, hybrid 8.88 → 9.36.
Grading noise was measured on identical text: the same memory answers scored differently on 37 of 80 questions across two
sessions (mean absolute difference 0.66, up to 4 points), which is why the final comparison was regraded in one session.

## Where it worked
- **Lists, histories and false premises in the transcript-only answers.** q073 "Whom did Kelly marry?" 2 → 9, q045 women
  Michael dates 5 → 9, q078 Karen after Jim 2 → 7, q046 managers 3 → 6; on the new questions, engagements 4 → 10, Andy and
  Erin 5 → 9, Jan and Michael 5 → 8, Jim and Pam 3 → 8. Retrieval-miss failures in rag fell from 10 to 4.
- **No harm elsewhere.** On the 65 questions the graph does not touch, scores moved by −0.05 and −0.11.
- **Citations survive.** Graph rows carry the transcript lines they came from, so answers still cite scenes.

## Where it failed (concrete)
1. **q071 "Whom did Mose hit?"** The scene exists (Mose hits Andy, S5E9 sc.20) but the extraction recorded no such event, and
   the transcript SQL searched for "hit" while the text says "hits". Every answer to it, from v2 and v3 alike, was refused or wrong.
2. **q048 fire drill.** "Fire drill" never appears in the transcripts; the graph found only the car event, so the order
   question could not be settled and the transcript-only answer refused.
3. **q070 "short appearance, high impact".** v2 gave a hedged pick; v3 refused although its passages held candidates
   (5 → 0): a prompt-level regression no graph row could cause.
4. **q058 senator's affair.** Hybrid added "campaign manager Thomas" from memory; the show says Chief of Staff Wesley Silver
   (S9E19 sc.33). Memory claims inside hybrid answers remain the main source of unsupported detail.
5. **q086 Stanley's marriages and affairs.** Only 3 graph rows; answers invented a "Lydia" affair setting. Sparse extraction
   gives the model room to fill gaps.

## What surprised us
- **The graph helps the transcript-only answer, not the labelled-memory one.** Hybrid already knows the famous relationships,
  so its gain was +0.0 on the original set.
- **Most of the apparent gain on the old set came from four questions we had studied while designing.** On the other ten
  graph-query questions rag moved 8.1 → 8.3. The independent evidence is the twelve new questions.
- **Grading was the hardest part to keep honest.** Separate sessions drifted by 0.44 on identical text and by up to 4
  points on one answer; only a single blind session with both versions removed it.
- **Keeping memory out of the extraction** (job titles, "married" without a line) took more design than the extraction itself.

## Decision: the study ends here
v3 is the final pipeline and is now the app's default. Nothing more is built. Ideas that were considered and not pursued,
for anyone continuing: let the enhancer query the graph for questions that name nobody ("who manages the branch"); show
more than two transcript lines per graph row; stricter control of unsupported memory claims in hybrid answers; a
programmatic citation check that knows about graph rows (the stored automatic check is stricter than the real faithfulness
grading and flagged real quotes); an extraction pass with higher recall for minor characters.

## Caveats
One run; Sonnet-only graders; answers from v3 can reveal the version ("according to the graph"); per-answer scores are noisy
by 1-2 points; q040's reference is internally inconsistent (30 against 24) and was left as is; the twelve new questions
were chosen to suit list and arc queries, so +2.00 is the best case.
