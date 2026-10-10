# Graph schema (v3, migration 013): for review

Status: **applied 2026-10-10; build `v3-graph-001` loaded.** All section 6 recommendations were accepted ("go ahead"), so the
tables differ from the first draft described in sections 3 and 6: candidate links are in `graph_entity_links`, entities are keyed
by name (no serial id), local ids have foreign keys, and `graph_refers_back`, `graph_current` and a full-text index on event text
were added. File: `db/migrations/013_graph_tables.sql`. Loader: `graph/build_graph.py` (dry run only so far).
Nothing here calls an LLM. The tables are built from the extraction JSON already stored in Postgres
(`episode_extractions`, stage `reviewed`, run `v3-extract-001`) and from the two linking files
(`graph/out/certain_entities.json`, `graph/out/tiered_entities.json`).

Reading order: what the tables are (1), how a fact travels from the JSON to a table (2), the tables one by one (3), how a
question is answered with them (4), what the schema cannot do yet (5), and the decisions I need from you (6).

---

## 1. The idea in one paragraph

Each episode was extracted on its own, so every episode has its own ids: `c1` is Kelly in S7E14 and somebody else in
S2E18. The graph keeps those per-episode rows exactly as extracted (they are the evidence) and adds **one linking layer**:
`graph_characters.entity_id` says "this person in this episode is the same person as that entity". Relations and events are
joined to entities **through that link**. So a wrong link is fixed by rebuilding the link; no extracted fact changes.

```
graph_entities (104)               one row per linked person: name, tier, counts
      ▲ entity_id
graph_characters (3,883)           one row per person per episode (local_id c1, c2, ...)
      ▲ local_id                         ▲ local_id
graph_relations (325)              graph_event_participants (4,568)
                                         ▲ event_id
                                   graph_events (1,698) ── place_local_id ──► graph_places (793)

graph_episode_summaries (186)      one summary per episode
graph_builds                       one row per loader run; every table above carries build_id
```

Counts are from the dry run on `v3-extract-001` (186 episodes, 0 failures).

---

## 2. From JSON to tables

The stored JSON for one episode has six parts. Each goes to one table:

| JSON part | Table | Notes |
|---|---|---|
| `characters[]` | `graph_characters` | plus the link to an entity, decided by the linking files |
| `places[]` | `graph_places` | local to the episode; not linked across episodes (yet) |
| `events[]` | `graph_events` | one row per event |
| `events[].participants[]` | `graph_event_participants` | one row per (event, character, role) |
| `relations[]` | `graph_relations` | one row per reported change |
| `summary` | `graph_episode_summaries` | |
| `refers_back[]` | **not stored** (see decision 6) | |

Real example, S7E14 (the first one I used for testing). The extraction has a character `c1` named "Kelly" and `c2`
(Ryan), and one relation:

```
relation r1: a=c1, b=c2, type=married, change=revealed, certainty=stated,
             quote="like a week ago, we got really wasted and it just felt right", lines=[42531, 42540, 42543]
```

After the load, that is one row in `graph_relations` (a_local_id `c1`, b_local_id `c2`, season 7, episode 14). The names
come only through `graph_characters`, and the entity (if any) through `graph_characters.entity_id`.

---

## 3. The tables

All tables have `build_id` (a graph build; several builds can exist side by side). Deleting a build removes its rows
(`ON DELETE CASCADE`).

### graph_builds
One row per loader run.

| column | meaning |
|---|---|
| build_id, label | e.g. `v3-graph-001` |
| run_id | which extraction run was read (`extraction_runs`) |
| rules | linking thresholds and the files used (so a build can be explained later) |
| counts | rows loaded, for a quick check |

### graph_entities: the linked people
One row per person the data lets us name across episodes.

| column | meaning |
|---|---|
| entity_id | serial, **changes on every rebuild** (decision 5) |
| name | normalised primary name, unique within a build (`michael`, `david wallace`) |
| names | primary names merged into it (small groups attached to a certain entity) |
| tier | `certain`, `probable` or `possible` (below) |
| cards, episodes, seasons | how many characters-in-episodes, episodes and seasons it covers |
| note | surname variants noticed inside a certain group (only a note) |

The tiers, and what produced them:

| tier | rule | code | rows in dry run |
|---|---|---|---|
| certain | primary name in 40+ episodes, one card per episode | `graph/link_certain.py` | 2,766 cards |
| probable | full name (2+ words), 3+ episodes, one card per episode | `graph/link_tiers.py` | 69 cards |
| possible | one-word name, 3+ episodes, one card per episode; may be a role or several people | `graph/link_tiers.py` | 551 cards |

104 entities in total. 497 of 3,883 cards stay unlinked.

### graph_characters: one person in one episode (a "card")
Key: `(build_id, season, episode, local_id)`.

| column | meaning |
|---|---|
| names | the names the extraction gave (first one is the primary name) |
| description | what the person does in this episode (verb-first, from the extraction) |
| present | on screen, or only mentioned |
| line_ids | transcript lines that show the character |
| entity_id | the link; **null = unlinked** (stays a local node, found by name) |
| link_tier | confidence of the link; null when unlinked |
| candidate_entity_ids | for a `possible` card: named entities it might be the same as (e.g. `david` -> `david wallace`). Never a merge. |

