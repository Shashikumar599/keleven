# Phase 0: Dataset comparison (Kaggle vs Hugging Face)
## 1. Basic stats
| metric | Kaggle | HF (all) | HF (aired only) |
|---|---|---|---|
| lines | 54626 | 59909 | 57973 |
| seasons | 9 | 9 | 9 |
| episodes | 186 | 186 | 186 |
| scenes (sum per episode) | 8157 | 9161 | 8849 |
| distinct speakers | 775 | 797 | 790 |
| empty lines | 6 | 0 | 0 |
| lines with [brackets] | 0 | 10062 | 9803 |
| lines with non-ASCII | 268 | 2583 | 2583 |

HF deleted-scene lines: **1936**

## 2. Unexpected Kaggle columns
- `unnamed: 6`: 17 non-empty values. Samples: [' how are you?', ' Alan and I will conduct your performance review over the phone tomorrow.', " I'm good. I can go home now.", " can we please not talk about paper? There's gotta be something else we can talk about.", " I'm stopping the car."]

## 3. Episode coverage
- Episodes only in Kaggle: [[3, 24], [4, 15], [4, 16], [4, 17], [4, 18], [5, 27], [5, 28], [6, 25], [6, 26], [7, 25], [9, 24]]
- Episodes only in HF: [[3, 11], [4, 2], [4, 4], [4, 6], [4, 8], [5, 2], [5, 15], [6, 5], [6, 18], [7, 12], [9, 23]]

Episodes where Kaggle differs from HF aired lines by more than 15% (70):

