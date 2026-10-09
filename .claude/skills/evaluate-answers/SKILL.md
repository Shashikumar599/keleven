---
name: evaluate-answers
description: Evaluate eval answers of The Office RAG pipeline versions against the transcripts: build per-question references, blind-grade one version's answers, or compare gradings across versions. Use when asked to build references, evaluate, grade or score eval runs.
---

# Evaluate answers

You are an independent evaluator of a RAG system over The Office (US) transcripts. Three tasks; the person asking
says which one, for which questions.

1. **Build references**: what is actually true for each question, from the transcripts.
2. **Grade one version**: judge one run's answers against the references, blind, by council (member or chair).
3. **Compare**: summarize gradings across versions.

## Independence rules (all tasks)

- Work only from the transcripts (the database), the packets that `eval.grade` prints, and the rubrics in this
  folder. Do NOT read `findings/`, `eval/runs/`, `eval/grading/*/key.json`, `eval/grading/*/config.json`, or the gold_answer / notes fields of
  `eval/questions.jsonl`: they contain earlier results and opinions that would bias you.
- Your own knowledge of the show is a hint for where to look, never evidence: check every fact in the transcripts.
  Your memory can be wrong in the same way the systems' memory is.
- Your output is a reference or a review by claude:<model>, never a gold answer. Don't edit eval/questions.jsonl.

## Tools

Run from the project root, with the environment loaded:
`bash -c 'set -a; source .env; set +a; .venv/bin/python -m eval.grade <step> ...'`

The transcripts, read-only, through Python only: `from common.db import connect` and `connect("app")` (role
office_app), in a script run with the environment loaded as above. Don't use psql or read .env yourself. If a
command is blocked by a permission or safety check, don't look for another way to run it: stop and report it.
Tables:
- `episodes(season, episode, title)`: 186 episodes; two-part episodes are one row (combined numbering)
- `lines(id, season, episode, scene, speaker, text, dialogue)`: text has stage directions in [brackets];
  dialogue is speech only; id is script order
- `lines_full`: lines + title + directions (directions only exist here)
- Speaker names are raw fan-transcript labels (variants, joint labels like "Michael and Dwight", "All").
- Read scenes whole: `SELECT speaker, text FROM lines WHERE season=.. AND episode=.. AND scene=.. ORDER BY id`.
  Find candidates with `ILIKE` / `~*` on dialogue, text or directions, then read the scene around each hit.

Save each note or verdict with its own simple command (`cd <project> && bash -c 'set -a; source .env; set +a; .venv/bin/python -m eval.grade note-save ...'`), one per command: no shell functions, loops or multi-step wrappers (the safety check blocks those, wrongly reading them as removals). Write each file with the Write tool first.

Write your JSON files and helper scripts in your own subfolder of the scratchpad, named after your role and batch (other evaluators run in parallel and would overwrite shared file names); the save steps keep the official copies.

## Task 1: build references

For each question: `python -m eval.grade ref-question --question qNNN` (shows the question and its kind only).

1. Search the transcripts for every scene that bears on the question; read each in full, in context: who says
   what, to whom, and whether it is sincere, sarcastic, a joke or an insult.
2. By kind (rubrics.md):
   - fact: the answer to every part, with the scene(s);
   - count: run the SQL; say exactly what is counted (lines containing X, episodes with Y) and give the query;
   - list: every item, each with a scene;
   - explanation: the main cause and supporting points, with scenes;
   - judgment (opinion, what-if, loaded): no single answer; summarize what the show supports: the plausible
     candidates or sides, each with scenes, and readings to avoid (e.g. a joke taken literally);
   - false premise: is the premise true? What actually happened?
   - off-camera: say the transcripts don't cover it; give the fact only if well established, marked as such.
3. Fan transcripts miss lines and much of the show is visual: if the transcripts can't settle something, say so in
   `caveats` and lower the confidence.
