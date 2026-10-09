# Experiment log

One short entry per eval run: what changed, the scores, and one line of interpretation. Raw outputs are in
`eval/runs/<label>.jsonl`.

## 2026-10-04 · `2026-10-04-v1-baseline`
- **What:** first full run of the question set (79 questions, questions file `14ebfcdb…`) on v1: vector retrieval
  (pack_300t_3s_80min × voyage-4-large@1024, k=8, ±1 neighbour) and three answers each: rag (`5ef7191d…`), llm
  (`00c114b1…`), hybrid (`2f685a0f…`). gemini-3.8-flash, model-default temperature, max 4,096 output tokens, one
  Gemini batch job (237 requests, finished in about 11 minutes).
- **Tokens:** 1.06M input, 58k output, 161k thinking.
- **Errors:** 4 of 237 answers were cut off before the JSON was complete (q017 hybrid, q037 llm, q046 rag, q047 rag).
- **Citation check:** 5 evidence quotes not found in the passages; 0 inline citations to scenes that weren't sent.
- **Self-reported:** rag said "not answerable from the passages" on 12 questions; llm said it didn't know on 2.
- **Scores:** not graded yet (gold answers pending).
- **Interpretation:** the pipeline runs end to end in batch. Accuracy is unknown until grading.
- **Added later (2026-10-05):** q080 (added to the question set after this run) answered under v1 with single online
  calls (`eval.run online`): v1 retrieval, rag_v1 and hybrid_v1, memory reused from the v2 run. Run 183. The
  label now covers the same 80 questions as v2.
- **Re-runs (same day):** the 4 cut-off answers were caused by the 4,096 output limit, which includes thinking: 5
  answers hit it at ~3,930 thinking tokens (232 others finished by 2,910). Limit raised to 16,384; those 5 (q017
  llm, q017 hybrid, q019 llm, q037 llm, q047 rag) re-run as single online calls and replaced in place; the JSONL
  keeps the batch error. All 237 answers are now complete. With room, they thought up to 13,261 tokens.

## 2026-10-04 · BM25 alone vs v1 vector (retrieval only, no LLM)
- **What:** BM25 keyword index (bm25s 0.3.12, k1 1.5, b 0.75; accents stripped, all words kept incl. 1-letter and
  stop words, no stemming) over the same 4,658 chunks; built in memory in 0.4 s, 20,887 distinct words. Measured
  on the 55 questions with known scenes: is a gold scene in the top 8?
- **Scores:** vector 44/55, BM25 46/55, either 49/55.
- **BM25 rescued** 5 vector misses: q002 identity theft (rank 1), q017 Cornell sweater (1), q027 Beyoncé (1), q079
  "I do not miss him" (8, via "Jim ... miss him"; the punchline isn't in the data), q049 building (8).
- **Vector won** where the question's words aren't the transcript's: q033 "start a fire" (scene says smoke, fire
  safety, firecrackers; BM25 rank 13), q061 costumes (9), q048 two events in one question (BM25 nothing).
- **Both fail (6):** series-wide stories q045, q050, q051, q056; q071 "Whom did Mose hit?" (common words, BM25 51);
  q031 "Why are you the way that you are" (all common words, BM25 25; phrase matching would help).
- **Interpretation:** the two methods fail on different questions, so fusing them should approach 49/55.

## 2026-10-05 · Hybrid (vector + BM25, RRF) and k = 8 / 10 / 12 (retrieval only, no LLM)
- **What:** vector top 50 and BM25 top 50 fused by RRF (rrf_k 60, untuned), then top k; ±1 neighbour expansion
  for prompt size. Same 55 questions with known scenes.
- **Scores (right scene sent):** k=8: vector 44, hybrid 48-49 · k=10: vector 44, hybrid 49 · k=12: vector 45,
  hybrid 50. Avg passage tokens per question: k=8 ~5.3k, k=10 ~6.5k (+23%), k=12 ~7.7k (+46%).
- **Hybrid gains at k=8:** q002, q017, q027 (BM25 rank 1), and q050 / q056 by agreement: mediocre in both lists
  (19 & 41, 27 & 35) fused to 7 and 6. q033 and q061 moved to rank 1.