| season | episode | kaggle_lines | hf_lines_all | hf_lines_aired | diff_vs_aired_pct |
|---|---|---|---|---|---|
| 9.0 | 23.0 | 0.0 | 522.0 | 522.0 | -100.0 |
| 7.0 | 12.0 | 0.0 | 319.0 | 319.0 | -100.0 |
| 6.0 | 18.0 | 0.0 | 281.0 | 281.0 | -100.0 |
| 6.0 | 5.0 | 0.0 | 353.0 | 353.0 | -100.0 |
| 5.0 | 15.0 | 0.0 | 254.0 | 254.0 | -100.0 |
| 5.0 | 2.0 | 0.0 | 265.0 | 265.0 | -100.0 |
| 4.0 | 8.0 | 0.0 | 300.0 | 300.0 | -100.0 |
| 4.0 | 6.0 | 0.0 | 324.0 | 324.0 | -100.0 |
| 3.0 | 11.0 | 0.0 | 323.0 | 323.0 | -100.0 |
| 4.0 | 2.0 | 0.0 | 615.0 | 615.0 | -100.0 |
| 4.0 | 4.0 | 0.0 | 557.0 | 557.0 | -100.0 |
| 4.0 | 14.0 | 220.0 | 617.0 | 617.0 | -64.3 |
| 6.0 | 16.0 | 294.0 | 625.0 | 625.0 | -53.0 |
| 7.0 | 17.0 | 150.0 | 313.0 | 313.0 | -52.1 |
| 6.0 | 14.0 | 131.0 | 264.0 | 264.0 | -50.4 |
| 3.0 | 23.0 | 278.0 | 544.0 | 544.0 | -48.9 |
| 7.0 | 24.0 | 255.0 | 494.0 | 494.0 | -48.4 |
| 3.0 | 17.0 | 184.0 | 340.0 | 340.0 | -45.9 |
| 5.0 | 5.0 | 268.0 | 435.0 | 435.0 | -38.4 |
| 4.0 | 9.0 | 206.0 | 331.0 | 331.0 | -37.8 |
| 5.0 | 13.0 | 261.0 | 416.0 | 416.0 | -37.3 |
| 4.0 | 11.0 | 233.0 | 362.0 | 362.0 | -35.6 |
| 3.0 | 16.0 | 177.0 | 255.0 | 255.0 | -30.6 |
| 3.0 | 20.0 | 277.0 | 398.0 | 398.0 | -30.4 |
| 5.0 | 3.0 | 219.0 | 311.0 | 311.0 | -29.6 |
| 5.0 | 6.0 | 295.0 | 417.0 | 417.0 | -29.3 |
| 3.0 | 4.0 | 231.0 | 313.0 | 313.0 | -26.2 |
| 3.0 | 21.0 | 244.0 | 323.0 | 323.0 | -24.5 |
| 3.0 | 6.0 | 212.0 | 279.0 | 279.0 | -24.0 |
| 3.0 | 22.0 | 280.0 | 365.0 | 365.0 | -23.3 |
| 5.0 | 17.0 | 239.0 | 311.0 | 311.0 | -23.2 |
| 5.0 | 16.0 | 232.0 | 300.0 | 300.0 | -22.7 |
| 6.0 | 19.0 | 278.0 | 359.0 | 359.0 | -22.6 |
| 3.0 | 1.0 | 134.0 | 173.0 | 173.0 | -22.5 |
| 7.0 | 21.0 | 257.0 | 329.0 | 329.0 | -21.9 |
| 4.0 | 12.0 | 241.0 | 308.0 | 308.0 | -21.8 |
| 6.0 | 12.0 | 264.0 | 334.0 | 334.0 | -21.0 |
| 3.0 | 14.0 | 207.0 | 257.0 | 257.0 | -19.5 |
| 3.0 | 8.0 | 470.0 | 584.0 | 584.0 | -19.5 |
| 3.0 | 18.0 | 289.0 | 356.0 | 356.0 | -18.8 |
| 8.0 | 1.0 | 226.0 | 274.0 | 274.0 | -17.5 |
| 5.0 | 11.0 | 240.0 | 291.0 | 291.0 | -17.5 |
| 3.0 | 5.0 | 261.0 | 312.0 | 312.0 | -16.3 |
| 8.0 | 8.0 | 238.0 | 282.0 | 282.0 | -15.6 |
| 5.0 | 19.0 | 311.0 | 267.0 | 267.0 | 16.5 |
| 5.0 | 26.0 | 319.0 | 273.0 | 273.0 | 16.8 |
| 7.0 | 19.0 | 290.0 | 244.0 | 244.0 | 18.9 |
| 7.0 | 22.0 | 325.0 | 265.0 | 265.0 | 22.6 |
| 6.0 | 24.0 | 308.0 | 245.0 | 245.0 | 25.7 |
| 3.0 | 13.0 | 264.0 | 207.0 | 207.0 | 27.5 |
| 5.0 | 10.0 | 322.0 | 240.0 | 240.0 | 34.2 |
| 3.0 | 15.0 | 252.0 | 180.0 | 180.0 | 40.0 |
| 6.0 | 9.0 | 367.0 | 247.0 | 247.0 | 48.6 |
| 4.0 | 7.0 | 449.0 | 274.0 | 274.0 | 63.9 |
| 5.0 | 14.0 | 412.0 | 237.0 | 237.0 | 73.8 |
| 4.0 | 5.0 | 536.0 | 269.0 | 269.0 | 99.3 |
| 6.0 | 17.0 | 625.0 | 279.0 | 279.0 | 124.0 |
| 6.0 | 13.0 | 334.0 | 131.0 | 131.0 | 155.0 |
| 7.0 | 16.0 | 346.0 | 72.0 | 72.0 | 380.6 |
| 4.0 | 17.0 | 186.0 | 0.0 | 0.0 | 18600.0 |
| 6.0 | 26.0 | 245.0 | 0.0 | 0.0 | 24500.0 |
| 4.0 | 16.0 | 255.0 | 0.0 | 0.0 | 25500.0 |
| 5.0 | 28.0 | 270.0 | 0.0 | 0.0 | 27000.0 |
| 5.0 | 27.0 | 273.0 | 0.0 | 0.0 | 27300.0 |
| 4.0 | 15.0 | 305.0 | 0.0 | 0.0 | 30500.0 |
| 6.0 | 25.0 | 326.0 | 0.0 | 0.0 | 32600.0 |
| 3.0 | 24.0 | 491.0 | 0.0 | 0.0 | 49100.0 |
| 7.0 | 25.0 | 493.0 | 0.0 | 0.0 | 49300.0 |
| 4.0 | 18.0 | 516.0 | 0.0 | 0.0 | 51600.0 |
| 9.0 | 24.0 | 516.0 | 0.0 | 0.0 | 51600.0 |

