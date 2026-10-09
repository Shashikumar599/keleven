# v1 vs v2: analysis of the council grading

Sets: v1 = `s-d99104` (run `2026-10-04-v1-baseline`), v2 = `s-bcc971` (run `2026-10-05-v2`). 80 questions, three answers
each: **memory** (no transcripts), **rag** (transcripts only, strict), **rag + memory** (transcripts plus memory, memory
claims labelled). Scores 0-10 from the council (fact / faithfulness / reader lenses + chair). Memory answers were
generated once and reused in v2, so memory is the control: whatever differs for memory is grading noise.

## 1. Reading the numbers safely

- Memory answers are identical in both runs, yet they scored 7.3 vs 7.1, and 9 of 80 differ by 2 or more points. So the
  grading noise is about +-0.2 on a mean and up to 2 points on one answer. Treat a difference of under 0.5 on a mean
  (or under 2 on one answer) as nothing.
- The grading agents were not identical across versions. v1: fact and faithfulness members pinned to Sonnet, reader and
  chair on the session model (Opus early, Sonnet after the switch partway through). v2: C1-C4 all on the session model
  (Sonnet), C5-C8 chairs and the C7/C8 readers on Opus. The verdict files all say reviewer `claude-opus-5-5`; that field
  is not the model that ran. The large changes below are checkable facts (a count, a scene) where the grader model
  should not matter; small and judgment differences could.
- Per-category cells hold 1-22 questions. Only `detail` (22) and `who_said` (7) are large enough to say much alone.

## 2. Headline

| | memory | rag | rag + memory |
|---|---|---|---|
| mean /10, v1 | 7.35 | 7.62 | 8.88 |
| mean /10, v2 | 7.06 | 8.65 | 9.36 |
| correct (8-10), v1 / v2 | 51 / 52 | 52 / 64 | 70 / 77 |
| wrong or refused, v1 / v2 | 11 / 12 | 15 / 6 | 3 / 1 |
| rag grounded "yes", v1 / v2 | n/a | 68 / 76 | 63 / 70 |
| memory overconfident when wrong | 24 / 80 | | 22 / 80 |

v2 moved rag by +1.0 and rag + memory by +0.5; memory is flat by construction.

## 3. Which system did what better

**Memory (no transcripts).** Strong on famous lines and who-said (9.4-9.9 on who_said and finish_the_quote), order (9.7),
off-camera (9.3) and opinions it can reason about. Weak on detail (5.3), visual (6.0), counts (4.8) and which-episode
(7.0). 22-26 of its failures are `memory_error`, and 22-24 of 80 answers are confidently wrong ("overconfident"):
q023 "36 hours", q024 invented cupcakes, q037 rejects a premise that is true, q071 "Mose never hits anyone", q063 invents
a nursing reason for Pam's costume. Memory never improves with the version, and it is not safe to trust where it is
confident. It is still the best answer on 4-11 questions (q003, q048, q073, q078...), always where retrieval missed.

**Rag (transcripts only).** v1 was the weakest system on exact facts it could not find: who_said 6.6, finish_the_quote
6.8, order 2.0, count 2.3, because the right scene was not in the 8 chunks (12 refusals, 18 retrieval_miss). v2 fixed
exactly that: who_said 9.3, finish_the_quote 8.2, order 7.0, count 9.7, refusals 12 -> 5, retrieval_miss 18 -> 11.
It stays honest: 76 of 80 answers fully grounded, and its refusals are justified (the scene was not sent). Its weaknesses
are now (a) whole-show questions (lists over many episodes, arcs over seasons: list 5.7, story_arc 2.0), (b) judgment
questions (6.6; it picks the candidate the passages happen to contain and reads jokes literally), and (c) one-off scenes
whose words the question does not share.

**Rag + memory (hybrid).** Best at everything in both versions. Its failure mode is different: not "I can't find it" but
memory overriding or adding to good evidence. v1: 14 failures across memory_error 4, claim_beyond_evidence 3,
evidence_misread 2, others; v2: 3 failures (q068 and q070 judgment, q071 memory error).
It is the best answer outright on 12 questions and ties for best on 53 more (65 of 80 in all). It lost to the better single system
by 2 or more points only 2 times in v2 (q013, q035, each 8 vs 10) and 3 in v1 (q026, q058, q079). 10 of 80 hybrid
answers have grounded = "partly" (v2), the main remaining defect: [memory] and scene labels mixed up.

Take-away: memory and transcripts fail on different questions, and a model that may use both and says which is which is
the safest answer. Memory alone is only worth its confidence on famous quotes and general knowledge.

## 4. What v2 improved, and why (mechanism)

| Question types | v1 rag -> v2 rag | Cause fixed |
|---|---|---|
| counts (q039-q044) | 2.3 -> 9.7 | SQL on the lines table returns the exact number; v1 counted from 8 chunks (q040: "6 or 7", truth 24) |
| who_said / finish_the_quote with rare wording (q002, q017, q027, q031) | 2 -> 10 | BM25 finds exact words ("Beyonce", "Cornell sweater", "identity theft") that the embedding diluted inside long chunks |
| order / which-came-first (q047, q049) | 2 -> 10 / 9 | two events in one question; enhancer + hybrid now bring both scenes |
| hybrid answers (all) | 8.9 -> 9.4 | better evidence leaves less room for memory to override it |
| thinking tokens | -40% | less hunting inside weak evidence (not a score effect) |

Retrieval alone (no LLM): right scene in the top 8 for 53 of 55 questions with known scenes (v1: 44).

## 5. Where v2 is still weak, with the evidence