- **Hybrid losses:** a chunk found by only one list can sink: q048 vector rank 1 -> hybrid 11; q079 BM25 8 -> 16.
- **k:** 10 adds nothing; 12 adds one (q048 at 11) for +46% tokens. Remaining misses are not near misses (q079 16,
  q031 50, q045 / q051 / q071 not in top 50): they need other fixes (one search per event, phrase matching, graph).
- **Run-to-run variance:** Voyage query embeddings are almost deterministic: identical on repeat for most
  questions, but occasionally shifted (q002 distances by up to 0.0025), which reorders near ties. Hybrid at k=8
  measured 48 in one run and 49 in the next. Stored retrieval is the reference for each eval run.
- **Interpretation:** keep k=8; hybrid gives +4 to +5 over v1 at the same prompt size.

## 2026-10-05 · `2026-10-05-v2`
- **What:** first full v2 run, 80 questions (questions file `13f9f4ff…`, adds q080 to the v1 set). v2 retrieval
  (enhancer_v1 + hybrid search + SQL, k=8, ±1) prepared one question at a time (80 enhancer calls, median 2.0 s,
  max 4.0 s), then one Gemini batch: rag_v2 (`b99b1177…`) and hybrid_v2 (`5b5419f8…`) for 80 questions; memory
  answers reused from v1 for 79 (memory_v1 `00c114b1…`), one new for q080. 161 batched calls, max output 16,384.
- **Retrieval (no LLM judgment):** right scene sent for 53/55 questions with known scenes (v1 44); gained q002,
  q017, q027, q031, q049, q050, q051, q056, q079; lost none; still missing q045, q071. SQL written for 51/80
  (all 6 count questions), 0 failed; SQL scenes added to the passages for 14.
- **Run:** 240 answers, 0 errors. Tokens (new calls only): 1.17M input, 45k output, 99k thinking (v1: 1.06M /
  58k / 173k); max thinking 3,238 (v1 13,261). 21 rag/hybrid answers cite [SQL].
- **Citation check:** 4 evidence quotes not found in the passages (v1: 6); 0 citations to scenes not sent.
- **Self-reported:** rag "not answerable" on 9 (v1: 12).
- **Scores:** not graded yet.
- **Interpretation:** retrieval is much better (+9 questions with the right scene). Thinking dropped by about
  40% with better evidence; worth checking in grading whether answers got better, not just cheaper.

## 2026-10-05 · Grading pilot: v1 (set s-556ab2, was g1), 6 questions
- **What:** evaluate-answers skill, rubrics-v1, scores 0-10. Single blind grader (main model) for q017 (fact),
  q040 (count), q045 (list); debate for q050 (why), q066 (opinion), q074 (false premise): three advocates (Sonnet,
  one per answer type) wrote briefs, a neutral judge (main model) checked the proofs and scored. All fresh contexts.
- **Scores (mean /10, 6 answers each):** v1 memory 7.8, v1 rag 5.5, v1 hybrid 7.8. RAG's losses are retrieval
  misses (q017 honest refusal 2, q050 6, q045 6) and a count from a sample (q040: "6 or 7, Jim second", truth 24,
  Dwight). Memory's: q017 Andy instead of Nellie, q040 "34-35". Hybrid matches memory where retrieval missed.
- **Debate:** useful for pointing the judge at the deciding scenes; about half the advocates' attacks were false
  (valid split episode numbers, a quote that was in the transcript), and the judge discarded them after checking.
  The judge thinks reference-based grading would have given the same scores. The advocate instructions now warn
  against numbering objections and ask for proofs checked in the database.
- **Reference fix:** q045 gained two optional items the grader found (Julie at the Happy Hour, Margaret).
- **Interpretation:** the pipeline works; v1 RAG's weakness on these 6 is retrieval, not reasoning.

## 2026-10-05 · Grading pilot 2: council (set s-d99104 = v1), same 6 questions
- **What:** council grading: fact and faithfulness members (Sonnet), reader member and chair (main model), each a
  fresh agent covering the 6 questions; chair checks disputed findings in the transcripts. Reviewer
  claude-council:claude-opus-5-5.