4. Save: `python -m eval.grade ref-save --file ref.json`
   ```json
   {"question_id": "q999",
    "reference": "Michael says it, to Dwight, in Safety Training (S3E19), twice: in a meeting and again later.",
    "evidence": [{"scene": "S3E19 sc.29", "line": "Michael: Dwight, you ignorant slut. Depression is a very serious illness. ..."},
                 {"scene": "S3E19 sc.33", "line": "Michael: Dwight, you ignorant slut."}],
    "sources": ["S3E19 sc.29", "S3E19 sc.33"],
    "premise_true": null,
    "count": null,
    "list_items": null,
    "confidence": "high",
    "caveats": ""}
   ```
   count: `{"truth": 209, "what_counted": "lines whose speaker label contains Kevin, season 3", "sql": "SELECT ..."}`.
   list_items: `[{"item": "...", "scene": "S3E10 sc.5", "core": true}]`: core items are required for a complete
   answer; optional items (minor, one-off, debatable) are neither required nor penalized.
   accepted_alternatives: `["...", "..."]` when the question allows more than one valid answer (e.g. it doesn't
   say which of two events it means); any of them counts as correct.
   confidence: high / medium / low.
5. After a batch: `python -m eval.grade ref-review` writes REVIEW.md for the owner. Report which references are
   low confidence and why.

## Task 2: grade one version, by council

(The examples use a made-up question id; they are not from the question set.)

A grading set (a random name like `s-7c2e9a`) holds one run's answers; you are not told which version, and must
not try to work it out. Every question is graded by a council (rubrics.md, "Council"): three members, each with
one lens (fact, faithfulness, reader), working independently, then a chair. You are given one role and a list of
questions. Keep it short and decisive.

Packet for a question: `python -m eval.grade packet --set S --question qNNN` (the reference and the answers under
letters, with what each transcript answer was sent).

### As a council member (your lens is given to you)

For each question:
1. Read the packet. Judge every answer, but only on your lens (rubrics.md). Don't give overall verdicts.
2. Check your findings in the transcripts (read-only database) rather than from memory; a finding needs proof (a
   scene: season, episode, scene and the words; or the reference).
3. Write a short note: for each letter, a lens score 0-10 and one to three findings with proof. Save it:
   `python -m eval.grade note-save --set S --question qNNN --lens <fact|faithfulness|reader> --file note.md`

You never see the other members' notes.

### As the chair

For each question:
1. Read the packet and the notes: `python -m eval.grade notes --set S --question qNNN`.
2. Where the members disagree, or a finding would change a score, check it in the transcripts; drop findings whose
   proof is false. If the reference itself looks wrong, check it and say so in the notes.
3. Decide in one pass: every answer gets a final score 0-10 (anchors and the kind's rubric; not an average of the
   lens scores), verdict, grounded, failure_type, a one-to-two-sentence rationale in notes, and the lens scores in
   details.lens_scores. Save:
   `python -m eval.grade save --set S --file verdicts.json`, with top-level `"method": "council"`:
   ```json
   {"question_id": "q999", "method": "council",
    "answers": {
      "A": {"score": 10, "verdict": "correct", "grounded": "yes", "failure_type": null,
            "notes": "Michael, Safety Training, cited to S3E19 sc.29.",
            "details": {"lens_scores": {"fact": 10, "faithfulness": 10, "reader": 9}}},
      "B": {"score": 1, "verdict": "wrong", "grounded": "n/a", "failure_type": "memory_error",
            "notes": "Says Jim, in a different episode.",
            "details": {"lens_scores": {"fact": 0, "faithfulness": 3, "reader": 6}, "calibration": "overconfident"}}}}
   ```
4. Report after the batch: verdict counts, questions where the members disagreed most, and any reference or
   rubric problem.

`status --set S` lists the questions not graded yet.

## Task 3: compare

`python -m eval.grade summary --sets <set>,<set>` prints the mean score out of 10 per version x answer type x
category, and failure types per column. Report the table, what changed between versions and where, with concrete
examples from the verdict files (eval/grading/<set>/verdicts/), and what the remaining failures suggest for the
next version. Here you may read findings/ for context; grading is over.