1. **Retrieval misses on 11 rag answers** (q003, q045, q046, q048, q054, q069, q070, q071, q073, q078, plus q079 where the punchline is missing from the data):
   - **q073 "Whom did Kelly marry?" (10 -> 2).** Enhancer `search_text` = "Kelly marry", no SQL. The transcript says
     "married", "engaged", "wedding"; BM25 has no stemming, so the lexical side misses and the chunk with the answer (S7E14)
     did not make the top 8. v1 got it by chance.
   - **q071 "Whom did Mose hit?".** The enhancer wrote SQL with `\mhit\M`; the text says "Mose **hits** Andy" (S5E9 sc.20).
     The SQL returned 0 rows, and the runner only retries on an SQL error, not on an empty result. 5 of the 51 SQL queries
     returned nothing (q003, q018, q023, q071, q079).
   - **q078 / q046 / q045 (arcs and lists).** One search, 8 chunks, cannot cover 4 seasons or 7 managers. Only 3 of 7
     managers were retrieved for q046.
   - **The enhancer mostly echoes the question.** In 67 of 80 plans its search text adds at most one new word. It does not
     expand morphology (marry/married), does not decompose, does not search per event, and writes SQL only for 51.
2. **Series-wide / trait / relationship questions** are the common thread (q045, q046, q069, q078, q070): the answer is
   spread over many scenes and no single chunk says it. A graph, or per-episode and per-character summaries, is the
   obvious fit.
3. **Judgment questions** (rag 6.6, v1 7.5): transcript-only answers mine the passages they got, miss the better
   candidate that was never sent (q069: Michael vs Toby; q070: Mose over stronger candidates), and read jokes
   literally (q068 Nellie's "a thousand years old", Meredith's in-character line; q075 Creed "possible murderer";
   q080 Pam's self-deprecation). Literal reading is a model/prompt weakness, retrieval-independent.
4. **Memory confidence.** 22 overconfident memory answers; they are harmless inside hybrid when evidence is present and
   harmful when it is not (q071 hybrid: "Mose hits no one else").
5. **Unfound data limits:** q079 (the punchline words are not in the dataset), off-camera questions (q054, q055) and
   visual gags the transcripts only imply. These are not retrieval problems; some cannot be answered from this data.

## 6. Problems in the evaluation itself (fix before grading v3)

- Rubric gaps reported by the chairs: no failure type for an honest "I don't know" from memory, nor for a weak
  judgment pick caused by limited retrieval; scope criterion applied inconsistently (is "answers only within its
  sample" a scope or reading issue?); no rule for a quote whose words are missing from the data (q079); no outcome
  label for a true premise that is accepted (q073); q072 is a count filed as a list; q044 reference 30 / 27 lines vs
  the systems' 25 / 22 (same winning season); q054 / q055 off-camera references vs the rule.
- Grading noise and mixed models (section 1). A fixed model per role is needed for v3, and the memory control stays.
- The question set has only 6 count, 3 list, 4 explanation, 8 judgment questions: too few to see changes in those
  types. The set was also used to find the v2 problems, so v3 fixes aimed at these failures are tuned to them.
- Grading is expensive: about 40 agent runs (3 members + chair per 10 questions, plus reruns after usage limits) per version.

## 7. Lessons that carry into v3

1. Keep the three-answer comparison; hybrid (transcripts + labelled memory) is the target to beat (9.4).
2. A better router, not just more retrieval: counts need SQL, exact words need BM25, whole-show questions need
   something that aggregates across scenes.
3. The enhancer must do real work: normalise word forms, add synonyms and neighbours ("married / engaged / wedding"),
   split a multi-part question into several searches, retry SQL that returns 0 rows.
4. Whole-show questions need a structure over the transcripts: a graph of characters, relationships and events, or
   hierarchical chunks (scene -> episode summary -> season / character arc). Test it on exactly the failing questions.
5. Reading nuance (sarcasm, jokes, in-character lines) needs prompt-level work: a note in the answer prompt and a
   separate check, because retrieval does not fix it.
6. Measure with the memory control and a held-out question set, otherwise v3 gains cannot be separated from tuning.

## 8. Plan

**Phase A: finish evaluation housekeeping (small, no new LLM runs).**
1. Owner decisions on the rubric gaps in section 6, then edit rubrics.md (v1 and v2 verdicts stay as graded; record the
   rubric version on each future set).
2. Owner review of the remaining medium-confidence references (q044, q040, q046, q026, q054, q055, q060, q072, q079)
   and of the three wrong draft notes in questions.jsonl (q073, q060, q032), only with the owner's yes.
3. Pin the grader model per role for v3 (and record it in config.json).

**Phase B: design v3 (discussion first, nothing built).**
1. Review the failing questions as a design brief: list questions scoring under 8 in v2 grouped by cause (retrieval
   miss on one-off scenes, whole-show, judgment reading, memory, data limits). Decide which a graph can reach.
2. Decide the graph scope: entities (characters, episodes, scenes), edges (relationships, events, mentions), how
   they are extracted (LLM over scenes, cost), and how an answer uses them. Decide whether episode / character
   summaries (hierarchical chunks) are tried first as the cheaper step.
3. Decide the enhancer / router upgrade (morphology, decomposition, SQL retry on empty) and whether it is part of v3 or a
   v2.1. The v2 prompt files are frozen: any change is a new version and a new file.
4. Add new questions for the graph-type failures (traits, arcs, relationships, "who in the whole series ...", lists
   across seasons), about 30, split into dev and a held-out test set that is not used while tuning.

**Phase C: build and measure v3.** Retrieval-only measurement first (right scene / right entities found, no LLM),
then the answer run (same 80 plus the new questions), graded with the same council and pinned models, then
v1 + v2 + v3 compared with the memory control. Log decisions and the run in decisions.md and experiment-log.md.

**Phase D (optional): reliability check.** Regrade about 10 memory answers once with fixed models to put a number on
grading noise.
