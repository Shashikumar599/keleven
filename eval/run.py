"""
Run the question set through the pipeline as one Gemini batch job.

    python -m eval.run prepare --label 2026-10-04-v1-baseline --version v1    retrieval for every question
                                                                   (v1: Voyage only; v2: also one enhancer
                                                                   LLM call per question, not batched; v3: the
                                                                   same, and the enhancer also writes a graph query)
    python -m eval.run enhance-submit --label ... --version v3     v3 only: ONE batch job for the enhancer calls (LLM calls)
    python -m eval.run enhance-status / enhance-collect --label ... job state / fetch the plans into enhancer_plans.jsonl
                                                                   (then prepare --version v3 uses them: no online enhancer calls)
    python -m eval.run plan    --label ...                         what would be submitted: counts, size, token estimate
    python -m eval.run submit  --label ...                         build the prompts, submit ONE batch job (LLM calls)
    python -m eval.run status  --label ...                         job state
    python -m eval.run collect --label ...                         fetch answers, check citations, log, write JSONL
    python -m eval.run rerun   --label ...                         re-answer failed answers as single online calls
    python -m eval.run online  --label ... --only qNNN             answer questions missing from a run, online

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
from generation.answer_v3 import PROMPT_FILES_V3, answer_v3, build_prompt_v3, check_citations_v3, prompt_sha256_v3
from generation.llm import DEFAULT_MODEL
from retrieval import CURRENT_VERSION, retrieve
from retrieval import graph as graphrun
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


# ---------- per-version prompt files, prompt building and citation checks (v1, v2 as before; v3 has its own) ----------

def prompt_file_for(system, version):
    return PROMPT_FILES_V3[system] if version == "v3" else prompt_file(system, version)


def prompt_sha_for(system, version):
    return prompt_sha256_v3(system) if version == "v3" else prompt_sha256(system, version)


def load_prompt_for(system, version):
    from generation.answer import PROMPTS
    return (PROMPTS / prompt_file_for(system, version)).read_text()


def build_prompt_for(version, question, retrieval=None):
    return build_prompt_v3(question, retrieval) if version == "v3" else build_prompt(question, retrieval)


def check_for(version, data, retrieval):
    return check_citations_v3(data, retrieval) if version == "v3" else check_citations(data, retrieval)


def answer_for(version, question, system, retrieval, llm):
    if version == "v3":
        return answer_v3(question, system, retrieval, llm)
    from generation.answer import answer
    return answer(question, system, retrieval=retrieval, llm=llm, version=version)


# ---------- retrieval, stored as ids and rebuilt from the chunks table ----------

def _plan_for_file(plan):
    """The plan as stored in retrieval.jsonl. The graph result's transcript lines are left out (the file holds ids, never
    transcript text); rebuild() fetches them again from the same line_ids."""
    g = (plan or {}).get("graph_result")
    if not g or "lines" not in g:
        return plan
    return {**plan, "graph_result": {k: v for k, v in g.items() if k != "lines"}}


def retrieval_record(qid, r, version):
    return {"question_id": qid, "question": r.question, "version": version, "method": r.method,
            "chunk_set": r.chunk_set, "model": r.model,
            "k": r.k, "expand": r.expand, "query_tokens": r.query_tokens, "timings_ms": r.timings_ms,
            "hits": [{"rank": h.rank, "chunk_id": h.chunk.chunk_id, "distance": h.distance, **h.scores}
                     for h in r.hits],
            "sent_chunk_ids": [c.chunk_id for p in r.passages for c in p.chunks], "plan": _plan_for_file(r.plan)}


def rebuild(rec):
    """The Retrieval object for a stored record: same hits, same passages, same prompt."""
    with connect("app") as conn:
        chunks = _chunks(conn, "chunk_id = ANY(%s)", (rec["sent_chunk_ids"],))
    hits = [Hit(h["rank"], h["distance"], chunks[h["chunk_id"]],
                {k: v for k, v in h.items() if k not in ("rank", "chunk_id", "distance")}) for h in rec["hits"]]
    plan = rec.get("plan")
    if plan and plan.get("graph_result") and "lines" not in plan["graph_result"]:
        graphrun.attach_lines(plan["graph_result"])         # v3: the transcript lines shown with the graph rows
    return Retrieval(question=rec["question"], chunk_set=rec["chunk_set"], model=rec["model"], k=rec["k"],
                     expand=rec["expand"], hits=hits, passages=_passages(hits, chunks),
                     query_tokens=rec["query_tokens"], timings_ms=rec["timings_ms"],
                     method=rec.get("method", "vector"),          # records from before v2 are vector
                     plan=plan)


def prepare(args):
    path = run_dir(args.label) / "retrieval.jsonl"
    existing = read_jsonl(path)
    other = {r.get("version", "v1") for r in existing} - {args.version}
    if other:
        sys.exit(f"{path} holds {', '.join(sorted(other))} retrieval; use a new label for {args.version}")
    done = {r["question_id"] for r in existing}
    todo = [q for q in load_questions(args.only) if q["id"] not in done]
    print(f"{args.version}: {len(done)} already retrieved, {len(todo)} to go (k={args.k}, expand={args.expand})")
    plans = {x["question_id"]: x for x in read_jsonl(run_dir(args.label) / "enhancer_plans.jsonl")} if args.version == "v3" else {}
    if args.version == "v3":
        print(f"enhancer plans from the batch: {len(plans)}" + ("" if plans else " (none: the enhancer runs online per question)"))
    with path.open("a") as f:
        for q in todo:
            extra = {"enhancement": plans[q["id"]]} if q["id"] in plans else {}
            if args.version == "v3" and plans and not extra:
                print(f"  {q['id']}: no batch plan, the enhancer runs online")
            r = retrieve(q["question"], version=args.version, k=args.k, expand=args.expand, **extra)
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
    prompts = {s: load_prompt_for(s, version) for s in SYSTEMS}
    out = []
    for q in questions:
        r = rebuild(recs[q["id"]])
        for s in SYSTEMS:
            if s == "llm" and stored_memory(q["question"], prompt_file_for("llm", version)):
                continue                  # memory doesn't depend on the version: reused at collect, no new call
            out.append((f"{q['id']}:{s}", s, prompts[s], build_prompt_for(version, q["question"], r if s != "llm" else None)))
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
        print(f"  {s:7} {n:4} requests  ~{tok:,} input tokens  prompt {prompt_file_for(s, v)} {prompt_sha_for(s, v)[:12]}")
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
        "prompts": {s: {"file": prompt_file_for(s, label_version(args.label)),
                        "sha256": prompt_sha_for(s, label_version(args.label))} for s in SYSTEMS},
    }, indent=1))
    print(f"submitted {job.name} ({len(inlined)} requests), state {job.state}; saved {job_path}")


# ---------- v3: the enhancer as one batch job (stage 1), then the answers as a second one (stage 2) ----------

def enhance_requests(args):
    from generation.answer import PROMPTS
    from generation.enhance_v3 import PROMPT_FILE
    system = (PROMPTS / PROMPT_FILE).read_text()
    return system, [(q["id"], f"Question: {q['question']}") for q in load_questions(args.only)]


def enhance_submit(args):
    from google import genai
    from google.genai import types
    from generation.enhance import MAX_OUTPUT_TOKENS as ENH_TOKENS, THINKING_LEVEL
    from generation.enhance_v3 import PROMPT_FILE, Plan3
    if args.version != "v3":
        sys.exit("the enhancer batch is for v3 only (use --version v3)")
    job_path = run_dir(args.label) / "enhance_job.json"
    if job_path.exists() and not args.force:
        sys.exit(f"{job_path} exists: an enhancer job was already submitted for this label (use --force to submit another)")
    system, reqs = enhance_requests(args)
    inlined = [types.InlinedRequest(
        model=DEFAULT_MODEL, contents=prompt, metadata={"key": qid},
        config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=ENH_TOKENS,
                                           response_mime_type="application/json", response_schema=Plan3,
                                           thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL)))
        for qid, prompt in reqs]
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    job = client.batches.create(model=DEFAULT_MODEL, src=inlined, config={"display_name": f"{args.label}-enhancer"})
    job_path.write_text(json.dumps({
        "job": job.name, "label": args.label, "model": DEFAULT_MODEL, "requests": len(inlined), "stage": "enhancer",
        "submitted_at": datetime.now(timezone.utc).isoformat(), "questions_sha256": questions_sha256(),
        "prompt": {"file": PROMPT_FILE, "sha256": hashlib.sha256(system.encode()).hexdigest()}}, indent=1))
    print(f"submitted {job.name} ({len(inlined)} enhancer requests), state {job.state}; saved {job_path}")


def _enhance_job(label):
    from google import genai
    meta = json.loads((run_dir(label) / "enhance_job.json").read_text())
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return meta, client.batches.get(name=meta["job"])


def enhance_status(args):
    meta, job = _enhance_job(args.label)
    print(f"{meta['job']}: {job.state}  {job.completion_stats or ''}")


def enhance_collect(args):
    from generation.enhance_v3 import Plan3
    meta, job = _enhance_job(args.label)
    if job.state.name != "JOB_STATE_SUCCEEDED":
        sys.exit(f"job not finished: {job.state}")
    path = run_dir(args.label) / "enhancer_plans.jsonl"
    done = {r["question_id"] for r in read_jsonl(path)}
    ok = bad = 0
    with path.open("a") as f:
        for item in job.dest.inlined_responses:
            qid = (item.metadata or {})["key"]
            if qid in done:
                continue
            try:
                if item.error is not None or item.response is None:
                    raise ValueError(str(item.error or "no response"))
                plan = Plan3.model_validate_json(item.response.text or "").model_dump()
            except (ValidationError, ValueError) as e:
                print(f"  {qid}: no plan ({e}); prepare will run the enhancer online for it")
                bad += 1
                continue
            u = item.response.usage_metadata
            f.write(json.dumps({"question_id": qid, "plan": plan, "model_version": item.response.model_version or meta["model"],
                                "usage": {"input": u.prompt_token_count, "output": u.candidates_token_count,
                                          "thinking": u.thoughts_token_count or 0} if u else None,
                                "latency_ms": None, "batch": True}) + "\n")
            ok += 1
    print(f"{ok} plans written, {bad} failed; {path}")
    print("next: prepare --version v3 (uses the plans), then plan and submit for the answers")


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
    version = label_version(args.label)
    logged = already_logged(args.label)
    questions = {q["id"]: q for q in load_questions()}
    out, errors = [], 0
    for qid, answers in sorted(by_question.items()):
        r = rebuild(recs[qid])
        for s, a in answers.items():
            if s != "llm" and a["data"]:
                a["check"] = check_for(version, a["data"], r)
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
    from generation.llm import get_llm
    from common.qalog import replace_answer
    path = EVAL / "runs" / f"{args.label}.jsonl"
    rows = read_jsonl(path)
    recs = {r["question_id"]: r for r in read_jsonl(run_dir(args.label) / "retrieval.jsonl")}
    version = label_version(args.label)
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
            new = answer_for(version, r.question, s, r, llm)
            new.setdefault("error", None if new["data"] is not None else "invalid output (online)")
            ok = replace_answer(row["run_id"], s, new)
            row["answers"][s] = {**{k: new.get(k) for k in ("data", "raw", "error", "check", "llm")},
                                 "batch_error": a.get("batch_error", a["error"]), "rerun": "online",
                                 "max_output_tokens": 16384}
            print(f"  {row['question_id']}:{s}  {'ok' if new['data'] else 'FAILED again'}"
                  f"{'' if ok else ' (log update failed)'}  {new['llm']['usage']}")
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in rows))
    print(f"updated {path}")


def online(args):
    """Answer questions missing from a label's run with single online calls (e.g. a question added after the
    batch). Retrieval must already be prepared; stored memory answers are reused. Appends to <label>.jsonl."""
    from generation.llm import get_llm
    path = EVAL / "runs" / f"{args.label}.jsonl"
    rows = read_jsonl(path)
    have = {r["question_id"] for r in rows}
    recs = {r["question_id"]: r for r in read_jsonl(run_dir(args.label) / "retrieval.jsonl")}
    version = label_version(args.label)
    questions = [q for q in load_questions(args.only) if q["id"] not in have]
    llm = get_llm()
    for q in questions:
        if q["id"] not in recs:
            sys.exit(f"no retrieval for {q['id']}: run prepare --only {q['id']} first")
        r = rebuild(recs[q["id"]])
        answers = {}
        for s in SYSTEMS:
            reused = stored_memory(q["question"], prompt_file_for("llm", version)) if s == "llm" else None
            answers[s] = reused or answer_for(version, q["question"], s, r, llm)
            answers[s].setdefault("error", None if answers[s].get("data") is not None else "invalid output")
            if s != "llm" and answers[s].get("data"):
                answers[s]["check"] = check_for(version, answers[s]["data"], r)
        run_id = log_run(r, answers, source="eval", mode="dev", question_id=q["id"], eval_label=args.label)
        rows.append({"question_id": q["id"], "category": q.get("category"), "question": r.question, "run_id": run_id,
                     "hits": recs[q["id"]]["hits"], "sent_chunk_ids": recs[q["id"]]["sent_chunk_ids"], "online": True,
                     "answers": {s: {k: a.get(k) for k in ("data", "raw", "error", "check", "llm", "reused_from_run")}
                                 for s, a in answers.items()}})
        print(f"  {q['id']}: " + ", ".join(f"{s} {'reused' if a.get('reused_from_run') else 'ok' if a.get('data') else 'FAILED'}"
                                          for s, a in answers.items()) + f"  (run {run_id})")
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["prepare", "plan", "submit", "status", "collect", "rerun", "online",
                                   "enhance-submit", "enhance-status", "enhance-collect"])
    ap.add_argument("--label", required=True, help="run name, e.g. 2026-10-04-v1-baseline")
    ap.add_argument("--only", type=lambda s: set(s.split(",")), help="question ids, e.g. q017,q023")
    ap.add_argument("--version", default=CURRENT_VERSION, choices=["v1", "v2", "v3"], help="prepare: pipeline version")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--expand", type=int, default=1)
    ap.add_argument("--answers", type=lambda s: set(s.split(",")),
                    help="rerun: these answers even without an error, e.g. q017:llm,q019:llm")
    ap.add_argument("--force", action="store_true", help="submit again although a job exists for this label")
    args = ap.parse_args()
    {"prepare": prepare, "plan": plan, "submit": submit, "status": status, "collect": collect, "rerun": rerun, "online": online,
     "enhance-submit": enhance_submit, "enhance-status": enhance_status, "enhance-collect": enhance_collect}[args.step](args)


if __name__ == "__main__":
    main()