- **Scores (mean /10):** v1 memory 7.5, v1 rag 5.0, v1 hybrid 7.3 (pilot 1: 7.8 / 5.5 / 7.8).
- **Agreement between the two independent methods:** 18 answers; 9 identical, 17 within 1 point, mean absolute
  difference 0.56. Council slightly stricter (reader lens): q066 rag 9 -> 7 (leans on a gag line, counterpoint is
  just another candidate), q050 rag + memory 9 -> 8 (mixed citation / [memory] labels).
- **Members:** fast members made several false findings the chair dropped after checking (Robert California
  talking Jo out of her job is in S8E1 sc.5; the IHOP / catalogue line is in S4E14 sc.64; valid split episode
  numbers). The lenses added findings a single grader scored as fine: buried main points (q050 rag), judgment
  reading (q066 rag), honest refusal vs sample count (q017 vs q040).
- **Interpretation:** grading is stable across methods (within about half a point on average), so differences
  between versions larger than that are meaningful. The chair's database checks are essential.

## 2026-10-05 · v1 graded by council (set s-d99104, all 80 questions)
- **Method:** council per question (fact, faithfulness, reader members, then a chair), 80 questions x 3 answers
  (memory, rag, rag + memory), scores 0-10; references built blind earlier. Run in batches of about 10 questions;
  a usage limit interrupted one wave and the affected chairs / members were rerun.
- **Mean score /10 (80 answers each):** memory 7.3, rag 7.6, rag + memory 8.8.
- **Failure types:** memory: memory_error 26, incomplete 2, literal_reading 2; rag: retrieval_miss 18, incomplete 5,
  claim_beyond_evidence 2, literal_reading 2, count_from_sample 1; hybrid: memory_error 4, claim_beyond_evidence 3,
  evidence_misread 2, retrieval_miss 1.
- **Where each wins:** rag beats memory on detail (9.1 vs 6.1), visual (9.0 vs 5.6), which_episode (9.8 vs 7.8),
  multi_hop (9.6 vs 8.2); memory beats rag on who_said (9.9 vs 6.6), finish_the_quote (9.8 vs 6.8), order (9.3 vs
  2.0), count (5.5 vs 2.3), opinion (7.5 vs 6.7).
- **Rubric inconsistency found:** judgment totals were mapped 9-10 correct / 6-8 partial, while score anchors and
  eval.grade save use 8-10 / 4-7; the B7 chair lowered 11 answers of rubric total 8 by one point (q067 B, C; q068
  A; q069 C; q070 A; q075 B, C; q076 C; q080 A, B) so they could be saved as partial. Fixed in rubrics.md (8-10 /
  4-7 / 0-3); those 11 scores are one point low in v1 and the verdict files are unchanged.
- **Correction (2026-10-06):** the 10 judgment answers that had been lowered from 8 to 7 (q067 memory and hybrid; q068
  memory; q069 hybrid; q070 hybrid; q075 hybrid and rag; q076 memory; q080 memory and rag) were restored to 8 (correct
  band, support criterion 1) in the verdict files and in qa_reviews; the original values are kept in details.adjusted.
  The chair had said 11; 10 are affected. v1 means after the correction: memory 7.3, rag 7.6 (unchanged to one
  decimal), rag + memory 8.9 (was 8.8).

## 2026-10-06 · v2 graded by council (set s-bcc971, all 80 questions) and v1 vs v2
- **Method:** same as v1 (fact / faithfulness / reader members, then a chair), 80 questions x 3 answers, scores 0-10,
  references unchanged. A usage limit stopped the run twice (C5 / C6 chairs, C7 members); affected agents were rerun,
  nothing partial was saved. Chair verdicts: C5 24 correct / 2 partial / 2 wrong / 2 refused, C6 26 / 4 / 0 / 0, C7
  19 / 10 / 1 / 0, C8 20 / 4 / 3 / 3 (C1-C4 are in the summary below).
- **Mean score /10 (80 answers each):** memory v1 7.3 -> v2 7.1; rag 7.6 -> **8.7**; rag + memory 8.9 -> **9.4**.
  The memory answers are the same ones (reused), so the 0.2 difference is grading noise: 9 of 80 memory answers
  differ by 2 or more points between the two gradings. Differences under about half a point on a mean are not meaningful.
- **Failure types:** rag retrieval_miss 18 -> 11, incomplete 5 -> 2, count_from_sample 1 -> 0; hybrid 15 failures
  -> 3 (literal_reading, other, memory_error 1 each); memory_error 26 -> 22 (same answers, regraded).
