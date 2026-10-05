"""
Run the question set through the pipeline as one Gemini batch job.

    python -m eval.run prepare --label 2026-10-04-v1-baseline --version v1    retrieval for every question
                                                                   (v1: Voyage only; v2: also one enhancer
                                                                   LLM call per question, not batched)
    python -m eval.run plan    --label ...                         what would be submitted: counts, size, token estimate
    python -m eval.run submit  --label ...                         build the prompts, submit ONE batch job (LLM calls)
    python -m eval.run status  --label ...                         job state
    python -m eval.run collect --label ...                         fetch answers, check citations, log, write JSONL
    python -m eval.run rerun   --label ...                         re-answer failed answers as single online calls

A batch job runs asynchronously on Google's side, so the steps share state through files in
eval/runs/<label>/ (retrieval.jsonl, job.json). They hold chunk ids and hashes only, never transcript text: prompts are
rebuilt from the chunks table when submitting and collecting.

Every answer is logged like a web question (qa_runs source 'eval', with eval_label and question_id) and so appears
in History. The final record for the run is eval/runs/<label>.jsonl.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from common.db import connect
from common.qalog import log_run
from common.stored import stored_memory
from generation.answer import SCHEMAS, build_prompt, check_citations, load_prompt, prompt_file, prompt_sha256
from generation.llm import DEFAULT_MODEL
from retrieval import CURRENT_VERSION, retrieve
from retrieval.vector import Hit, Retrieval, _chunks, _passages

EVAL = Path(__file__).parent
QUESTIONS = EVAL / "questions.jsonl"
SYSTEMS = ("rag", "llm", "hybrid")
MAX_OUTPUT_TOKENS = 16384         # same as the web app (GeminiProvider.generate default); includes thinking
INLINE_LIMIT = 19_000_000         # Gemini inline batch requests must stay under 20 MB


def load_questions(only=None):
    rows = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]
    return [r for r in rows if not only or r["id"] in only]


def questions_sha256():
    return hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()


def run_dir(label):
    d = EVAL / "runs" / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def label_version(label):
    """The pipeline version of a label's retrieval (one label holds one version; records before v2 are v1)."""
    recs = read_jsonl(run_dir(label) / "retrieval.jsonl")
    return recs[0].get("version", "v1") if recs else CURRENT_VERSION


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


# ---------- retrieval, stored as ids and rebuilt from the chunks table ----------

def retrieval_record(qid, r, version):
    return {"question_id": qid, "question": r.question, "version": version, "method": r.method,
            "chunk_set": r.chunk_set, "model": r.model,
            "k": r.k, "expand": r.expand, "query_tokens": r.query_tokens, "timings_ms": r.timings_ms,
            "hits": [{"rank": h.rank, "chunk_id": h.chunk.chunk_id, "distance": h.distance, **h.scores}
                     for h in r.hits],
            "sent_chunk_ids": [c.chunk_id for p in r.passages for c in p.chunks], "plan": r.plan}


def rebuild(rec):
    """The Retrieval object for a stored record: same hits, same passages, same prompt."""
    with connect("app") as conn:
        chunks = _chunks(conn, "chunk_id = ANY(%s)", (rec["sent_chunk_ids"],))
    hits = [Hit(h["rank"], h["distance"], chunks[h["chunk_id"]],
                {k: v for k, v in h.items() if k not in ("rank", "chunk_id", "distance")}) for h in rec["hits"]]
    return Retrieval(question=rec["question"], chunk_set=rec["chunk_set"], model=rec["model"], k=rec["k"],
                     expand=rec["expand"], hits=hits, passages=_passages(hits, chunks),
                     query_tokens=rec["query_tokens"], timings_ms=rec["timings_ms"],
                     method=rec.get("method", "vector"),          # records from before v2 are vector
                     plan=rec.get("plan"))


def prepare(args):
    path = run_dir(args.label) / "retrieval.jsonl"
    existing = read_jsonl(path)
    other = {r.get("version", "v1") for r in existing} - {args.version}
    if other:
        sys.exit(f"{path} holds {', '.join(sorted(other))} retrieval; use a new label for {args.version}")
    done = {r["question_id"] for r in existing}
    todo = [q for q in load_questions(args.only) if q["id"] not in done]
    print(f"{args.version}: {len(done)} already retrieved, {len(todo)} to go (k={args.k}, expand={args.expand})")
    with path.open("a") as f:
        for q in todo:
            r = retrieve(q["question"], version=args.version, k=args.k, expand=args.expand)
            f.write(json.dumps(retrieval_record(q["id"], r, args.version)) + "\n")
            f.flush()
            print(f"  {q['id']}  {len(r.passages)} passages, {r.timings_ms['total']} ms")
    print(f"wrote {path}")


# ---------- building the batch ----------

