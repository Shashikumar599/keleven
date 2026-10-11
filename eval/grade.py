"""
Grading eval answers by Claude in a fresh context (the evaluate-answers skill), in three tasks:

  1. References: one per question, built once from the transcripts and shared by every version's grading.
     python -m eval.grade ref-question --question q017       what the reference builder sees (question + kind only)
     python -m eval.grade ref-save --file ref.json            store eval/grading/references/q017.json
     python -m eval.grade ref-review                          eval/grading/references/REVIEW.md, for the owner

  2. Grading one version at a time, against the references (never seeing other versions' answers):
     python -m eval.grade init   --label L                             once, by the coordinator: makes a set with a
                                                                       random name (e.g. s-7c2e9a) for run L
     python -m eval.grade packet --set s-7c2e9a --question q017              that run's answers, blinded A, B, C
     python -m eval.grade save   --set s-7c2e9a --file verdicts.json         store the verdicts (qa_reviews + a copy)
     python -m eval.grade status --set s-7c2e9a                              which questions are graded
     Set names are random, with no order, so graders can't tell which version they grade.

     Every question is graded by a council: three lens members write notes, then a chair decides and saves.
     python -m eval.grade note-save --set S --question q066 --lens fact --file note.md
     python -m eval.grade notes --set S --question q066                       the three notes, for the chair

  3. Cumulative comparison: python -m eval.grade summary --sets s-7c2e9a,s-41b0d3   (mean score out of 10)

A grading set (eval/grading/<set>/) holds the blinding key (key.json: letter -> run and system) and a copy of every
verdict file. The grader must not read key.json, findings/ or eval/runs/: packets give it everything it needs.
Packets show no draft gold answers or notes from eval/questions.jsonl (they were written with knowledge of earlier
results). Verdicts are reviews (reviewer claude:<model>), never gold answers.
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from common.db import connect
from common.qalog import log_review
from eval.run import label_version, load_questions, read_jsonl

EVAL = Path(__file__).parent
REFS = EVAL / "grading" / "references"
REVIEWER = "claude:claude-opus-5-5"                  # single grader / debate (first pilot)
COUNCIL_REVIEWER = "claude-council:claude-opus-5-5"  # council chair
LENSES = ("fact", "faithfulness", "reader")
RUBRIC = "rubrics-v2"
TYPE = {"llm": "memory (no transcripts)", "rag": "transcripts only", "hybrid": "transcripts + memory"}
KIND = {"detail": "A fact", "who_said": "A fact", "which_episode": "A fact", "finish_the_quote": "A fact",
        "order": "A fact", "visual": "A fact", "multi_hop": "A fact", "count": "B count", "list": "C list",
        "why": "D explanation", "story_arc": "D explanation", "opinion": "E judgment", "counterfactual": "E judgment",
        "loaded": "E judgment", "false_premise": "false premise", "off_camera": "off-camera"}
VERDICTS = {"correct", "partial", "wrong", "refused"}
SCORE_RANGE = {"correct": (8, 10), "partial": (4, 7), "wrong": (0, 3), "refused": (0, 2)}
GROUNDED = {"yes", "partly", "no", "n/a"}
FAILURES = {"retrieval_miss", "evidence_misread", "literal_reading", "invented_quote", "claim_beyond_evidence",
            "memory_error", "memory_in_rag", "count_from_sample", "premise_accepted", "premise_over_rejected",
            "attribution_error", "incomplete", "refused_with_evidence", "no_position", "memory_unsure", "other"}


def question(qid):
    q = next((q for q in load_questions() if q["id"] == qid), None)
    if not q:
        sys.exit(f"no question {qid}")
    return q


def set_dir(name):
    d = EVAL / "grading" / name
    (d / "verdicts").mkdir(parents=True, exist_ok=True)
    return d


def set_label(args):
    """The run label a grading set grades: given once with `init`, so graders never see it."""
    cfg = set_dir(args.set) / "config.json"
    if not cfg.exists():
        sys.exit(f"grading set {args.set} has no run label: init it first")
    return json.loads(cfg.read_text())["label"]


def init(args):
    """Create a grading set for a run under a random name (no order, no version hint), unless --set is given."""
    import secrets
    if getattr(args, "labels", None):
        args.label = args.labels[0]
    if not (EVAL / "runs" / f"{args.label}.jsonl").exists():
        sys.exit(f"no run {args.label}")
    args.set = args.set or f"s-{secrets.token_hex(3)}"
    cfg = {"label": args.label}
    if getattr(args, "labels", None):            # combined set: several runs of the same questions, graded in one blind session
        missing = [l for l in args.labels if not (EVAL / "runs" / f"{l}.jsonl").exists()]
        if missing:
            sys.exit(f"no run {', '.join(missing)}")
        cfg = {"label": args.labels[0], "labels": args.labels}
    (set_dir(args.set) / "config.json").write_text(json.dumps(cfg))
    print(f"grading set {args.set} ready")


def load_key(name):
    p = set_dir(name) / "key.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ---------- 1. references ----------

def ref_question(args):
    q = question(args.question)
    print(f"# {q['id']} [{q['category']}, kind: {KIND.get(q['category'], 'A fact')}]\n{q['question']}")
    if (REFS / f"{q['id']}.json").exists():
        print("\n(a reference already exists; ref-save will replace it)")


def ref_save(args):
    r = json.loads(Path(args.file).read_text())
    for f in ("question_id", "reference", "sources", "confidence"):
        if not r.get(f) and f != "sources":
            sys.exit(f"reference needs {f}")
    if r["confidence"] not in ("high", "medium", "low"):
        sys.exit("confidence must be high, medium or low")
    q = question(r["question_id"])
    r = {**r, "question": q["question"], "category": q["category"], "made_by": REVIEWER,
         "verified_by_owner": False}
    REFS.mkdir(parents=True, exist_ok=True)
    (REFS / f"{q['id']}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
    print(f"saved reference {q['id']} ({r['confidence']} confidence)")


def ref_review(args):
    """One markdown file listing every reference compactly, for the owner to review."""
    out = ["# References for review", "",
           "Built by Claude from the transcripts. Check each one; mark a reference verified by setting "
           "`verified_by_owner: true` in its JSON file (or tell Claude which ones are right or wrong).", ""]
    for p in sorted(REFS.glob("q*.json")):
        r = json.loads(p.read_text())
        mark = "verified" if r.get("verified_by_owner") else f"{r['confidence']} confidence"
        out += [f"## {r['question_id']} [{r['category']}] ({mark})", f"**Q:** {r['question']}", "",
                f"**Reference:** {r['reference']}", ""]
        for e in r.get("evidence") or []:
            out.append(f"- {e.get('scene', '')}: {e.get('line', '')}")
        if r.get("caveats"):
            out += ["", f"_Caveats: {r['caveats']}_"]
        out.append("")
    (REFS / "REVIEW.md").write_text("\n".join(out))
    print(f"wrote {REFS / 'REVIEW.md'} ({len(list(REFS.glob('q*.json')))} references)")


# ---------- 2. grading one version ----------

def run_row(label, qid):
    return next((r for r in read_jsonl(EVAL / "runs" / f"{label}.jsonl") if r["question_id"] == qid), None)


def scenes_sent(label, qid):
    rec = next((r for r in read_jsonl(EVAL / "runs" / label / "retrieval.jsonl") if r["question_id"] == qid), None)
    if not rec:
        return "", None
    with connect("app") as conn:
        rows = conn.execute("""SELECT season, episode, title, scene_start, scene_end FROM chunks_full
                               WHERE chunk_id = ANY(%s) ORDER BY season, episode, position""",
                            (rec["sent_chunk_ids"],)).fetchall()
    merged = []
    for s, e, t, a, b in rows:
        if merged and merged[-1][:2] == (s, e) and a <= merged[-1][4] + 1:
            merged[-1] = (s, e, t, merged[-1][3], max(b, merged[-1][4]))
        else:
            merged.append((s, e, t, a, b))
    return "; ".join(f"S{s}E{e} {t} sc{a}-{b}" for s, e, t, a, b in merged), rec.get("plan")


def packet(args):
    q = question(args.question)
    ref_path = REFS / f"{q['id']}.json"
    if not ref_path.exists():
        sys.exit(f"no reference for {q['id']}: build it first (ref-question / ref-save)")
    label = set_label(args)
    row = run_row(label, q["id"])
    if row is None:
        sys.exit(f"{q['id']} is not in this set's run")
    key = load_key(args.set)
    labels = json.loads((set_dir(args.set) / "config.json").read_text()).get("labels")
    if q["id"] not in key:
        if labels:                  # combined set: every run's rag and hybrid answer, and the memory answer once
            entries, seen_memory = [], False
            for lb in labels:
                r = run_row(lb, q["id"])
                if r is None:
                    sys.exit(f"{q['id']} is not in run {lb}")
                for sysname in r["answers"]:
                    if sysname == "llm" and seen_memory:
                        continue
                    seen_memory = seen_memory or sysname == "llm"
                    entries.append({"label": lb, "run_id": r["run_id"], "system": sysname})
            random.SystemRandom().shuffle(entries)
            key[q["id"]] = {chr(65 + i): e for i, e in enumerate(entries)}
        else:
            systems = list(row["answers"])
            random.SystemRandom().shuffle(systems)
            key[q["id"]] = {chr(65 + i): {"label": label, "run_id": row["run_id"], "system": s}
                            for i, s in enumerate(systems)}
        (set_dir(args.set) / "key.json").write_text(json.dumps(key, indent=1))
    ref = json.loads(ref_path.read_text())

    print(f"# {q['id']} [{q['category']}, kind: {KIND.get(q['category'], 'A fact')}] {q['question']}")
    print(f"\nReference ({ref['confidence']} confidence"
          f"{', verified by the owner' if ref.get('verified_by_owner') else ''}): {ref['reference']}")
    for e in ref.get("evidence") or []:
        print(f"  - {e.get('scene', '')}: {e.get('line', '')}")
    for f in ("premise_true", "count", "list_items", "caveats"):
        if ref.get(f) not in (None, "", []):
            print(f"  {f}: {ref[f]}")
    for letter, k in sorted(key[q["id"]].items()):
        k_label = k.get("label", label)
        a = run_row(k_label, q["id"])["answers"][k["system"]] if labels else row["answers"][k["system"]]
        d = a.get("data") or {}
        print(f"\n## Answer {letter}: {TYPE[k['system']]}")
        if a.get("error"):
            print(f"ERROR: {a['error']}")
        print(d.get("answer") or a.get("raw") or "")
        if "answerable" in d:
            print(f"- answerable: {d['answerable']}")
        if "knows_answer" in d:
            print(f"- knows_answer: {d['knows_answer']}; uncertain: {d.get('uncertain')}")
        for f in ("memory_claims", "conflicts"):
            if d.get(f):
                print(f"- {f}: {d[f]}")
        bad = {(b["season"], b["episode"], b["scene"], b["quote"]): b["problems"]
               for b in ((a.get("check") or {}).get("bad_evidence") or [])}
        for ev in d.get("evidence") or []:
            probs = bad.get((ev["season"], ev["episode"], ev["scene"], ev["quote"]))
            print(f"- evidence S{ev['season']}E{ev['episode']} sc{ev['scene']} "
                  f"{'NOT FOUND: ' + ', '.join(probs) if probs else 'ok'}: {ev['quote']!r}")
        if k["system"] != "llm":
            sent, plan = scenes_sent(k_label, q["id"])
            print(f"- scenes it was sent: {sent}")
            res = (plan or {}).get("sql_result")
            if res:
                print(f"- SQL result it was sent: {plan['sql']}\n  "
                      f"({res.get('error') or str(len(res['rows'])) + ' rows'}) {res['rows'][:12]}")


def save(args):
    v = json.loads(Path(args.file).read_text())
    qid = v["question_id"]
    key = load_key(args.set).get(qid)
    if not key:
        sys.exit(f"no packet was made for {qid} in set {args.set}")
    if set(key) - set(v["answers"]):
        sys.exit(f"verdicts missing for {sorted(set(key) - set(v['answers']))}")
    for letter, g in v["answers"].items():
        problems = [f"verdict {g.get('verdict')!r}"] if g.get("verdict") not in VERDICTS else []
        if g.get("grounded") not in GROUNDED:
            problems.append(f"grounded {g.get('grounded')!r}")
        if g.get("failure_type") not in FAILURES | {None}:
            problems.append(f"failure_type {g.get('failure_type')!r}")
        lo, hi = SCORE_RANGE.get(g.get("verdict"), (0, 10))
        if not isinstance(g.get("score"), int) or not lo <= g["score"] <= hi:
            problems.append(f"score {g.get('score')!r} (must be an integer {lo}-{hi} for {g.get('verdict')})")
        if problems:
            sys.exit(f"{qid} {letter}: invalid {', '.join(problems)}")
    for letter, g in v["answers"].items():
        k = key[letter]
        details = {**(g.get("details") or {}), "score": g["score"], "letter": letter, "rubric": RUBRIC,
                   "grading_set": args.set, "method": v.get("method", "single")}
        reviewer = COUNCIL_REVIEWER if v.get("method") == "council" else REVIEWER
        if combined_set(args.set):          # a combined set re-grades runs already graded: keep the earlier reviews (unique per run, system, reviewer)
            reviewer = f"{reviewer}#{args.set}"
        log_review(k["run_id"], k["system"], reviewer, g["verdict"], notes=g.get("notes"), grounded=g["grounded"],
                   failure_type=g.get("failure_type"), details=details)
    (set_dir(args.set) / "verdicts" / f"{qid}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False))
    print(f"saved {qid}: {len(v['answers'])} answers")


def combined_set(name):
    """True for a set made with init --labels (several runs graded together)."""
    return bool(json.loads((set_dir(name) / "config.json").read_text()).get("labels"))


def status(args):
    done = {p.stem for p in (set_dir(args.set) / "verdicts").glob("*.json")}
    qids = [r["question_id"] for r in read_jsonl(EVAL / "runs" / f"{set_label(args)}.jsonl")]
    todo = [q for q in qids if q not in done]
    no_ref = [q for q in todo if not (REFS / f"{q}.json").exists()]
    print(f"{len(done)} graded, {len(todo)} to go ({len(no_ref)} without a reference yet): {' '.join(todo)}")


# ---------- 2b. council notes (one per lens per question) ----------

def note_save(args):
    """A council member's note for one question: eval/grading/<set>/notes/<qid>-<lens>.md"""
    if args.lens not in LENSES:
        sys.exit(f"lens must be one of {LENSES}")
    if args.question not in load_key(args.set):
        sys.exit(f"no packet for {args.question} in set {args.set}")
    d = set_dir(args.set) / "notes"
    d.mkdir(exist_ok=True)
    (d / f"{args.question}-{args.lens}.md").write_text(Path(args.file).read_text())
    print(f"saved {args.lens} note for {args.question}")