## 4. Does Kaggle include deleted scenes?
- HF aired lines found in Kaggle: **50.6%** (of 42230 lines with 4+ words)
- HF deleted-scene lines found in Kaggle: **1.5%** (of 1391 lines)
- Reading: if the deleted rate is close to the aired rate, Kaggle includes deleted scenes. If it is near zero, Kaggle is aired-only.
- Kaggle lines found in HF: **53.4%** (of 40028 lines). Low overlap means different transcription sources or different cleaning.

## 5. Speaker name variants (main characters)
| character | Kaggle variants | HF variants |
|---|---|---|
| Michael | Michael:  (74), Michael and Dwight (11), Micheal (9), Video Michael (7), Michel (5), Dwight and Michael (5) | Michael and Dwight (11), Micheal (9), Video Michael (7), Dwight and Michael (6), Michel (5), Micahel (4) |
| Dwight | Dwight:  (34), Michael and Dwight (11), Dwight and Michael (5), Andy and Dwight (5), Dwight  (2), Michael & Dwight (2) | Michael and Dwight (11), Dwight and Michael (6), Andy and Dwight (5), Michael & Dwight (3), Dwight  (2), Jim, Pam, Michael and Dwight (2) |
| Jim | Jim:  (33), Fake Jim (6), Jim and Pam (4), Andy and Jim (4), Pam and Jim (2), Michael and Jim (2) | Fake Jim (6), Jim and Pam (4), Andy and Jim (4), Pam and Jim (2), Michael and Jim (2), JIM9334 (2) |
| Pam | Pam:  (31), Jim and Pam (4), Pam as "fourth-biggest client" (3), Pam and Jim (2), Jim, Pam, Michael and Dwight (2), Pam as "ninth-biggest client" (2) | Jim and Pam (4), Pam [on phone] (4), Pam as fourth-biggest client (3), Pam and Jim (2), Jim, Pam, Michael and Dwight (2), Jim & Pam (2) |
| Andy | Andy:  (35), Andy, Creed, Kevin, Kelly (5), Andy and Dwight (5), Andy and Jim (4), Andy & Michael (3), Andy & Erin (3) | Andy, Creed, Kevin, Kelly (5), Andy and Dwight (5), Andy and Jim (4), Andy & Michael (3), Andy & Erin (3), Andy & Walter (3) |
| Angela | Angela:  (17), Angela & Oscar (3), Anglea (1), Angels (1), Angela and Dwight (1), Angela and Kelly (1) | Angela & Oscar (3), Anglea (1), Angels (1), Angela and Dwight (1), Angela and Kelly (1), Dwight and Angela (1) |
| Kevin | Kevin:  (7), Andy, Creed, Kevin, Kelly (5), Kevin & Oscar (1), Phyllis, Meredith, Michael, Kevin (1), Andy, Creed, Kevin, Kelly, Darryl (1), Dwight, Erin, Jim & Kevin (1) | Andy, Creed, Kevin, Kelly (5), Kevin & Oscar (1), Phyllis, Meredith, Michael, Kevin (1), Andy, Creed, Kevin, Kelly, Darryl (1), Kevin & Andy (1), Dwight, Erin, Jim & Kevin (1) |
| Oscar | Oscar:  (20), Angela & Oscar (3), Kevin & Oscar (1), Oscar and Stanley (1), All but Oscar (1) | Angela & Oscar (3), Kevin & Oscar (1), Oscar and Stanley (1), Meredith, Creed, Oscar and Matt (1), All but Oscar (1), Darryl & Oscar (1) |
| Ryan | Ryan Howard (17), Ryan:  (5), Ryan and others (1), Michael, Pam & Ryan (1), Ryan and Michael (1), Ryan and Kelly (1) | Ryan Howard (17), Ryan and others (1), Michael, Pam & Ryan (1), Ryan and Michael (1), Ryan and Kelly (1) |
| Kelly | Diane Kelly (12), Andy, Creed, Kevin, Kelly (5), Kelly:  (4), Kelly and Erin (2), Andy, Creed, Kevin, Kelly, Darryl (1), Angela and Kelly (1) | Diane Kelly (18), Andy, Creed, Kevin, Kelly (5), Kelly and Erin (2), Andy, Creed, Kevin, Kelly, Darryl (1), Angela and Kelly (1), Ryan and Kelly (1) |
| Stanley | Stanely (2), Oscar and Stanley (1), Fake Stanley (1), Stanley:  (1), Phyllis, Stanley, Dwight (1), Phyllis, Kevin & Stanley (1) | Stanely (2), Oscar and Stanley (1), Stanley & Phyllis (1), Fake Stanley (1), Phyllis, Stanley, Dwight (1), Phyllis, Kevin & Stanley (1) |
| Phyllis | Phyllis:  (6), Phylis (2), Phyllis, Meredith, Michael, Kevin (1), Phyllis and Creed (1), Phyliss (1), Phyllis, Stanley, Dwight (1) | Phylis (2), Phyllis, Meredith, Michael, Kevin (1), Stanley & Phyllis (1), Phyllis and Creed (1), Phyliss (1), Phyllis, Stanley, Dwight (1) |
| Meredith | Meridith (2), Phyllis, Meredith, Michael, Kevin (1), Meredith:  (1), Kevin & Meredith (1) | Meridith (2), Phyllis, Meredith, Michael, Kevin (1), Meredith, Creed, Oscar and Matt (1), Meredith & Kelly (1), Kevin & Meredith (1) |
| Creed | Andy, Creed, Kevin, Kelly (5), Andy, Creed, Kevin, Kelly, Darryl (1), Phyllis and Creed (1), Creed:  (1), Robert & Creed (1) | Andy, Creed, Kevin, Kelly (5), Andy, Creed, Kevin, Kelly, Darryl (1), Phyllis and Creed (1), Meredith, Creed, Oscar and Matt (1), Robert & Creed (1) |
| Toby | - | - |
| Darryl | Daryl (37), Darryl:  (10), Andy and Darryl (3), Darrly (2), Darryl and Katy (1), Darry (1) | Daryl (37), Andy and Darryl (3), Darrly (2), Darryl and Katy (1), Darry (1), Andy, Creed, Kevin, Kelly, Darryl (1) |
| Erin | Erin:  (16), Andy & Erin (3), Dwight and Erin (2), Kelly and Erin (2), Michael and Erin (1), Andy and Erin (1) | Andy & Erin (3), Dwight and Erin (2), Kelly and Erin (2), Michael and Erin (1), Andy and Erin (1), Erin and Kelly (1) |
| Jan | Joan (5) | Joan (5), Jan [on phone] (1) |
| Holly | Molly (3), Holy (2), Michael & Holly (1), Michael and Holly (1), Michael, Holly, and Darryl (1) | Michael & Holly (4), Molly (3), Holy (2), Michael and Holly (1), Michael, Holly, and Darryl (1), Holly & Darryl (1) |
| Gabe | abe (1) | abe (1) |
| Nellie | Nellie Bertram (1), Nellie and Pam (1) | Nellie Bertram (1), Nellie and Pam (1) |
| Robert | Bert (19), Robert California (15), Robert Dunder (11), Robert & Creed (1) | Bert (23), Robert California (15), Robert Dunder (11), Robert & Creed (1) |

