# Twelve questions (ten graph-oriented, two added by the owner): DRAFT for the owner to edit

Status: candidates only. No gold answers and nothing is verified. `eval/questions.jsonl` is not touched.
Planned use: held-out test set for v3 (split `test`), never used for tuning. Run v2 and v3 on them, grade both together, blind.

How these were chosen
- Written from general knowledge of the show's structure, before looking at any graph output for them, so the graph did not shape them.
- None repeats an existing question (q045, q046, q050, q058, q072, q073, q077 and q078 were checked) or an example in `enhance_v3.md`.
- They differ in shape: lists across many seasons, a history between two people, one timeline in order, one ordering, one arc of events.
- Each needs facts from several episodes, which one search of 8 chunks tends to miss. Some may still be easy for v2; that is useful too.
- g11 and g12 were added by the owner. They are not graph-shaped (a causal explanation and a character judgment), so they act as controls: the graph is not expected to help, and v3 should not do worse than v2 on them.

| id | category | question | why it suits a graph | what the gold answer must settle (owner checks in the transcripts) |
|---|---|---|---|---|
| g01 | list | With whom does Dwight have a romantic relationship over the series? | one person, several partners, many seasons | every partner and the season; decide whether short flings count |
| g02 | list | Which couples get engaged over the series? | a relation type across the whole show | each couple, the episode, and whether the engagement ends in marriage or breaks off |
| g03 | list | Which couples get married over the series? | same, a different relation type | each couple and the episode of the wedding; decide whether a joke or a fake wedding counts |
| g04 | story_arc | What is the history between Jan and Michael across the series? | a pair with begin, end and reunion over several seasons | the start, the break-ups, the reunion, how it ends |
| g05 | story_arc | How does the relationship between Andy and Erin change over the series? | a relationship with several changes | the key changes in order, with episodes |
| g06 | list | Which marriages and affairs of Stanley are shown over the series? | several relations of one person, partly off-screen | each person involved, the episode, and how each ends |
| g07 | story_arc | How does Jim and Pam's relationship progress from the first season to the end? Give the key episodes. | one pair through four relation types | crush, dating, engagement, marriage, with the episodes; major setbacks |
| g08 | list | Who were Michael's bosses over the series? | boss relation over time, several people | each boss and the period; decide whether acting or corporate heads count |
| g09 | list | Whom does Angela date or marry over the series? | one person, several partners and overlaps | each partner, the period, and the overlaps or affairs |
| g10 | order | Did Angela get engaged to Andy before or after she broke up with Dwight? | two dated events of one person, order matters | both events with episodes; the order |
| g11 | why | Why did the Scranton branch always perform better than the rest? | an explanation that spans many scenes; the premise ("always better") may be only partly true | whether the show supports "always" (which branches, which periods); the causes the show gives or implies; no single stated cause is likely |
| g12 | opinion | Was Angela toxic and mean? | a judgment about one person built from many scenes; loaded wording | a position with the strongest scenes on each side (cruelty, and the moments that soften her); jokes and insults are not a verdict (same rules as q066, q069, q080) |

Notes for editing
- Change the wording freely; keep each question answerable from the transcripts.
- Where a question hinges on a judgment (a fling, a joke wedding, an acting boss), write that rule into the gold answer, as for q044 and q046.
- If a question cannot be answered from the transcripts at all, replace it; a question that no system can answer tells us nothing about the graph.
- Gold answers must be written by you. Claude may only draft them, and they stay unverified until you confirm.