- **Per answer (rag and hybrid, 160 pairs):** 126 within 1 point; 20 improved by 3 or more, 2 worsened by 3 or more.
  rag: 22 up, 47 same, 11 down; hybrid: 23 up, 44 same, 13 down.
- **Biggest gains (rag, all 2 -> 9/10, retrieval_miss fixed):** counts q039 / q040 / q041 / q042 / q043 / q044 (SQL
  gives the exact number; v1 guessed from a sample), who_said q027 "I am Beyonce" and q031 "Why are you the way that
  you are" (BM25), finish_the_quote q002, detail q017 (Cornell sweater), order q047 / q049 (right scenes now found).
- **Where v2 did worse:** q073 rag 10 -> 2 (v1 happened to retrieve S7E14, where Kelly marries Ryan; v2 did not, so
  it honestly refused); q078 rag 6 -> 2 (Karen's arc, S4E1 / S4E6 / S5E14 not sent); q046 rag 5 -> 3 (managers list,
  only 3 of 7 core managers retrieved); q070 rag 6 -> 4, q067 rag 9 -> 7 (judgment; weak candidates / a claim beyond
  the evidence). Other drops are 1-2 points on answers that were already correct.
- **Left after v2 (answer scored 5 or less, 12):** all rag but q071 hybrid (memory error): q003 (quote), q048 (staged
  fire), q071 (Mose hits Andy S5E9), q073, q078, q046, q070, q045, q054, q069, q079; 10 of the 11 rag cases are
  retrieval_miss (the needed scene was not in the top 8): one-off scenes whose wording the question does not share,
  and series-wide questions (a list over many episodes, an arc over several seasons).
- **Judgment questions:** rag opinion 7.0 -> 6.2 and story_arc 6.0 -> 2.0 (one question); transcript-only answers
  picked weak candidates and read jokes literally (q068 Nellie's "a thousand years old", Meredith's in-character
  line; q080 Pam's self-deprecation). Only 1 to 6 questions per category, so these are noisy.
- **Grading problems raised by the chairs (rubric, not yet fixed):** no failure type for an honest "I don't know"
  from a memory answer or for a weak judgment pick when retrieval was limited; scope criterion applied inconsistently
  by the reader lens; no rule for a quote whose words are missing from the data (q079); no outcome label for a true
  premise that is accepted (q073); q072 is a "how many" question filed as a list; q044 reference counts 30 / 27
  Dundies lines where the systems' regex found 25 / 22 (same winning season); q054 and q055 references vs the
  off-camera rule.
- **Interpretation:** v2 did what it was built for: exact wording, counts and ordering are fixed. What is left is
  retrieval misses on whole-show questions (traits, arcs, lists over many episodes), memory errors, and weak
  judgment answers. That list is the starting point for the v3 (graph) design.

## 2026-10-09 · Graph extraction, first single-episode test (S7E14 The Search, stage 1)
- **What:** one Gemini call (gemini-3.8-flash, thinking low), extract_v1.md (sha c113ef11) + stage1_schema.json
  (68b51374), 310 lines. Schema first rejected with 400 because of `maxItems`; removed (size limits are validator flags).
  Samples in docs/samples/S7E14.stage1.*.
- **Cost:** 10,345 input, 4,024 output tokens, no thinking, 28 s. Whole series estimate: about 1.9M input, 0.75M output.
- **Validator:** 24 characters, 6 places, 6 events, 3 relations, 1 refers_back; one flag (participant not in cited lines).
- **Checked against the transcript (by hand):** facts in the events are right (divorce announcement, Cece locked in a car,
  Michael stranded, the search, Holly finds Michael on the roof, they kiss S7E14 sc.?, lines 42825-42827).
  Problems: (1) **memory leak in descriptions:** job titles (customer service, accountant, receptionist, regional manager,
  sales, HR, liaison, warehouse manager) appear in 0 lines of the episode, so the model supplied them from memory despite the
  prompt; (2) **unsupported relation:** Jim-Pam "married / shown / stated" cites Michael's line "Is sex different after the
  baby, Jim?", which does not state a marriage; the validator's quote check passed because the quote exists;
  (3) missing: Holly-Michael relation although the kiss event is there, and Kelly-Ryan only "married ends" (no revealed);
  (4) importance: the divorce announcement is "minor" against the rule that a relationship ending is major; (5) 6 events
  for 310 lines (only the main plot); (6) the roof typed as workplace.
- **Interpretation:** the pipeline works end to end and the events are grounded, but memory still enters through the
  descriptions and through relations the lines do not state. Needs a prompt change (describe actions, no job titles unless
  a line says it) and a validator check that cited lines contain relation cue words.
- **Run 2 (same episode, prompt c273976a, edits: descriptions = actions with no job titles, stated vs implied, importance
  rule, place kinds):** 10,547 in / 3,652 out, 26 s; 25 characters, 4 places, 5 events, 6 relations; 2 flags. Fixed: job
  titles gone from descriptions (the only leftovers, "Pam's mother" and "Vendor", are supported or harmless), the divorce is
  now major, the roof is public, a Holly-AJ breakup relation (dating ends, quote "You broke up with AJ weeks ago") and
  family relations for Cece were added with sensible certainty (Pam-Cece implied). Still wrong: Jim-Pam "married, shown,
  stated" again, citing "Aw you'll get through it hon.": no line in the episode says they are married (married, wife,
  husband, wedding appear 0 times about them); Kelly-Ryan still only "ends" (no revealed row despite the instruction).
