You are building a fact database from the transcript of ONE episode of a TV show. The facts will later be used to
answer detailed questions about the show, such as "Whom did X marry?", "Who did Y date?", "What happened to Z after
the breakup?". So every fact must be supported by specific lines of this episode, and nothing may be invented: a
wrong fact in the database makes a later answer wrong, while a missing fact only makes it less complete. When in
doubt, leave it out.

You return one JSON object in the schema you are given. You do NOT answer questions and you do NOT write prose
outside the JSON.


## The show and how to read it

The show is a workplace sitcom in a mockumentary style. Characters talk to the camera in short interviews (talking
heads) and talk to each other in the office. Most lines are jokes, sarcasm, exaggeration, awkward bluffing, pranks and
lies. Characters often say the opposite of what they mean, insult each other as a joke, boast, show off and play
roles. The characters are goofy and flawed. Friendships, rivalries, romances and the work hierarchy develop slowly
over many episodes: hints and jokes come long before anything is official, and a joke about a relationship is NOT a
relationship.

How to read it:

- Sarcasm, jokes, insults, lies, boasts, role-play (a game, a prank, a costume) and exaggerations are not facts. If you
  report something that comes from one, mark its certainty `joke_or_false`.
- A character's description of themselves or of someone else is that character's claim, not a fact. A statement to the
  camera is that character's view.
- A fact is `stated` when the lines say it plainly or show it plainly (stage directions in [brackets] count). It is
  `implied` when a reasonable reader would infer it from the lines but nobody says it.
- The episode text below is your only source of information. Report only what its lines and stage directions say or
  show; anything that is not in them is not reported.


## What you are given

1. The speaker labels used in this episode, with how many lines each has (a hint about who speaks; labels can be
   first names, full names or generic words like "Man").
2. The episode text, scene by scene. Every line starts with its id in brackets: `[L40213] Jim: ...`. Stage directions
   are in [brackets] inside the line.


## What to return

### summary
Two to five sentences, at most 120 words: what happens in this episode.

### characters
People only. Each person who speaks or acts in this episode, and each person who is only mentioned and matters to an
event or a relation. One entry per person in THIS episode. Do not try to work out who they are in other episodes:
describe what this episode shows, and a later step links them.

For each:
- `local_id`: c1, c2, ... (only meaningful inside this episode).
- `names`: every name or label used for them in this episode (speaker label, full name, nickname, "the senator").
- `description`: one phrase of at most 15 words that STARTS WITH A VERB in the third person, saying what this person
  does in this episode (for example "Phones Michael and asks him to come to a meeting", "Searches the city for
  Michael"). Never start with a noun or a title. Give no job, rank, department or relationship to other people unless
  a line in this episode says it.
- `present`: true if they speak or appear in this episode, false if they are only talked about.
- `lines`: up to five line ids where they appear or are mentioned.

Groups ("everyone", "the sales team") are not characters. If two different people share the same name in this episode, make two entries. If one person is called by two names in
this episode, make one entry with both names. If you are not sure whether two names are the same person, make two
entries.

### places
Where things happen. Each distinct place the episode shows or talks about that matters to an event: a room or area of
the workplace, a building, someone's home, a restaurant, a vehicle, a town. Companies that are only mentioned (no
location) are listed here too, with kind organization. Not people.

For each:
- `local_id`: p1, p2, ... (only meaningful inside this episode).
- `name`: as used in the lines or stage directions ("the office", "the warehouse", "Jim's house", "the conference room").
- `kind`: workplace (a room or area of an office, warehouse or other place of work), home, public (a shop, a street,
  a rooftop, a restaurant, a vehicle), organization (a company mentioned without a location) or other.
- `description`: a short phrase of at most 10 words saying what happens there in this episode.
- `lines`: up to three line ids that show or mention it.

### events
The things that happen that matter for the story. Report:

- changes in a relationship (a first date, a kiss, a proposal, a breakup, a wedding, a divorce, a fight and its end);
- changes in work (hired, fired, quits, promoted, a new boss, a transfer, a business starts or closes);
- conflicts, pranks and schemes that have consequences or involve a named target;
- reveals and secrets (something becomes known to someone);
- milestones and births, deaths, moves, trips and parties that matter to a character.

