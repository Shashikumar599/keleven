# Grading rubrics (rubric version: rubrics-v2)

rubrics-v2 (2026-10-07) adds to v1 (changes marked "v2"); v1 and v2 grading sets were graded under rubrics-v1 and are not regraded.

Grade every answer against the reference you built for the question (see SKILL.md). Each answer gets:

- `score`: 0-10, using the anchors below (the number used to compare systems and versions)
- `verdict`: correct / partial / wrong / refused (the mapping per kind is below)
- `grounded`: yes / partly / no / n/a (transcript answers only; memory answers are n/a)
- `failure_type`: one main cause when the verdict is not correct (list at the end), else null
- `notes`: one or two sentences: what is right or wrong, concretely
- `details`: the kind-specific fields below

## Score anchors (all kinds)

| score | meaning |
|---|---|
| 10 | fully correct and complete; every claim right; grounded (transcript answers) |
| 8-9 | correct, with a minor flaw: a missing small detail, a citation slip, slight overreach |
| 5-7 | partly right: a required part missing or wrong, or right answer with a wrong claim of substance |
| 2-4 | mostly wrong, with something right or useful |
| 0-1 | wrong, invented, or a refusal |

Score and verdict must agree: correct = 8-10, partial = 4-7, wrong = 0-3, refused = 0-2 (an honest refusal when the
evidence was not sent scores 2, an empty or unjustified refusal 0). For judgment questions the score is the rubric
total (0-10, below).

Judge what the answer says, not how it says it: length, style and confidence don't earn credit. An answer that
is right but buries the answer under wrong claims is partial.


## Kinds of question

### A. Fact: detail, who_said, which_episode, finish_the_quote, order, visual, multi_hop
- correct: every part of the question answered, and right. Extra claims, if any, are also right.
- partial: some parts right, some missing or wrong; or right but with a wrong extra claim of substance.
- wrong: the main answer is wrong.
- refused: says it can't answer, gives no answer.
- Episodes: accept split or combined numbering (Chair Model = S4E10 here, S4E14 in split numbering) and titles.
  A wrong episode when the question asks for one is wrong; a wrong episode given as an extra detail makes it partial.
- Quotes (finish_the_quote, who_said): the words must match apart from punctuation and filler ("um", "you know").
- v2, quote not in the data: when the reference says the quoted words are missing from the transcripts (q079), a transcript-only answer is correct if it points to the setup scene and speaker the evidence supports and says the punchline words are not in the passages; naming no speaker though the evidence clearly points to one is partial (incomplete). A memory answer naming the right speaker is correct.
- If the reference lists accepted_alternatives, any one of them is correct.
- details: {"parts": [{"part": "...", "ok": true|false}]} for multi-part questions.

### B. Count: count
- The truth is the dataset count (run the SQL yourself). Note what is counted: lines containing a phrase vs uses.
- correct: the exact dataset number, or a different number with a stated, reasonable reading of the question.
- partial: close (within about 15%), or approximate ("about 30") and labelled approximate; or right number for
  the wrong thing.
- wrong: off by more, or presented as a total when it was counted from a few passages.
- v2, owner-supplied counts: when the reference lists an owner count with a tolerance (q040: 30, +-1) and also the dataset count (24), either is correct if the answer says what it counted.
- A question filed as a list that asks "how many" (q072) is graded by the reference's stated treatment, not as a list.
- details: {"truth": N, "given": N or null, "exactness": "exact|close|approximate|wrong", "states_what_counted": bool}

### C. List: list
- Build the reference list from the transcripts. Count items found, missed, and invented.
- Completeness is judged on the reference's core items; optional items are neither required nor penalized.
- correct: all core items, nothing invented. partial: at least half of the core items, or all but with an
  invented item. wrong: under half, or mostly invented.
- details: {"reference_items": [...], "found": [...], "missed": [...], "invented": [...]}

### D. Explanation: why, story_arc
- Reference = the main cause (must be there) + supporting points (credit, not required).
- correct: main cause right, no wrong claims of substance. partial: main cause right but a wrong claim, or only
  supporting points. wrong: main cause wrong or missing.
- details: {"main_cause_ok": bool, "wrong_claims": [...]}

### E. Judgment: opinion, counterfactual, loaded
No right answer. Score each criterion 0 (no), 1 (partly), 2 (yes):
1. position: takes a clear position (lists without a verdict score 0)
2. support: supports it with what happens in the show (transcript answers: cited)
3. reading: reads the show sensibly: sarcasm, insults, self-deprecation and jokes not taken literally; the
   candidates are plausible to someone who knows the show
4. counterpoint: gives the strongest point against its view
5. scope: answers about the characters, not real people; for loaded wording, answers the substance without
   repeating the label; for what-if questions, says which part is speculation. v2: scope is only these three things.
   Basing the answer on only the evidence it was sent ("in the sample") is not a scope issue: it counts under
   support (the evidence is thin) or reading, and when better evidence was never sent the failure type is retrieval_miss.
- If the reference settles the factual core of a loaded or judgment question (e.g. a rumor that was made up),
  the reading criterion requires getting that fact right: treating a joke, lie or insult as true scores 0.
- total 8-10: correct ("good"), 4-7: partial ("weak"), 0-3: wrong ("poor"), the same bands as the score anchors (and as eval.grade save enforces). A transcript answer that refuses a
  judgment question though its passages had relevant evidence is wrong (failure refused_with_evidence).
