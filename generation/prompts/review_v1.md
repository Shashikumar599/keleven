You are checking a fact extraction against the transcript of ONE episode of a TV show. Someone else read the episode
and wrote the extraction (characters, places, events and relations). The extraction will be stored as a fact database
and used to answer detailed questions about the show, so every detail in it must be shown by this episode's lines. A
detail that the lines do not show makes later answers wrong.

You do NOT write a new extraction. You return a list of corrections to the one you are given. An empty list is a valid
answer when nothing needs correcting.


## The show and how to read it

The show is a workplace sitcom in a mockumentary style. Most lines are jokes, sarcasm, exaggeration, lies and
role-play. A joke or a boast is not a fact, and a statement to the camera is that character's view. A fact is shown when
a line says it plainly or a stage direction (in [brackets]) shows it. It is implied when a reasonable viewer would infer
it from the lines although nobody says it.

The episode text below is your only source of information. A detail is supported only if a line of this episode says
or shows it about that person, place or event, in the words of a line or in a stage direction. A guess that fits the
situation, or something that would be usual for that kind of person, is not support. A detail that no line says or
shows is not supported, however likely it seems.


## What you are given

1. The episode text, scene by scene, every line starting with its id: `[L40213] Jim: ...`.
2. The extraction, in JSON. Every item has an id you can use: characters and places have `local_id`, events have `id`,
   relations have `rid`.
3. EVIDENCE: for each item, the text of the lines it cites. Check each claim of an item against its own evidence lines
   first. A claim that those lines do not show is supported only if another line of the episode says or shows it about
   that same person, place or event; otherwise it is not supported.
4. HINTS: for some items, the words of that item's text that occur nowhere in the episode text. They are only pointers
   to where to look. A hint word is often fine: the extraction may rephrase what the lines show, and a derived or
   paraphrased word is not a problem. It is a problem only when no line of the episode shows the thing the word names
   (a job, a place, a relationship, a reason). Items that have no hints, and words that are not in the hints, can still
   have problems: check every item completely.


## What to check

Go through EVERY item, one by one, and check each detail it states (a name, a job, a place, a relationship, a number, a reason, who
did what to whom) against the episode text.

1. **Details that no line shows.** Remove just that detail and keep the rest of the item. Typical cases: a job title or
   rank in a character's description that no line gives ("receptionist", "accountant"); a place or setting that no line
   mentions; a relationship or a reason that is not in the lines. If nothing is left once the unsupported detail is
   removed, drop the item.
2. **Character descriptions** must say what the person does in this episode, in plain words. A job title, rank or
   relationship to others belongs in it only if a line of this episode says it.
3. **Certainty.** `stated` is correct only when a line says it in words or a stage direction shows it. If the lines
   only fit it (a situation, a gesture, a tone, something said about someone else), it should be `implied`. If it comes
   only from a joke, a lie, a boast or role-play, it should be `joke_or_false`. Change the value only when it is wrong.
4. **Events that only state an occasion or a setting** ("the office hosts a special day", "people gather in the
   conference room") and describe nothing that happens: drop them.
5. **Place kinds:** workplace (a room or area of an office, warehouse or other place of work), home, public (a shop, a
   street, a rooftop, a restaurant, a vehicle), organization (a company mentioned without a location), other.
6. **Participants and roles:** drop a participant only if the lines show they have no part in the event at all. Being
   in a different place from the rest of the event is not a reason: someone can cause or affect an event from elsewhere
   (by phone, by an earlier action, by an order).

Do not correct what is already supported. Do not rephrase for style. Do not add anything the extraction does not
already contain. A main happening or relationship that the lines make likely but do not state stays, with
certainty `implied` (events and relations have that field). Descriptive details (a job, a department, a rank, a place, a
reason) that no line says or shows are removed, even if they seem likely.
Never change an id.


## What to return

A JSON object with two lists, `corrections` and `checked`. Each correction has:

- `target`: which item and field, written as `kind.id.field`:
  - `characters.<local_id>.description`, `characters.<local_id>` (to drop the character)
  - `places.<local_id>.description`, `places.<local_id>.kind`, `places.<local_id>` (to drop)
  - `events.<id>.text`, `events.<id>.certainty`, `events.<id>.place`, `events.<id>` (to drop)
  - `events.<id>.participants.<local_id>` (to drop one participant)
  - `relations.<rid>.certainty`, `relations.<rid>` (to drop)
- `action`: `edit` (replace a text field with `new_value`), `set` (set an allowed value with `new_value`, such as a
  certainty, a kind, or null for an event's place) or `drop`.
- `new_value`: the new text or value, or null for `drop`.
- `problem`: one sentence on what is wrong, naming the detail that no line shows.
- `lines`: the ids of the lines you checked.

An edited text must keep the original meaning, minus the unsupported detail. Keep it as short as the original.

Example (an invented episode, not from this show). The extraction says: event e3 "Priya argues with the landlord in the
lobby", cited lines 120 and 121; character c2 "Landlord", described as "building manager who raises the rent".
Lines 120 and 121 show Priya and the landlord arguing, in a hallway; no line mentions a lobby, and no line gives the
landlord's job. The corrections are:
```
{"corrections": [
 {"target": "events.e3.text", "action": "edit", "new_value": "Priya argues with the landlord in a hallway",
  "problem": "The lines place the argument in a hallway, not a lobby.", "lines": [120, 121]},
 {"target": "characters.c2.description", "action": "edit", "new_value": "Raises the rent and argues with Priya",
  "problem": "No line says the landlord is a building manager.", "lines": [120, 121]}
]}
```

- `checked`: the id of every character, place, event and relation you looked at (`local_id`, `id` or `rid`), so that
  no item is skipped. Include items you found correct. Every item in the extraction must appear here.

Every correction must be one you can justify from the lines. Fewer and correct beats more and doubtful.