- **Finding:** the memory leak survives in `shown` relations: nothing in the episode changes, so the model fills in what it
  remembers. Proposal: drop `shown` from the schema (relations only when the episode begins, ends or reveals one; an open
  interval needs no repeated confirmation).
- **Run 3 (same episode, `shown` removed, prompt e9bcfbf4, schema 936cb24c):** 10,571 in / 3,459 out, 24 s; 27 characters,
  5 places, 6 events, 3 relations, 3 flags (participant not in cited lines, mostly witnesses). Relations now: Kelly-Ryan
  married `revealed` and `ends` (the two rows the prompt asks for, both quoting 42531 "Ryan Bailey Howard and I got
  divorced"), Holly-AJ dating `ends` ("You broke up with AJ weeks ago"). The unsupported Jim-Pam "married" is gone; Jim and
  Pam's family relations to Cece are gone with it (they were `shown`). All 3 relations are supported by their lines.
  Samples updated in docs/samples/S7E14.stage1.*. Next: try 2-3 more episodes of different kinds before building the
  pipeline.

## 2026-10-09 · Graph extraction test 2: S2E18 (Take Your Daughter to Work Day), stage 1, prompt e9bcfbf4
- **Run:** 9,990 in / 4,203 out, 33 s, 267 lines; 26 characters, 3 places, 8 events, 6 relations (all `revealed`), 1 flag.
  Samples in docs/samples/S2E18.stage1.*.
- **Small conflict with a named target:** extracted (e3 "Stanley aggressively confronts Ryan after seeing him talk with
  Melissa", cites line 7974 = the exact line). Also Michael's dating-service sign-up (major romance), the Fundle Bundle tape,
  the Struwwelpeter reading. Relation quotes are real: Kevin-Stacy engaged ("Abby's my fiancee Stacy's daughter"),
  Stanley-Melissa family. Place "Michael's mother's house" typed home.
- **Problems:** (1) job titles in 12 of 26 descriptions (receptionist, salesman, regional manager, HR, accountant, customer
  service, temp, executive) none of which occurs in the episode text: the fix that worked on S7E14 did not hold here;
  (2) `certainty` is optimistic: every relation is "stated", but Stanley-Terry married rests on Melissa's "That is my
  step-mother" (implied at best) and Toby-Sasha family on lines where Toby only talks to Sasha; (3) e1 is a generic
  event ("hosts the day") with children as agents.
- **Interpretation:** events and quotes are grounded; memory enters through job-title descriptions and through inflated
  certainty. Plans: descriptions that must start with a verb (an action, which job titles do not fit), a validator flag
  for role nouns that are not in the episode text, and a verifier pass later (cited lines + claim -> stated / implied /
  unsupported) instead of trusting stage 1 certainty.

## 2026-10-09 · Review pass (corrector) first test on the stored S2E18 and S7E14 extractions
- **What:** review_v1.md (sha in graph/out/*.review.json meta) + graph/review_schema.json; the reviewer sees the episode text
  and the stage 1 extraction (with relation ids) and returns corrections (edit / set / drop); code applies and re-validates.
  Not written to the database. Outputs in graph/out/ (not committed).
- **S2E18:** 12,307 in / 1,089 out, 9 s; 12 corrections, 12 applied: dropped the empty event e1 ("the office hosts the
  day"); removed job titles from 9 descriptions (receptionist, salesman x3, accountant x3, customer service, temp) and
  "corporate executive" and "Pam's fiance" (no line shows them). The validator is clean afterwards.
- **S2E18, missed:** "at reception" in event e6 (the leak the owner found), "Regional manager" (Michael), "HR
  representative" (Toby), "Office employee" (Meredith), "Warehouse employee" (Roy, Darryl); no certainty changes at all, so
  Stanley-Terry "married, stated" (evidence: "That is my step-mother") and Toby-Sasha stay "stated".
- **S7E14 (run 3, few known errors):** 12,887 in / 280 out, 5 s; 3 corrections: a skipped edit of a character's names (field
  not allowed), the AJ description corrected (Holly broke up with AJ, not the reverse; true to line 42558), and Helen removed
  as participant of the gas-station event ("not present"): arguable, she is the cause. No damage to supported items.
- **Interpretation:** the corrector is cheap (about 1k output tokens) and makes real, mostly right corrections without
  rewriting, but one pass misses about half of the leaks and never tightens certainty. Idea: code computes the words in the
  extraction that occur nowhere in the episode text and hands them to the reviewer as hints (it still decides, so paraphrases
  are not deleted); and examples of certainty fixes in the prompt.
- **Review run 2 on S2E18 (prompt with a `checked` list of every item, participant rule fixed):** 12,415 in / 1,390 out, 10 s;
  `checked` covered 43 of 43 items; the 12 corrections have exactly the same targets as run 1. So the first pass was not
  skipping items: it looked at everything and judged the same way. Re-checking the ground truth: Toby "HR" is supported
  (line 8094 "you work for human resources"), "warehouse" is weakly supported (8169 "warehouse guys"), so those were not
  real misses. Real misses left: "at reception" in e6 (a detail inside a supported sentence), Michael "Regional manager"
  (lines say "the boss", 7887), and inflated certainty on inferred relations (Stanley-Terry, Toby-Sasha). The participant
  rule change was not exercised by this episode (it concerns S7E14's Helen).

- **Review run 3 on S2E18 (with hint words; 64 hints in 31 items):** 12,802 in / 1,520 out, 13 s; 43 of 43 checked; 14
  corrections. New catches: "at reception" removed from e6; Michael "Regional manager" -> "Boss" (line 7887); Stanley-Terry
  `married` stated -> implied. Hints: 15 of 64 hint words were removed by a correction (all the job titles plus `reception`,
  `german`); 49 were harmless paraphrases left alone; one removed word (`service`) was not hinted but part of a hinted phrase.
  The certainty change was not hint-driven. Not caught: Toby-Sasha certainty, Meredith "Office employee", and (run to run
  variation) Roy "Pam's fiance", removed in runs 1 and 2 but not in run 3.
- **Problem and fix:** in 6 descriptions the reviewer replaced a removed job title with "Employee" (a word no line gives; it also
  changed "German stories" to "cautionary stories"). Added an edit guard in code (new words must come from the old text or the
  episode vocabulary; others are removed again); replayed offline on the saved corrections: 14 of 14 applied, the
  substitutions repaired.

## 2026-10-09 · Both passes on S9E22 (Dwight proposes to Angela)
- **Stage 1:** 16,231 in / 5,261 out, 35 s, 501 lines; 28 characters, 5 places, 12 events, 2 relations, 3 flags.
  **Review:** 19,951 in / 532 out, 16 s; 47 of 47 checked, 3 corrections (Pam, Phyllis, Stanley "Sales rep" removed). Samples in
  docs/samples/S9E22.*.
- **Facts right:** Dwight stops Angela's car and proposes with his grandmother's ring (59358), she accepts ("Okay, yes...yes, I
  will!" 59359) -> relation Dwight-Angela engaged / begins with that quote; "Phillip's your son" -> Dwight-Philip family
  revealed; Pam's worry and Jim's montage; Andy's audition; Darryl's farewell; documentary premiere at Poor Richard's.
- **Leaks left after the review (0 hits in the 501 lines):** "Accountant" for Kevin, Oscar, Angela; "Building security guard"
  (Hank); "Works at the front desk" (Erin); "Former manager" (Andy). Supported: Milkmaid (58910), Regional manager (7 lines),
  "Assistant to the regional manager". So the reviewer found 3 of about 7 unsupported role claims (it caught "accountant" on S2E18
  but not here): reviewer recall on descriptions is unreliable on a longer episode even with hints.
- **Interpretation:** events and relations are good; the leak is concentrated in character descriptions that start with a job
  noun ("Accountant who ..."). The prompt asked for "what the person does" but never required a verb-first sentence (planned
  after the S2E18 test, not applied). Fix at the source: description must start with a verb.
- **Correction to the S9E22 entry above (owner asked for a thorough re-check):** "Accountant" for Angela is partly supported:
  line 59260 Angela: "Thanks for letting me hang out in Accounting." (my search for "accountant" missed "Accounting"; the hint list
  correctly did not hint it, because the stems match). Kevin and Oscar as accountants have no line. Confirmed unsupported:
  Hank "Building security guard" (his only line is "Thank you."; hinted word `guard`, missed by the reviewer), Erin "Works at the
  front desk" and Andy "Former manager" (not hinted: the words desk / manager occur elsewhere in the episode, so a vocabulary
  check cannot see them), Glenn "Warehouse worker" (his line: "How was the delivery?"). Supported: Darryl and the warehouse
  (59079), Milkmaid (58910), regional manager (7 lines), Assistant to the regional manager.
- **Lesson:** the vocabulary hints only catch words that appear nowhere in the episode; a memory claim built from words used
  elsewhere in the episode needs the reviewer to check the claim against that person's own lines. The reviewer prompt
  ("supported if some line shows or reasonably implies it") lets a model that remembers the show accept a plausible guess.

- **S9E22 rerun with verb-first descriptions (extract prompt 4953da27), stricter review prompt and evidence beside each item:**
  stage 1 16,261 in / 5,204 out; review 26,218 in / 323 out, 4 s, 48 of 48 checked, 1 correction (Hank "in the building lobby":
  no line mentions a lobby). Descriptions are now actions: every job-title leak of the first S9E22 run is gone from stage 1 (no
  Accountant, Sales rep, Receptionist, Former manager, security guard). Checked every remaining description claim against the
  lines: supported: Erin buzzes people in (stage direction 58888), Oscar invited Angela to move in (58906), Kevin and the gift card
  (59257-59262), the senator's divorce (58906), Esther and the farm (59192), Creed (58954, 59368), check-in guy (58912, 59218);
  weak: the bartender "switches to PBS" (the lines only show a tie, "Tie means I do nothing", then "All right.": an inference);
  unsupported and left: Glenn "in the warehouse". About 1 leak left against about 7.
- **Cost per episode now:** stage 1 about 16k in / 5k out (S9E22, 501 lines) plus review about 26k in / 0.3k out. For 186 episodes
  about 6-8M input and 1M output tokens (the evidence block adds about 6k input per review).

## 2026-10-10 · Quality sample of run v3-extract-001 (Claude's review; owner's review pending)
- **What:** random sample (seed 7) of 30 events and 20 relations from the reviewed extractions of all 186 episodes
  (graph/make_sample.py -> graph/out/quality-sample.md); each read against its cited lines, 14 doubtful ones checked against the
  surrounding transcript. Results in graph/out/quality-sample-claude-review.md.
- **Result:** events 28 correct / 2 partly / 0 wrong; relations 17 / 3 / 0 (R07 Dwight-Angela married is a contested trick
  marriage ("That doesn't count!"); R11 Jim-Dwight boss is an inference from the Jim-Michael co-manager promotion; E09
  "weekend of the wedding" is an inference, wedding June 10 vs trip June 8; E17 "second place" vs "employee number three").
- **Findings:** errors are over-reach (inference or contested claim stated as fact), not invention. The participant flag (28% of
  events) did not point to a wrong event in the sample. Importance is noisy (about 4 of 16 "major" arguable). The senator
  appears as "Robert" (needs linking).
