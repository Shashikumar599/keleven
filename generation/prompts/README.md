# Prompts

Each file is sent to the model as is, so lineage notes live here, not in the files.

A prompt file is frozen once a pipeline version has been evaluated with it: a change makes a new file, and
`PROMPT_FILES` in generation/answer.py maps each pipeline version to its files. The hash of the file actually used
is logged with every answer (qa_answers.prompt_sha256).

| File | Used by | Derived from | What it adds |
|---|---|---|---|
| rag_v1.md | v1 | | Strict grounding in the passages; evidence first; citations [S2E1 sc.41] |
| memory_v1.md | v1, v2 | | Memory only, with uncertainty |
| hybrid_v1.md | v1 | | Passages + memory, every claim labelled |
| rag_v2.md | v2 | rag_v1.md | How the evidence was found: the search text (passages match it, not the exact question), the SQL result block (all lines, not a sample), [SQL] citations, counts defer to SQL; judgments about characters (a line's context, a word is not the trait, passages are examples for series-wide judgments) |
| hybrid_v2.md | v2 | hybrid_v1.md | The same additions; SQL vs memory conflicts go to "conflicts"; for series-wide character judgments memory may lead (labelled), passages illustrate |
| enhance_v1.md | v2 | | The enhancer: search_text, sql, assumptions; nothing added from memory |
| enhance_v3.md | v3 | enhance_v1.md | A fourth output, `graph_sql`: one SELECT over the graph views (timeline, relations, events, characters), with the view schema and name-matching rules in the prompt; names and filter values only from the question; the same no-memory rule |
| rag_v3.md | v3 | rag_v2.md | How to read a graph result: cite its scenes and quotes like passages, "the graph shows" and may be incomplete, implied rows hedged, "start / end not shown" is not a date, possible-match people are not one person, passages win on conflict |
| hybrid_v3.md | v3 | hybrid_v2.md | The same graph rule; graph claims are cited by scene, never [memory]; graph vs memory conflicts go to "conflicts" |
| extract_v1.md | v3 (graph extraction, DRAFT under review) | | One call per episode: events, timed relations, refers_back, summary; show context (mockumentary, jokes and sarcasm are not facts); evidence as line ids; fixed relation types |
| review_v1.md | v3 (graph extraction review pass, DRAFT under review) | | A second call that checks the stage 1 extraction against the episode text and returns corrections only (edit, set, drop): removes details no line shows, fixes certainty, drops empty events; keep and mark implied when in doubt |

v1 baseline hashes (eval/runs/2026-10-04-v1-baseline/job.json): rag_v1 5ef7191d, memory_v1 00c114b1, hybrid_v1
2f685a0f.
