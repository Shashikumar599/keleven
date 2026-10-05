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