def build_requests(label, only=None):
    """[(key, system, system_prompt, prompt)] for every question x system. Fails if retrieval is missing."""
    recs = {r["question_id"]: r for r in read_jsonl(run_dir(label) / "retrieval.jsonl")}
    questions = load_questions(only)
    missing = [q["id"] for q in questions if q["id"] not in recs]
    if missing:
        sys.exit(f"no retrieval for {len(missing)} questions ({', '.join(missing[:5])}...): run prepare first")
    version = label_version(label)
    prompts = {s: load_prompt(s, version) for s in SYSTEMS}
    out = []
    for q in questions:
        r = rebuild(recs[q["id"]])
        for s in SYSTEMS:
            if s == "llm" and stored_memory(q["question"], prompt_file("llm", version)):
                continue                  # memory doesn't depend on the version: reused at collect, no new call
            out.append((f"{q['id']}:{s}", s, prompts[s], build_prompt(q["question"], r if s != "llm" else None)))
    return out


def plan(args):
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")       # an estimate only: Gemini's tokenizer differs
    reqs = build_requests(args.label, args.only)
    size = sum(len(sp.encode()) + len(p.encode()) for _, _, sp, p in reqs)
    by_system = {}
    for _, s, sp, p in reqs:
        n = by_system.setdefault(s, [0, 0])
        n[0] += 1
        n[1] += len(enc.encode(sp)) + len(enc.encode(p))
    print(f"label {args.label}, model {DEFAULT_MODEL}, questions file sha256 {questions_sha256()[:12]}")
    for s, (n, tok) in by_system.items():
        v = label_version(args.label)
        print(f"  {s:7} {n:4} requests  ~{tok:,} input tokens  prompt {prompt_file(s, v)} {prompt_sha256(s, v)[:12]}")
    print(f"  total   {len(reqs):4} requests  ~{sum(t for _, t in by_system.values()):,} input tokens, "
          f"{size / 1e6:.1f} MB inline (limit 20 MB); output up to {MAX_OUTPUT_TOKENS} tokens each")

    from google import genai                         # model metadata only, no generation
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])     # keep a reference: a temporary one is closed
    m = client.models.get(model=DEFAULT_MODEL)
    actions = m.supported_actions or []
    print(f"model {m.name}: supported actions {actions}")
    if actions and "batchGenerateContent" not in actions:
        print("WARNING: batchGenerateContent not listed for this model")


def submit(args):
    from google import genai
    from google.genai import types
    job_path = run_dir(args.label) / "job.json"
    if job_path.exists() and not args.force:
        sys.exit(f"{job_path} exists: a job was already submitted for this label (use --force to submit another)")

    reqs = build_requests(args.label, args.only)
    if sum(len(sp.encode()) + len(p.encode()) for _, _, sp, p in reqs) > INLINE_LIMIT:
        sys.exit("batch too large for inline requests")
    inlined = [types.InlinedRequest(
        model=DEFAULT_MODEL, contents=prompt, metadata={"key": key},
        config=types.GenerateContentConfig(system_instruction=system_prompt, max_output_tokens=MAX_OUTPUT_TOKENS,
                                           response_mime_type="application/json", response_schema=SCHEMAS[s]))
        for key, s, system_prompt, prompt in reqs]

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    job = client.batches.create(model=DEFAULT_MODEL, src=inlined, config={"display_name": args.label})
    job_path.write_text(json.dumps({
        "job": job.name, "label": args.label, "model": DEFAULT_MODEL, "requests": len(inlined),
        "submitted_at": datetime.now(timezone.utc).isoformat(), "questions_sha256": questions_sha256(),
        "version": label_version(args.label),
        "prompts": {s: {"file": prompt_file(s, label_version(args.label)),
                        "sha256": prompt_sha256(s, label_version(args.label))} for s in SYSTEMS},
    }, indent=1))
    print(f"submitted {job.name} ({len(inlined)} requests), state {job.state}; saved {job_path}")


# ---------- collecting ----------

def get_job(label):
    from google import genai
    meta = json.loads((run_dir(label) / "job.json").read_text())
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return meta, client.batches.get(name=meta["job"])


def status(args):
    meta, job = get_job(args.label)
    print(f"{meta['job']}: {job.state}  {job.completion_stats or ''}")


def to_answer(system, resp, err, meta):
    """One batch response in the shape generation.answer.answer() returns, so log_run can store it."""
    result = {"system": system, "prompt": meta["prompts"][system]["file"],
              "prompt_sha256": meta["prompts"][system]["sha256"], "data": None, "raw": None, "error": None,
              "llm": {"provider": "gemini", "model": meta["model"], "model_version": meta["model"],
                      "usage": None, "latency_ms": None, "attempts": 1}}
    if err is not None or resp is None:
        result["error"] = str(err or "no response")
        return result
    text = resp.text or ""
    try:
        result["data"] = SCHEMAS[system].model_validate_json(text).model_dump()
    except ValidationError as e:
        result["raw"], result["error"] = text, f"invalid output: {e.errors()[0]['msg']}"
    u = resp.usage_metadata
    result["llm"]["model_version"] = resp.model_version or meta["model"]
    if u:
        result["llm"]["usage"] = {"input": u.prompt_token_count, "output": u.candidates_token_count,
                                  "thinking": u.thoughts_token_count or 0}
    return result