Multi-speaker labels (top 10):

Kaggle: Michael and Dwight (11), DunMiff/sys (6), Dwight and Michael (5), Andy, Creed, Kevin, Kelly (5), Andy and Dwight (5), Jim and Pam (4), Andy and Jim (4), Andy & Michael (3), Andy & Erin (3), Andy & Walter (3)

HF: Michael and Dwight (11), Dwight and Michael (6), DunMiff/sys (6), Andy, Creed, Kevin, Kelly (5), Andy and Dwight (5), Jim and Pam (4), Andy and Jim (4), Michael & Holly (4), Michael & Dwight (3), Andy & Michael (3)

## 6. Spot check: S2E1, first 15 lines

**Kaggle**

- [scene 228] Michael: Tonight is the Dundies, the annual employee awards night here at Dunder Mifflin.  And this is everybody's favorite day. 
- [scene 229] Jim: So, you ready for the... the Dundies?
- [scene 229] Pam: Ugh...
- [scene 230] Pam: You know what they say about a car wreck, where it's so awful you can't look away? The Dundies are like a car wreck that
- [scene 231] Michael:  Hey hey hey! It's Fat Halpert.
- [scene 231] Jim: What?
- [scene 231] Michael:  Fat Halpert.  Jim Halpert.
- [scene 232] Michael: So why don't I take you on a tour of past Dundie winners. We got Fat Jim Halpert here. Jim, why don't you show of your D
- [scene 232] Jim: Oh, I can't because I keep them hidden. I don't want to look at them and get cocky.
- [scene 232] Michael: Oh, that's a good idea.
- [scene 232] Dwight: Mine are at home in a display case above my bed.
- [scene 232] Michael: Gyaaah. T.M.I. T.M.I my friends.
- [scene 233] Michael: T.M.I.? Too much information. Ah, it's just easier to say T.M.I. I used to say "Don't go there" but that's... lame.
- [scene 234] Michael: And here we have Stanley the Manly. Now Stanley is a Dundie all-star, aren't you Stan? Why don't you, ah, show them some
- [scene 234] Stanley: I don't know where they are, I think I threw them out.

