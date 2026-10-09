"""
Run both passes (stage 1 extraction, then the review) for many episodes and store every stage in Postgres
(tables extraction_runs / episode_extractions, migration 012). No graph tables yet.

    python -m graph.run_extraction --label 2026-10-10-pilot --pilot             # dry run: the plan and a token estimate
    python -m graph.run_extraction --label 2026-10-10-pilot --pilot --run       # the real run (LLM calls)
    python -m graph.run_extraction --label L --only S7E24,S9E23 --run           # chosen episodes
    python -m graph.run_extraction --label L --all --limit 20 --run             # the first 20 episodes not done yet
    python -m graph.run_extraction --label L --report                           # funnel of a run, no calls

Per episode: raw (what the model returned) -> validated (graph/validate.py) -> review (corrections) -> reviewed (corrected,
validated again). Resumable: an episode that has a reviewed row is skipped. A failed call stores a failed row and is NOT retried
automatically; a rerun skips it and lists it, unless --retry-failed is given.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from psycopg.types.json import Jsonb

from common.db import connect
from generation.llm import DEFAULT_MODEL, get_llm
from graph.extract_one import MAX_OUTPUT, PROMPT as EXTRACT_PROMPT, SCHEMA as EXTRACT_SCHEMA, THINKING, build_prompt
from graph.review import PROMPT as REVIEW_PROMPT, SCHEMA as REVIEW_SCHEMA, apply_corrections, evidence_block, hint_words, with_rids, _words
from graph.validate import load_episode, status as episode_status, validate

PILOT = [(1, 2), (2, 22), (3, 22), (4, 9), (5, 1), (6, 4), (7, 21), (7, 24), (8, 4), (9, 23)]


def tag(path):
    return f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()[:8]}"


def parse_only(text):
    out = []
    for part in text.split(","):
        m = re.fullmatch(r"S(\d+)E(\d+)", part.strip().upper())
        if not m:
            sys.exit(f"bad episode {part!r}, use S7E24")
        out.append((int(m[1]), int(m[2])))
    return out


def all_episodes():
    with connect("app") as c:
        return [(s, e) for s, e in c.execute("SELECT season, episode FROM episodes ORDER BY season, episode").fetchall()]


def get_run(label, params, create):
    hashes = dict(extract_prompt=tag(EXTRACT_PROMPT), review_prompt=tag(REVIEW_PROMPT),
                  extract_schema=tag(EXTRACT_SCHEMA), review_schema=tag(REVIEW_SCHEMA))
    with connect("admin") as c:
        row = c.execute("SELECT run_id, extract_prompt, review_prompt, extract_schema, review_schema FROM extraction_runs WHERE label=%s",
                        (label,)).fetchone()
        if row:
            if list(row[1:]) != list(hashes.values()):
                sys.exit(f"run {label!r} was started with other prompt or schema files {row[1:]}; use a new label")
            return row[0]
        if not create:
            return None
        return c.execute("INSERT INTO extraction_runs (label, model, extract_prompt, review_prompt, extract_schema, review_schema, params) "
                         "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING run_id",
                         (label, DEFAULT_MODEL, *hashes.values(), Jsonb(params))).fetchone()[0]


def write(run_id, season, episode, stage, status, payload=None, issues=None, usage=None, error=None):
    with connect("admin") as c:
        c.execute("""INSERT INTO episode_extractions (run_id, season, episode, stage, status, payload, issues, usage, error)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                     ON CONFLICT (run_id, season, episode, stage) DO UPDATE SET status=EXCLUDED.status, payload=EXCLUDED.payload,
                     issues=EXCLUDED.issues, usage=EXCLUDED.usage, error=EXCLUDED.error, created_at=now()""",
                  (run_id, season, episode, stage, status, Jsonb(payload) if payload is not None else None,
                   Jsonb(issues or []), Jsonb(usage or {}), error))


def existing(run_id):
    with connect("admin") as c:
        rows = c.execute("SELECT season, episode, stage, status FROM episode_extractions WHERE run_id=%s", (run_id,)).fetchall()
    done, failed = set(), set()
    for s, e, stage, st in rows:
        if stage == "reviewed":
            done.add((s, e))
        if st == "failed":
            failed.add((s, e))
    return done, failed


def process(run_id, season, episode, llm, system1, schema1, system2, schema2):
    name = f"S{season}E{episode}"
    with connect("app") as c:
        row = c.execute("SELECT title FROM episodes WHERE season=%s AND episode=%s", (season, episode)).fetchone()
    lines = load_episode(season, episode)
    base = build_prompt(season, episode, lines, row[0] if row else None)
    # stage 1
    try:
        r1 = llm.generate(system=system1, prompt=base, schema=schema1, max_output_tokens=MAX_OUTPUT, thinking_level=THINKING)
    except Exception as e:                      # a failed call is stored, not retried
        write(run_id, season, episode, "raw", "failed", error=f"{type(e).__name__}: {str(e)[:400]}")
        return name, "failed at stage 1", {}
    usage1 = {**r1.usage, "latency_ms": r1.latency_ms, "attempts": r1.attempts}
    clean, rep = validate(r1.text, lines)
    st = episode_status(rep)
    try:
        raw = json.loads(r1.text)
    except ValueError:
        raw = None
    write(run_id, season, episode, "raw", "ok" if raw is not None else "failed", payload=raw, usage=usage1,
          error=None if raw is not None else f"not JSON (output tokens {r1.usage.get('output')}): {r1.text[:300]}")
    write(run_id, season, episode, "validated", st, payload=clean, issues=rep.issues)
    if st == "failed":
        return name, "failed at validation", {"stage1": usage1}
    # review
    try:
        shown = with_rids(clean)
        hints = hint_words(shown, lines)
        prompt2 = (base + "\n\nEXTRACTION\n" + json.dumps(shown, ensure_ascii=False)
                   + "\n\nEVIDENCE (the lines each item cites)\n" + evidence_block(shown, lines)
                   + "\n\nHINTS (words in an item that occur nowhere in the episode text)\n"
                   + "\n".join(f"{k}: {', '.join(v)}" for k, v in hints.items()))
        r2 = llm.generate(system=system2, prompt=prompt2, schema=schema2, max_output_tokens=MAX_OUTPUT, thinking_level=THINKING)
        out = json.loads(r2.text)
    except Exception as e:
        write(run_id, season, episode, "review", "failed", error=f"{type(e).__name__}: {str(e)[:400]}")
        return name, "failed at review", {"stage1": usage1}
    usage2 = {**r2.usage, "latency_ms": r2.latency_ms, "attempts": r2.attempts}
    vocab = set(_words(" ".join(l["speaker"] + " " + l["text"] for l in lines.values())))
    corrections = out.get("corrections", [])
    new, log = apply_corrections(shown, corrections, vocab)
    all_ids = ({c["local_id"] for c in shown["characters"]} | {p["local_id"] for p in shown["places"]}
               | {e["id"] for e in shown["events"]} | {r["rid"] for r in shown["relations"]})
    missed = sorted(all_ids - set(out.get("checked", [])))
    write(run_id, season, episode, "review", "ok", payload={"corrections": corrections, "log": log, "checked": out.get("checked", []),
                                                          "not_checked": missed, "hints": hints}, usage=usage2)
    clean2, rep2 = validate(new, lines)
    write(run_id, season, episode, "reviewed", episode_status(rep2), payload=clean2, issues=rep2.issues)
    applied = sum(1 for e in log if e["status"] == "applied")
    return name, f"ok ({episode_status(rep2)}), {len(corrections)} corrections, {applied} applied", {"stage1": usage1, "review": usage2}


def report(label):
    run_id = get_run(label, {}, create=False)
    if run_id is None:
        sys.exit("no such run")
    with connect("admin") as c:
        rows = c.execute("SELECT season, episode, stage, status, issues, usage, error FROM episode_extractions WHERE run_id=%s", (run_id,)).fetchall()
    by = Counter((r[2], r[3]) for r in rows)
    print(f"run {label}: {len({(r[0], r[1]) for r in rows})} episodes")
    for k in sorted(by):
        print(f"  {k[0]:10} {k[1]:8} {by[k]}")
    for stage in ("validated", "reviewed"):
        rules = Counter((i["severity"], i["rule"]) for r in rows if r[2] == stage for i in r[4])
        print(f"  issues after {stage}:", dict(rules) or "none")
    tok = Counter()
    for r in rows:
        for k in ("input", "output", "thinking"):
            tok[(r[2], k)] += (r[5] or {}).get(k) or 0
    print("  tokens:", {f"{a}.{b}": v for (a, b), v in sorted(tok.items()) if v})
    for r in rows:
        if r[3] == "failed":
            print(f"  FAILED S{r[0]}E{r[1]} {r[2]}: {r[6]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pilot", action="store_true", help="the 10 pilot episodes")
    g.add_argument("--only", help="episodes, e.g. S7E24,S9E23")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--run", action="store_true", help="make the LLM calls (default: dry run)")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        return report(a.label)
    eps = PILOT if a.pilot else parse_only(a.only) if a.only else all_episodes() if a.all else None
    if eps is None:
        sys.exit("choose --pilot, --only or --all")
    params = {"thinking": THINKING, "max_output": MAX_OUTPUT, "workers": a.workers, "review_evidence": True, "hints": True}
    run_id = get_run(a.label, params, create=a.run)
    done, failed = existing(run_id) if run_id else (set(), set())
    todo = [e for e in eps if e not in done and (a.retry_failed or e not in failed)]
    skipped_failed = [e for e in eps if e in failed and e not in done and not a.retry_failed]
    if a.limit:
        todo = todo[:a.limit]
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    est_in = est_out = 0
    for s, e in todo:
        n = len(enc.encode(build_prompt(s, e, load_episode(s, e), None)))
        est_in += (n + 2400) + (n + 12000)
        est_out += 5500
    print(f"run {a.label}: {len(eps)} episodes selected, {len(done & set(eps))} already done, {len(todo)} to run"
          f"{', failed earlier and skipped: ' + str(skipped_failed) if skipped_failed else ''}")
    print(f"estimate for the {len(todo)}: about {est_in // 1000}k input and {est_out // 1000}k output tokens, {a.workers} calls at a time, model {DEFAULT_MODEL}")
    if not a.run:
        print("dry run: nothing sent;", ", ".join(f"S{s}E{e}" for s, e in todo))
        return
    llm = get_llm()
    system1, schema1 = EXTRACT_PROMPT.read_text(), json.loads(EXTRACT_SCHEMA.read_text())
    system2, schema2 = REVIEW_PROMPT.read_text(), json.loads(REVIEW_SCHEMA.read_text())
    if a.retry_failed:
        with connect("admin") as c:
            for s, e in todo:
                c.execute("DELETE FROM episode_extractions WHERE run_id=%s AND season=%s AND episode=%s", (run_id, s, e))
    started = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(process, run_id, s, e, llm, system1, schema1, system2, schema2): (s, e) for s, e in todo}
        for f in as_completed(futs):
            try:
                name, result, _ = f.result()
            except Exception as ex:               # a bug in one episode never stops the others
                s, e = futs[f]
                name, result = f"S{s}E{e}", f"error {type(ex).__name__}: {ex}"
            print(f"  {name}: {result}  [{int(time.time() - started)} s]", flush=True)
    print()
    report(a.label)


if __name__ == "__main__":
    main()
