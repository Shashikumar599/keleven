# Graph design (Phase 3 draft)

Status: **design note only.** Phase 3 is built only if Phase 2 findings show multi-hop or whole-dataset
questions still fail. Target questions: "What are the major storylines of Season 5?", "Trace every relationship
Andy had and what happened to each partner."

## Core idea
A relationship-only graph (who married whom) is weak; single facts are answered by plain retrieval. Narrative
questions need **events** as nodes: storylines are chains of events across episodes.

## Nodes
| Node | Examples | Source |
|---|---|---|
| Character (+ aliases) | Jim ("Big Tuna", "Halpert") | speaker names, mentions in dialogue |
| Episode, Scene | S5E1 Weight Loss, scene 12 | data (no LLM) |
| Event | Jim proposes to Pam at a gas station | LLM extraction, cited to a scene |
| Storyline | Michael Scott Paper Company, Jim & Pam | grouped from events |
| Organization / Place | Dunder Mifflin Scranton, Schrute Farms, Sabre | LLM extraction |

## Edges
| Edge | Kind |
|---|---|
| Scene PART_OF Episode, Episode NEXT Episode | structural (data) |
| Character APPEARS_IN Scene, Character TALKS_TO Character {scenes} | computed (SQL) |
| Character PARTICIPATES_IN Event {role}, Event HAPPENS_IN Scene | extracted, cited |
| Event LEADS_TO Event | extracted (cause and effect; links storylines together) |
| Event PART_OF Storyline | grouped |
| Character RELATION {dating, married, boss, rival, family} Character {from_ep, to_ep} | extracted, timed |
| Character WORKS_AT Organization {from_ep, to_ep} | extracted, timed |

## Rules
1. Fixed list of node and edge types; no open-ended extraction.
2. Every extracted fact has a scene citation and an episode index (time).
3. Structural and computed edges form a reliable base; only the event layer depends on the LLM.

## Linking
1. Merge character names: speaker list + nicknames found in dialogue.
2. Merge events: a later reference ("remember the gas station?") links to the original event.
3. Link events across episodes: compare a new event with recent events of the same characters → LEADS_TO.
4. Storylines: community detection on the event-character graph; LLM names and summarizes each cluster
   per season and for the series.

Extraction runs per episode (186 calls), not per scene: 35% of scenes are a single line.

## Answering "major storylines of Season 5"
Storylines with events in Season 5, ranked by number of events and episodes covered, answered from their
summaries with key event scenes as citations.

## Baseline to beat
Hierarchical summaries (episode → season, RAPTOR-style) without a graph. Research question: does the event graph
beat hierarchical summaries on storyline questions, and is the extra cost worth it?