Do not list every gag or every line of banter. Keep at most about 25 events per episode.

For each event:
- `id`: e1, e2, ... in the order they happen.
- `text`: one sentence, at most 25 words, past tense, with the characters' canonical names, readable on its own without
  the rest of the episode (not "he did it again").
- `kind`: one of romance, job, conflict, prank, milestone, family, other.
- `place`: the `local_id` of the place where it happens, or null if the lines do not say or it happens in several
  places.
- `participants`: who is involved: `{"character": "<local_id>", "role": "agent | patient | subject | witness"}`.
  agent does it, patient has it done to them, subject is who it is about, witness is present but not involved.
- `lines`: the ids of the lines that support it (numbers, without "L"), the fewest that prove it. Only ids that appear
  in the text.
- `certainty`: stated, implied or joke_or_false (see above).
- `importance`: judged only by this episode. "major" if the event is one of the main storylines of this episode (it
  takes up several scenes, or it is what the episode is about), or if it changes something lasting that the lines
  state: someone is hired, fired, quits or is promoted; a relationship begins or ends; a wedding, birth, death or move;
  a secret is revealed to the people it matters to. Usually two to six events per episode are major. Everything else is
  "minor". A relationship or a work status (job, rank) that begins or ends in this episode is always "major". You
  cannot know from one episode how an event matters later, so do not guess; use only what happens here and how much
  of the episode it takes.

### relations
A relation is a lasting link between two characters. Allowed types only:

- crush: one has romantic feelings for the other, said or shown, not yet together
- dating: a romantic relationship (together, in a couple, seeing each other)
- engaged: promised to marry
- married: married to each other
- family: related (parent, child, sibling, cousin, in-law); say which in `detail`
- boss: `a` is the boss of `b` (directed)
- rival: a lasting rivalry or enmity
- friend: a lasting friendship

A breakup, a called-off engagement or a divorce is not a separate type: report the relation that ended (dating,
engaged or married) with `change` = ends.

Report a relation ONLY if this episode states it, shows it or changes it. Do NOT report a relation just because both
characters appear in the episode. If nothing changes, return an empty list: most episodes have few.

For each relation:
- `a`, `b`: local ids (for boss, `a` is the boss).
- `type`: from the list above.
- `change`: begins (it starts in this episode), ends (it ends in this episode) or revealed (it already existed and
  a line in this episode tells us so for the first time). A relation that exists and does not begin, end or get
  announced here is NOT reported, even if the two people appear together.
- `detail`: a few words if needed (for family, which relation), otherwise null.
- `lines`: the supporting line ids.
- `quote`: for these relations, a short exact quote (at most 12 words) copied from one of the lines, otherwise null.
- `certainty`: stated, implied or joke_or_false.

A relation is `stated` only when a cited line says it in words or a stage direction shows it. If the lines only fit
it (a situation, a gesture, a tone), mark it `implied`. If the lines do not show it, leave it out. Every relation
must be backed by the lines you cite, not by anything else.

If an episode announces both that a relationship existed and that it is over, report two rows for the same pair: one
with `change` = revealed and one with `change` = ends.

If a marriage, engagement or relationship is only joked about, mark it `joke_or_false` or leave it out. A wedding
that is announced but not shown still counts if a character states it.

### refers_back
Lines where a character points back to something that happened earlier (an earlier episode or an earlier event in
this one): "remember the gas station?", "like last year's Christmas party". You cannot know which earlier event it is;
do not guess. Write the pointer: `{"event": "<id of the event it belongs to, or null>", "text": "<the words>",
"lines": [..]}`. Leave empty if there are none.



## Rules that matter most

1. Only what this episode's lines support. No guessing and no filling gaps.
2. Every event and every relation needs `lines` that really contain it. Do not cite lines you did not read.
3. Jokes, sarcasm, lies and role-play are `joke_or_false`; they never start or end a relation.
4. Every participant and every relation end must be a `local_id` you defined in `characters`, and every `place` one
   you defined in `places`. Never merge people across episodes and never say more about who a character is than this
   episode shows.
5. Fewer and correct beats more and doubtful. An empty list is a valid answer.
