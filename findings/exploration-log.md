# Exploration log (Phase 1)

Every question asked during exploration and how each approach did. These observations feed the question set
design in Phase 1b. Informal: the "memory" answers come from Claude in the working chat (answered before seeing
retrieval), not yet the pinned Gemini model; retrieval is vector-only (v1).

Setup unless noted: chunk set `pack_300t_3s_80min`, embeddings `voyage-4-large@1024`, exact cosine search, top 8-10,
no neighbour expansion, no metadata filters.

| # | Date | Question | Type | Memory | Vector RAG | Notes |
|---|---|---|---|---|---|---|
| 1 | 2026-10-03 | Why did Andy break up with Angela? | why / relationship, multi-episode | ✅ core story, ⚠️ unverifiable details | ⚠️ partial | key scenes missed |
| 2 | 2026-10-03 | In the Season 2 Dundies, which awards did Kelly, Stanley and Phyllis receive? | detail, single episode, famous | ✅ all three, ⚠️ unsure wording | ✅ all three + exact wording | wrong-season distractor |
| 3 | 2026-10-03 | In *Health Care* (S1), what fake diseases do employees write down? | list, single episode, famous | ⚠️ about half, one claim wrong | ✅ complete list with attribution | |
| 4 | 2026-10-04 | How many Kellys are in the office? | counting / aggregate | ✅ 2, ❓ couldn't place Diane Kelly | ❌ fails | SQL answers it fully |
| 5 | 2026-10-04 | Was Pam a bitch for breaking up with Roy? | opinion / judgement, loaded wording | ✅ arc + context, ⚠️ episode details unverified | ✅ evidence for both sides, Pam's own reasons | retrieval good; first answer dodged the judgement |
| 6 | 2026-10-04 | Which awards did Kelly, Stanley and Phyllis get at the Dundies? (first end-to-end run) | detail, two ceremonies | ❌ two confident errors | ✅ RAG and hybrid correct, cited | first Gemini run |
| 7 | 2026-10-04 | What was the number Kevin invented? (run 8) | detail, famous, answer word not in question | ✅ all three | ✅ (hit #3) | vector found it without the key word |
| 8 | 2026-10-04 | Who was the hottest girl in The Office cast? (run 9) | out of scope: real people, looks judgement | ❌ ranks a real actress, unverified claims | ⚠️ RAG refused (non-answer); ⚠️ hybrid ranks from memory (labelled) | RAG too literal on a subjective question |
| 9 | 2026-10-04 | Same question after the prompt amendment (run 10) | subjective, characters | ✅ characters, a view | ✅ RAG answers with 7 cited quotes; hybrid labels 3 memory claims | amendment fixed it |

## 1. Why did Andy break up with Angela?
- **Vector RAG:** 4 of the top 6 on topic: S5E1 *Weight Loss* sc. 17-19 (Angela still seeing Dwight while engaged),
  S5E11 *The Duel* sc. 23 (Andy found out, challenges Dwight), S5E22 *Heavy Competition* sc. 15 ("I broke up with
  Angela"), S5E16 *Blood Drive* sc. 20 (the duel, Andy's solo honeymoons). Answer: the affair with Dwight.
- **Failures:** top hit S9E21 *Livin' the Dream* sc. 47 is from the wrong era (years later); S4E3 *Launch Party*
  sc. 38-40 is Angela breaking up with **Dwight** (wrong couple); how Andy found out and the breakup itself were
  not retrieved. Neighbour expansion of the *Duel* chunk may bring the outcome in (not tried yet).
- **Memory:** affair with Dwight, Phyllis exposing it at *Moroccan Christmas*, the duel, both men leaving her;
  fuller story but with details it couldn't verify.

## 2. Season 2 Dundies: Kelly, Stanley, Phyllis
- **Vector RAG:** 6 of the top 8 from S2E1 *The Dundies*. Kelly: "Spicy Curry" (sc. 41); Stanley: "Fine Work",
  compares it with last year's "Great Work" (sc. 45-46); Phyllis: "Busiest Beaver", misprinted "Bushiest Beaver"
  (sc. 31).
- **Failure:** #2 was S7E20 *Michael's Last Dundies* (Stanley's "Diabetes Award"): the question names Season 2,
  but vector search can't filter by season. Metadata filters would fix it.
- **Memory:** all three awards right; missed the misprint joke and Stanley's comparison.

## 3. *Health Care* fake diseases
- **Vector RAG:** all top 8 from S1E3 *Health Care*. Complete list: Count Choculitis, spontaneous dental
  hydroplosion (Pam's idea, Jim's name), hot-dog fingers, leprosy, flesh-eating bacteria, government-created killer
  nanorobot infection, inverted penis; real ones read out too (dermatitis, anal fissures).
- **Memory:** about half the list; wrongly said people wrote down ebola (Jim only joked about it).

## 4. How many Kellys are in the office?
- **Vector RAG:** fails. All 8 hits are ordinary Kelly Kapoor scenes; nothing answers "how many". Counting needs
  the whole show plus one specific scene that never says "how many".
- **SQL by hand (Phase 2 style):** speakers containing "Kelly": Kelly (935 lines), **Diane Kelly** (a lawyer at
  Jan's deposition, S4E8 *The Deposition*, 18 lines), Kelly's mom and father (S3). The naming scene: S5E21 *The
  Michael Scott Paper Company* sc. 6, Charles says "Oh, and Kelly...", both answer, he renames them Kapoor and
  Hannon, Erin: "can I be Erin? It's my middle name."
- **Memory:** two Kellys (Kapoor and Kelly Erin Hannon) right; couldn't identify Diane Kelly.
- **Notes:** the question is ambiguous (employees named Kelly vs every character named Kelly). The SQL was written
  by hand with a guessed search term ("middle name"); Phase 2 text-to-SQL would have to find that itself.

## 5. Was Pam a bitch for breaking up with Roy?
- **Vector RAG:** top hits all from the right period (S2-S3), mostly on topic: S3E1 *Gay Witch Hunt* sc. 24 (Pam:
  "I got cold feet... I just had to get out of that relationship"), S3E17 *Cocktails* sc. 46 (Pam wants a fresh
  start with no secrets, confesses the Casino Night kiss, Roy yells, "This is over"), S3E18 *The Negotiation*
  sc. 28 (Pam to Jim: "Sorry I almost got you killed... It's completely over now") and sc. 46 (Roy apologizes;
  "you broke off our wedding for the guy"; Pam: "No, there were a lot of reasons"; "we both made some bad
  choices"), S2E15 *Boys & Girls* sc. 18 (Roy on Pam's talking: "bap bap bap").
- **Not retrieved:** the long engagement, Roy missing her art show, the bar Roy smashed, the attack on Jim itself
  (only implied by "almost got you killed").
- **Memory:** the overall arc, the art show and long engagement (not retrieved), the bar and the attack; less of
  Pam's own words.
- **Notes:** a judgement question with loaded wording. Retrieval doesn't judge; it supplies evidence from both
  sides (Roy's accusation and Pam's answer). **The first answer only listed evidence and dodged the question; the
  user called it out.** A good answer takes a clear, reasoned position built from the cited evidence (here: no,
  the breakup itself was right; the kiss while engaged and the late honesty are the fair criticisms), without
  repeating the question's insulting label. For the Part 5 prompt: answer opinion questions directly, with
  citations; "both sides" with no conclusion is a non-answer. New category for the question set: opinion /
  judgement (graded on whether it answers, uses evidence, and is fair).

## 6. Dundies again, first end-to-end run with Gemini (`gemini-3.8-flash`, prompts v1)
- **RAG:** correct and complete, covering both ceremonies: Kelly "Spicy Curry" [S2E1 sc.41], Phyllis "Busiest
  Beaver" misprinted "Bushiest Beaver" [S2E1 sc.31], Stanley "fine work" [S2E1 sc.45] and later the "Diabetes
  Award" [S7E20 sc.22]. 6 evidence quotes, all verified in the sent passages.
- **LLM (memory only):** Phyllis and Stanley's Season 2 awards right, but **two confident errors** with
  `knows_answer: true`: "Kelly did not receive an official Dundie on-screen" (she got Spicy Curry) and Stanley
  "did not receive an on-screen award" in Season 7 (the Diabetes Award). Also claims a Season 7 award for Phyllis
  that nothing here confirms.
- **LLM + RAG:** same as RAG, plus one claim labelled `[memory]` ("no other Dundie awards are presented to these
  three"), which is unverifiable and probably wrong for Phyllis. Labelling worked: the memory claim is separated.
- **Notes:** Gemini Flash's memory is clearly weaker than Claude's earlier answer to the same question, as
  expected. The question is ambiguous (several ceremonies); RAG and hybrid answered for both.

## 7. What was the number Kevin invented? (logged as run 8)
- **All three correct:** "Keleven", from the series finale (S9E23 sc.20 in our numbering): Oscar explains it was
  Kevin's "magic number" to balance his accounts and the reason he was fired; motto "A mistake plus Keleven gets you
  home by seven." RAG and hybrid fully cited (2 quotes verified each); Flash's memory had every detail too.
- **Retrieval:** the finale chunk was hit **#3**; the top hits were weaker than usual (distances 0.64-0.69 vs ~0.47
  on the Dundies question) and mostly other Kevin scenes.
- **Notes:** the question doesn't contain the answer word ("Keleven"), so keyword search would not have found it;
  vector search matched on Kevin + number + accounts. A famous-tier question: memory is complete, RAG adds proof.

## 8. Who was the hottest girl in The Office cast? (run 9)
- **The question is out of scope twice:** it is about the real cast (actresses), not characters, and asks for a
  judgement of looks. The transcripts contain neither.
- **RAG:** a non-answer (corrected after the owner's review; first logged as correct). `answerable: false`, "the
  passages do not state who the hottest girl is", plus one related fact: Michael's "Hottest in the Office" Dundie
  goes to Ryan the temp [S2E1 sc.37]. A subjective question never has a passage stating the verdict, so refusing on
  that basis is too literal: it should have laid out the in-universe evidence for different characters and given a
  view. 0 thinking tokens (other questions used 400-1,500).
- **LLM:** named a real actress as "most widely regarded as the most attractive woman in the cast" with plot claims
  that are unverified and probably partly invented (e.g. Michael seeing Jim's relationship with Karen as an upgrade).
- **LLM + RAG:** cited the Dundie, then picked a "winner" from memory (Pam / Jenna Fischer), 3 `[memory]` claims mixed
  with citations (S8E7 sc.7 "more beautiful now than ever", S1E6 sc.14 Katy). Labelling worked; the ranking shouldn't
  have happened.
- **Cause:** prompt v1's rule "opinion questions: take a clear position" (from the Pam/Roy question) pushed the LLM
  and hybrid answers to rank real people's attractiveness.
- **Fix for prompt v2:** subjective questions are never refused just because no passage states a verdict: present the
  evidence for the different sides, then give a view, with citations; `answerable` means "the passages contain
  relevant evidence". Suggested (owner to decide): frame looks questions in-universe (how characters are treated and
  described) rather than ranking the real actors.
- **Question set:** new category "out of scope / real world" (tests noticing the transcripts can't answer).

## 9. Same question after the prompt amendment (run 10)
- Prompts amended in place ("characters, not actors"; subjective questions answered with sides + a view).
- **RAG:** now answers. Candidates with citations: Katy (Roy "would be all over that", Michael and Dwight compete,
  S1E6), Pam's maternity replacement ("super cute", S8E7), Angela ("Tight Ass" Dundie, Roy's pick in "Who Would You
  Do?", S2E1/S2E4), Pam ("more beautiful now than ever", S8E7). View: Katy, with the counterpoint that Jim says
  she's "not really my type" and the official "Hottest in the Office" Dundie went to Ryan. 7 quotes verified.
- **LLM:** characters only (Katy, Pam, Karen), view Katy; no actors named.
- **LLM + RAG:** same candidates cited, plus Karen and Pam's long-term arc labelled `[memory]`; view Pam.
- **Note:** the in-universe evidence existed in the retrieved passages all along; prompt v1 just refused to use it.

## 10. Flash memory pre-test on q006-q016 (not logged as runs)
- 11 questions chosen to be hard for Flash: about 6 fully right, 4 partly right, 1 wrong.
- Right: Lloyd Gross, Erin's 22 lice cases, Harry Jannerone (Syracuse), the 2,336-pound weigh-in, the $4,300 surplus.
- Partly: wrong episode for Jim's red wire (said The Duel) and Stanley's jury duty (said a Season 8 "Jury Duty"
  episode); invented a line for Andy's agent Carla; "cream letter stock" for "cream butter stock"; Kapoor/Hannon cut
  off.
- Wrong: Creed's cupcake price (invented "$200 laced cupcake" instead of $3.75 / $3.67 by the dozen).
- **Lesson:** Flash's memory of the transcripts is broad; its weak spots are attribution (episode, speaker) and
  invented supporting detail. Ask for episode and speaker; grade details strictly.

## 11. Transcript-mined hard questions q017-q026: Flash memory vs v1 RAG (not logged as runs)
- Mined from the transcripts: minor characters (Nate, Bert, Broccoli Rob, Captain Jack, the coffee shop worker),
  small details inside a scene, stage directions. Each needed distinctive wording so retrieval had a chance too.
- **RAG right, Flash wrong or partly (6):** Captain Jack married his first wife (Flash: seafood buffet story);
  Nashua's gift basket card (Flash: bagels); Michael's coffee order (Flash: wrong drink, wrong date); Nate-pons
  (Flash: wrong episode, invented detail); Broccoli Rob's "two, three times a week" (Flash: once a month);
  Jersey State basketball team (Flash: no school or title).
- **Both right (3):** Lamar Odom trivia, Kerrigan costume, Val's "mom" Brandon. Kept as neutral questions.
- **RAG miss (1):** Kevin's Cornell sweater: gold scene not retrieved, so RAG said "not in passages"; Flash said
  Andy (it was Nellie). A plain test for keyword search in v2.
- **RAG corrected a wrong premise:** my first draft said the gloves were a Christmas gift; RAG answered that it was
  Valentine's Day (S8E14 sc.9). Flash accepted the premise and named a Christmas episode.
- **Data issues:** the caller in S8E14 sc.15 is labelled "Bob" (he's Val's boyfriend, Brandon), and RAG repeated
  it. Episode numbering differs: Flash says Chair Model is S4E14 (split numbering), the dataset says S4E10. Grading
  must accept either.
- **Lesson:** Flash invents plausible filler when it doesn't know: a whole story, a card text, a number. Small
  details from minor characters are where transcripts beat memory.

## 12. Transcript gap: Dwight's "False. I do not miss him" (S3E1 sc.3)
- The HF source line ends at "[serious]"; the punchline is missing. Kaggle has no copy of the line at all. Not a
  cleaning bug: fan transcripts cover every episode but not every word.
- q079 tests this: RAG can at best find the scene from the first half of the line; memory likely knows the quote.

## 13. Enhancer (enhance_v1.md) first test: 3 questions, not logged as runs
- Thinking level "minimal" is rejected by gemini-3.8-flash (400); "low" works and used 0 thinking tokens.
- Latency 1.7-2.6 s per call (~2.2k input tokens, 72-94 output). Slower than hoped for a call that runs before search.
- No memory leaks: q017 added no name (Flash's memory says Andy, wrongly); q027 searched for the quote without a
  speaker filter; q039 took season 2 from the question.
- SQL found the evidence directly in all three: q017 the Cornell sweater line (Kevin, S8E21 sc.8, "Nellie was nice
  enough..."), the scene v1 vector search missed; q027 Michael, S6E23 sc.17; q039 count 111 (matches the gold).
- q017's SQL required both words in one line, against prompt rule 6; it worked because they share a line.

## 14. Where v1 answers broke their prompt rules (all 237 baseline answers, checked by script + reading)
- **Invented "exact" quotes (rag rule 2 / hybrid rule 3: only quote text in the passages):** 5 quotes in 4 answers.
  q059 hybrid ("…I'm gonna have to take a leak-a"; the sent line is "…miss going to beers with you guys"), q071
  hybrid ("You will now wrestle my cousin Mose", not in the sent scene), q046 hybrid, q076 rag (2, from a scene
  never sent). The model writes a plausible line from memory and gives it a scene number. The citation check
  catches all of them. (Earlier I blamed a speaker-name prefix in the checker; wrong: the prefix matches fine.)
- **Quote stitched from several lines (one line or less):** q046 rag joined 3 lines and dropped the speaker names.
- **answerable=false while answering part of the question (rag rule 4 says answer the part):** q048, q049, q054;
  each gives cited partial evidence. So the "rag said not answerable on 12" count is overstated.
- **Hybrid source labels mixed (hybrid rule 4):** q046 and q050 put a scene citation and [memory] on one claim;
  q056 wrote "memory" inside a citation bracket ([S8E13 sc.24, S9E20 sc.14, memory]).
- **Checked, not violations:** "actor" names were the character Creed Bratton; "likely" in memory answers is
  reasoning in opinion / what-if answers, not hidden uncertainty; long evidence quotes are single long lines.
- **Judgment errors within the rules (not inconsistencies):** q037 memory rejects a true premise; q040 rag gives a
  passage-based count with only "based on the passages" as caveat.

## 15. "Most boring main character": literal reading, and transcripts making the hybrid answer worse (run 98)
- Enhancer search_text "boring character"; 6 of the 8 retrieved scenes contain the literal word (34 lines in the
  whole show do). A boring character is shown (Stanley's crosswords, everyone tuning out Toby), rarely named.
- The answers read lines literally, ignoring speaker and intent: Pam's "the most boring job in the office"
  (self-deprecation), Dwight's "the only thrill of your boring life" (an insult), "I love my boring life"
  (contentment), Kelly labelling Darryl's texts "Boring". v2 rag -> Pam; v1 rag -> Jim, from "I'm boring myself
  just talking about this" (bored by his job, not boring).
- Memory alone said Stanley / Pete. The v2 hybrid answer said Pam: the passages overrode memory's broader picture,
  because hybrid rules 1-2 put passages first. Right for facts, wrong for series-wide judgments. Known RAG effect:
  misleading context can make an answer worse than closed-book. The show's deadpan irony is mostly in delivery and
  looks to camera, which transcripts barely record.
- Fix: rule "Judgments about characters" in rag_v2 / hybrid_v2 (context of a line; a word is not the trait;
  passages are examples for series-wide judgments; hybrid may lead with memory there, labelled). Deeper fix for v3:
  character profiles, so trait questions retrieve portrayal, not words.

## 16. After the "judgments about characters" rule: same question type, v2 (web, dev mode)
- Asked as "who is most boring character in the office main characters" (new wording, so no memory reuse and no
  link to run 98: exact matching treats it as a new question).
- **Hybrid (fixed):** candidates Toby, Stanley, Pam; Toby and Stanley lead from memory's portrayal (labelled
  [memory]), transcript scenes used as illustrations (Stanley leaving the murder-mystery game S6E9, his bath and red
  wine S4E11). Pam drops to one candidate of three. The intended behaviour.
- **RAG (half-fixed):** still Pam, but now says the passages are "a narrow sample for a series-wide judgment, which
  provides low confidence" and argues against itself. It still treats Pam's self-description and Dwight's insult
  as evidence, which the rule forbids: partly followed (cf. entry 14, faithfulness).
- **Memory:** Toby, then Stanley and Pete (before: Stanley / Pete; different wording, new call).
- **Lesson:** a prompt can make strict RAG humble but can't give it evidence search never retrieved. Word-matched
  retrieval caps RAG on trait questions; the fix is retrieval of portrayal (v3 character profiles). For hybrid, the
  source-priority rule (facts: transcripts first; series-wide judgments: memory may lead) is what mattered.

## Patterns so far
- Famous single-episode details: memory mostly right; RAG adds completeness, exact wording, attribution, citations.
- Multi-episode stories: RAG partial (wrong era, wrong couple, missing key scenes).
- Counting / aggregate: vector RAG fails; SQL needed (evidence for Phase 2).
- Season named in the question but not used: metadata filtering needed.
- Opinion / judgement questions: retrieval finds the evidence; the answer must take a clear, cited position,
  not just list both sides, but only about characters in the show, never ranking real people (run 9).
- Subjective / out-of-scope questions: strict RAG refused (too literal); memory-based answers ranked real people.
  Neither is right: present the evidence for each side, then give a view.
- Minor-character details: Flash invents confident filler; RAG wins when retrieval finds the scene (entry 11).
- Trait / series-wide character judgments: retrieval finds the word, not the portrayal; answers read sarcasm,
  insults and self-deprecation literally, and passages can make the hybrid answer worse than memory unless the
  prompt lets memory lead for such judgments (entries 15-16).