**HF (aired)**

- [scene 1] Michael: Tonight is the Dundies, the annual employee awards night here at Dunder Mifflin. [holds up a trophy of a business man] A
- [scene 2] Jim: So, you ready for the... the Dundies?
- [scene 2] Pam: Ugh...
- [scene 3] Pam: You know what they say about a car wreck, where it's so awful you can't look away? The Dundies are like a car wreck that
- [scene 4] Michael: [in a Fat Albert voice] Hey hey hey! It's Fat Halpert.
- [scene 4] Jim: What?
- [scene 4] Michael: [in Fat Albert voice] Fat Halpert. [in normal voice] Jim Halpert.
- [scene 5] Michael: So why don't I take you on a tour of past Dundie winners. We got Fat Jim Halpert here. Jim, why don't you show of your D
- [scene 5] Jim: Oh, I can't because I keep them hidden. I don't want to look at them and get cocky.
- [scene 5] Michael: Oh, that's a good idea.
- [scene 5] Dwight: Mine are at home in a display case above my bed.
- [scene 5] Michael: Gyaaah. T.M.I. T.M.I my friends.
- [scene 6] Michael: T.M.I.? Too much information. Ah, it's just easier to say T.M.I. I used to say 'Don't go there' but that's... lame.
- [scene 7] Michael: And here we have Stanley the Manly. Now Stanley is a Dundie all-star, aren't you Stan? Why don't you, ah, show them some
- [scene 7] Stanley: I don't know where they are, I think I threw them out.