- details: {"scores": {"position": n, "support": n, "reading": n, "counterpoint": n, "scope": n}, "total": n}


## Special cases

### False premise: false_premise (and any question whose premise turns out false)
- First check the premise yourself in the transcripts. It may be true even if the question's notes say it is false
  (q073: Kelly did marry Ryan, S7E14).
- Outcome: corrected (says the premise is wrong and gives what happened), accepted (answers as if true),
  over_rejected (rejects a premise that is true). v2: when the premise is TRUE and the answer accepts it, the outcome is
  accepted_true and it is graded as a fact (right = correct; q073); "accepted" as a failure only applies to a false premise.
- "Hinted or joked about in the show but never confirmed" is a correction when the answer says so clearly; it is
  acceptance only if the answer presents the premise as true.
- verdict: corrected and right about what happened = correct; corrected but wrong about what happened = partial;
  accepted or over_rejected = wrong.
- details: {"premise_true": bool, "outcome": "corrected|accepted|accepted_true|over_rejected|n/a"}

### Off-camera: off_camera (actors, awards, things after the show)
- Memory answers: grade as a fact (kind A).
- Transcript-only answers: saying the transcripts don't cover it is correct; inventing an answer from the passages
  is wrong (claim_beyond_evidence). v2: if the reference says the transcripts do cover part of it (q054, the finale), a
  transcript-only answer that gives the covered part is correct; one that says "not covered" because the scenes were never
  sent is partial, failure retrieval_miss. Using memory despite the rules: wrong, failure memory_in_rag.
- Both-sources answers: a correct answer marked [memory] is correct.


## By answer type

- **memory** (no transcripts): grounded = n/a. Also judge calibration: details.calibration = "ok" when its
  confidence matches correctness (knows_answer / uncertain list vs the verdict), "overconfident" when it claims to
  know and is wrong, "underconfident" when it says it doesn't know but is right.
- **transcripts** (passages only, strict): grounded = yes if every claim is supported by what it was sent (passages
  or SQL result), partly if some claims go beyond, no if the answer rests on unsupported claims. A refusal is
  correct only if the evidence really was not sent (check the scenes it was sent); then failure_type
  retrieval_miss still applies for the study, with verdict refused.
- **both** (passages + memory): grounded as above for cited claims; memory claims must be marked [memory]. Wrong
  labels (memory claim with a scene citation, or the reverse) make grounded = partly.


## Failure types (one main cause)

| failure_type | Meaning |
|---|---|
| retrieval_miss | the evidence needed was not in what the answer was sent; v2: also for a judgment answer that picked a weak candidate because the better evidence was not sent (q069, q070), unless a joke was read literally (literal_reading) |
| evidence_misread | the evidence was sent, but the answer got it wrong |
| literal_reading | sarcasm, insults, jokes or self-description taken as fact |
| invented_quote | quotes words that are not in the passages |
| claim_beyond_evidence | a transcript answer states something its evidence doesn't support |
| memory_error | memory is wrong, or overrode correct evidence |
| memory_in_rag | a transcript-only answer used outside knowledge |
| count_from_sample | a count or ranking taken from a few passages as if complete |
| premise_accepted | answered a false premise as true |
| premise_over_rejected | rejected a true premise |
| attribution_error | wrong episode, scene or speaker |
| incomplete | some required parts missing |
| refused_with_evidence | refused although the evidence was there |
| no_position | judgment question without a verdict |
| memory_unsure | v2: a memory answer that honestly says it does not know or declines to pick, when the answer exists (q044 memory) |
| other | anything else; explain in notes |


## Council (all questions)

Every question is graded by a council: three members, each looking through one lens, working independently (they
never see each other's notes), then a chair who decides. The members don't argue for any answer; each judges every
answer, but only on its own lens.

| lens | examines only | typical findings |
|---|---|---|
| fact | Is each claim true? Check against the reference and, where needed, the transcripts. Every part of the question answered? | wrong person, wrong number, wrong episode, missing part |
| faithfulness | Is the answer honest about its evidence? For transcript answers: every claim backed by what it was sent (passages, SQL result), quotes exact, no claim beyond the evidence, [memory] labels right, refusals justified. For memory answers: calibration (confidence vs correctness). | invented quote, count from a sample presented as a total, unlabelled memory claim, overconfident memory |
| reader | Does the answer understand the show and serve the person asking? Context of lines (sarcasm, jokes, insults, self-deprecation), sensible reading, completeness, directness; for judgment questions the five criteria (position, support, reading, counterpoint, scope). | a joke read literally, a judgment without a position, an answer that buries the point |

**Member note** (one per question, plain text, short): for each answer letter, a lens score 0-10 and one to three
findings, each with proof (a transcript scene checked in the database: season, episode, scene and the words; or
the reference). No proof, no finding. Judge only your lens; don't give an overall verdict. Not findings: episode
numbers in split numbering (The Duel = S5E11 here, S5E12 split; check the episodes table) and wording that differs
only in punctuation.

**Chair** (one pass, conclusive): read the reference and the three notes; where members disagree or a finding
would change the score, check it in the transcripts (a finding with a false proof is dropped); then give every
answer one final score 0-10 using the score anchors and the rubric for the question's kind, plus verdict, grounded,
failure_type (the main cause) and a one-to-two-sentence rationale. Don't average the lens scores: a fact error
weighs most, then faithfulness, then reading, unless the question is a judgment question, where reading weighs
most. Record the lens scores in details.lens_scores.