def already_logged(label):
    with connect("app") as conn:
        rows = conn.execute("SELECT question_id, run_id FROM qa_runs WHERE source = 'eval' AND eval_label = %s",
                            (label,)).fetchall()
    return dict(rows)


def collect(args):
    meta, job = get_job(args.label)
    if job.state.name != "JOB_STATE_SUCCEEDED":
        sys.exit(f"job not finished: {job.state}")

    by_question = {}
    for item in job.dest.inlined_responses:
        qid, system = (item.metadata or {})["key"].split(":")
        by_question.setdefault(qid, {})[system] = to_answer(system, item.response, item.error, meta)
    questions_by_id = {q["id"]: q for q in load_questions()}
    for qid, answers in by_question.items():          # memory answers skipped at submit: reuse the stored ones
        if "llm" not in answers:
            reused = stored_memory(questions_by_id[qid]["question"], meta["prompts"]["llm"]["file"])
            if reused:
                answers["llm"] = reused

    recs = {r["question_id"]: r for r in read_jsonl(run_dir(args.label) / "retrieval.jsonl")}
    logged = already_logged(args.label)
    questions = {q["id"]: q for q in load_questions()}
    out, errors = [], 0
    for qid, answers in sorted(by_question.items()):
        r = rebuild(recs[qid])
        for s, a in answers.items():
            if s != "llm" and a["data"]:
                a["check"] = check_citations(a["data"], r)
            errors += a["error"] is not None
        run_id = logged.get(qid) or log_run(r, answers, source="eval", mode="dev", question_id=qid,
                                            eval_label=args.label)
        q = questions.get(qid, {})
        out.append({"question_id": qid, "category": q.get("category"), "question": r.question, "run_id": run_id,
                    "hits": recs[qid]["hits"], "sent_chunk_ids": recs[qid]["sent_chunk_ids"],
                    "answers": {s: {k: a.get(k) for k in ("data", "raw", "error", "check", "llm", "reused_from_run")}
                                for s, a in answers.items()}})

    path = EVAL / "runs" / f"{args.label}.jsonl"
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out))
    print(f"{len(out)} questions, {sum(len(o['answers']) for o in out)} answers ({errors} errors), "
          f"{len(logged)} were already logged; wrote {path}")
    print("next: add an entry to findings/experiment-log.md")


def rerun(args):
    """Answer again, as single online calls (the web app's path), every answer of the run that has an error
    (or exactly the answers named with --answers).
    The logged answer is replaced in place; the JSONL keeps the batch error under 'batch_error'."""
    from generation.answer import answer
    from generation.llm import get_llm
    from common.qalog import replace_answer
    path = EVAL / "runs" / f"{args.label}.jsonl"
    rows = read_jsonl(path)
    recs = {r["question_id"]: r for r in read_jsonl(run_dir(args.label) / "retrieval.jsonl")}
    llm = get_llm()
    for row in rows:
        for s, a in row["answers"].items():
            key = f"{row['question_id']}:{s}"
            if args.answers is not None:
                if key not in args.answers:
                    continue
            elif not a["error"] or (args.only and row["question_id"] not in args.only):
                continue
            r = rebuild(recs[row["question_id"]])
            new = answer(r.question, s, retrieval=r, llm=llm)
            new.setdefault("error", None if new["data"] is not None else "invalid output (online)")
            ok = replace_answer(row["run_id"], s, new)
            row["answers"][s] = {**{k: new.get(k) for k in ("data", "raw", "error", "check", "llm")},
                                 "batch_error": a.get("batch_error", a["error"]), "rerun": "online",
                                 "max_output_tokens": 16384}
            print(f"  {row['question_id']}:{s}  {'ok' if new['data'] else 'FAILED again'}"
                  f"{'' if ok else ' (log update failed)'}  {new['llm']['usage']}")
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in rows))
    print(f"updated {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["prepare", "plan", "submit", "status", "collect", "rerun"])
    ap.add_argument("--label", required=True, help="run name, e.g. 2026-10-04-v1-baseline")
    ap.add_argument("--only", type=lambda s: set(s.split(",")), help="question ids, e.g. q017,q023")
    ap.add_argument("--version", default=CURRENT_VERSION, choices=["v1", "v2"], help="prepare: pipeline version")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--expand", type=int, default=1)
    ap.add_argument("--answers", type=lambda s: set(s.split(",")),
                    help="rerun: these answers even without an error, e.g. q017:llm,q019:llm")
    ap.add_argument("--force", action="store_true", help="submit again although a job exists for this label")
    args = ap.parse_args()
    {"prepare": prepare, "plan": plan, "submit": submit, "status": status, "collect": collect, "rerun": rerun}[args.step](args)


if __name__ == "__main__":
    main()