def notes(args):
    """The three lens notes for a question, for the chair."""
    d = set_dir(args.set) / "notes"
    missing = [l for l in LENSES if not (d / f"{args.question}-{l}.md").exists()]
    if missing:
        sys.exit(f"{args.question}: no note yet from {', '.join(missing)}")
    for lens in LENSES:
        print(f"## {lens} member\n{(d / f'{args.question}-{lens}.md').read_text().strip()}\n")


# ---------- 3. cumulative comparison ----------

def summary(args):
    qs = {q["id"]: q for q in load_questions()}
    by, fails = defaultdict(list), defaultdict(lambda: defaultdict(int))
    for name in args.sets:
        key = load_key(name)
        for p in sorted((set_dir(name) / "verdicts").glob("*.json")):
            v = json.loads(p.read_text())
            cat = qs[v["question_id"]]["category"]
            for letter, g in v["answers"].items():
                k = key[v["question_id"]][letter]
                col = f"{label_version(k['label'])} {'memory' if k['system'] == 'llm' else k['system']}"
                by[(col, "ALL")].append(g["score"])
                by[(col, cat)].append(g["score"])
                if g.get("failure_type"):
                    fails[col][g["failure_type"]] += 1
    order = {"memory": 0, "rag": 1, "hybrid": 2}
    cols = sorted({c for c, _ in by}, key=lambda c: (c.split()[0], order[c.split()[1]]))
    cats = ["ALL"] + sorted({c for _, c in by} - {"ALL"})
    print("mean score out of 10 (number of answers)\n")
    print("category".ljust(17) + "".join(c.rjust(14) for c in cols))
    for cat in cats:
        print(cat.ljust(17) + "".join(
            (f"{sum(x) / len(x):.1f} ({len(x)})" if (x := by.get((c, cat))) else "-").rjust(14) for c in cols))
    print("\nfailure types:")
    for c in cols:
        print(f"  {c}: " + ", ".join(f"{k} {n}" for k, n in sorted(fails[c].items(), key=lambda kv: -kv[1])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["init", "ref-question", "ref-save", "ref-review", "packet", "save", "status", "summary",
                                     "note-save", "notes"])
    ap.add_argument("--lens", help="note-save: fact, faithfulness or reader")
    ap.add_argument("--set", help="grading set (one version), e.g. v1")
    ap.add_argument("--sets", type=lambda s: s.split(","), help="summary: grading sets, e.g. v1,v2")
    ap.add_argument("--label", help="eval run label graded in this set")
    ap.add_argument("--labels", type=lambda s: s.split(","), help="init: several run labels for one combined, blind set")
    ap.add_argument("--question", help="question id")
    ap.add_argument("--file", help="JSON file to save (reference or verdicts)")
    args = ap.parse_args()
    {"init": init, "ref-question": ref_question, "ref-save": ref_save, "ref-review": ref_review, "packet": packet, "save": save,
     "status": status, "summary": summary, "note-save": note_save, "notes": notes}[args.step](args)


if __name__ == "__main__":
    main()