### graph_places
Local places only (793). Key `(build_id, season, episode, local_id)`; columns name, kind (workplace / home / public /
organization / other), description, `line_ids`. Not linked across episodes, and the coverage check showed that is not needed
for now.

### graph_events and graph_event_participants
`graph_events`: id (`e1`), text (one sentence), kind (romance / job / conflict / prank / milestone / family / other),
`place_local_id`, certainty (stated / implied / joke_or_false), importance (major / minor, **local to the episode**),
`line_ids`.

`graph_event_participants`: (event, character `local_id`, role). Roles: agent (does it), patient (it is done to them),
subject (it is about them), witness (sees it).

### graph_relations
One row per relation **as reported in one episode**, not one per pair. Columns: `a_local_id`, `b_local_id`, type (crush,
dating, engaged, married, family, boss, rival, friend), change (**begins / ends / revealed**), detail, quote, certainty,
`line_ids`. Direction matters for `boss` (a is the boss). A relationship over time is several rows; the intervals are
derived later (section 5).

### graph_episode_summaries
Season, episode, summary text from the extraction.

---

## 4. How a question is answered

"Whom did Michael date?", with the tables above (shown as a join, not final SQL):

1. `graph_entities` row `michael` (certain) gives `entity_id`.
2. `graph_characters` rows with that `entity_id` give Michael's local id in each episode.
3. `graph_relations` rows of type `dating` where `a_local_id` or `b_local_id` is that local id give the changes.
4. The **other end** is read from `graph_characters` of the same episode: if it has an `entity_id` it is a linked
   person, otherwise it is a name (Carol, Helene, Donna are local nodes, found by name).
5. `line_ids` give the cited quotes from the `lines` table.

Result already seen on the stored data: Carol (S3E10), Jan (S3E11 to S3E23), Holly (S5E3 to S7E18), Helene (S6E6 to S6E8),
Donna (S6E22 to S6E23). That is the complete draft gold list for q045.

---

## 5. What this schema does not do yet

This is the storage layer. The graph is **not query-ready** until these exist (planned as migration 014, views):

1. **Resolved relations view.** Joining twice through `graph_characters` for every query is error-prone. A view should give
   `a_entity, a_name, b_entity, b_name, type, change, season, episode, certainty, line_ids`.
2. **Resolved events view.** The same for events: participants as entity or name.
3. **Relation timelines.** "Were Jan and Michael dating in S3E15?" needs intervals. Known difficulties: repeated `begins` rows
   (Holly S5E3 and S5E4), rows with no start, and `revealed` rows that only prove a relation existed.
4. **Evidence text.** `line_ids` is an integer array; getting the line text needs an `unnest` join with `lines`.
5. **Normalised name search** for unlinked characters (case-insensitive lookup by name).

Known limits that no schema fixes: minor recurring characters are `probable`/`possible` at best; the same person under two
names in different episodes stays two nodes; completeness depends on the extraction (relations are thin: 325 rows, 31
episodes have none); importance is noisy and local to the episode.

---

## 6. Decisions I need from you

| # | Decision | My recommendation |
|---|---|---|
| 1 | **Candidate links on the entity, not the card.** Today each card carries `candidate_entity_ids`, repeating the same fact on every card. Alternative: a table `graph_entity_links (entity_a, entity_b, kind = 'possible_same')`. | Change to the entity-links table. |
| 2 | **`link_tier` per card.** It currently always equals the entity's tier. It would only differ if cards inside one entity had different confidence (small groups attached on 2+ listings). | Keep it, and fill it from the attach step. |
| 3 | **Foreign keys for local ids.** Relations, participants and event places point at local ids with no key. The validator guarantees they exist, but the database would not catch a loader bug. | Add the keys. |
| 4 | **Evidence as arrays or rows.** Arrays are enough to show quotes. A `graph_evidence(item_kind, item_id, line_id)` table would answer "which facts cite this line". | Stay with arrays until a query needs it. |
| 5 | **Entity key.** The serial `entity_id` changes on every rebuild, so an id stored in a log or eval run would point at the wrong person. The normalised name is unique within a build and stable. | Use the name as the key; keep the serial as an internal detail. |
| 6 | **What the loader drops.** `refers_back` (callbacks) is not stored; item `flags` (validator findings) are not stored. | Store `refers_back`; leave flags in the extraction rows, where they already are. |
| 7 | **Several builds side by side.** Every query must filter on `build_id`; one forgotten filter silently mixes builds. | A `current_build` setting plus views that filter on it. |
| 8 | **Searching event text.** Some questions are best answered by text search over event sentences. A full-text index (or embeddings) on `graph_events.text` would let the graph path fall back on text. | Add a full-text index in 013; leave embeddings for later. |

## 7. Next steps once decisions are made

1. Update 013 with the decisions (nothing is applied, so this is a rewrite).
2. Apply 013 with the admin role, run the loader with `--run`, check the row counts against the dry run.
3. Write 014 (views), then relation timelines, then the minimal graph search and its place in the planner.
4. Log every decision in `findings/decisions.md`.
