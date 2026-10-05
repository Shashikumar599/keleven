#!/usr/bin/env python3
"""
Ask a question about The Office.

Usage:
    set -a; source .env; set +a
    python ask.py "why did andy break up with angela"              # retrieval only: what would be sent
    python ask.py "why did andy break up with angela" --answer     # + answers: RAG, LLM, LLM + RAG
    python ask.py "..." --answer --systems rag llm                 # only some systems
    python ask.py "..." --answer --no-log                          # don't log this question
    python ask.py "..." --k 5 --expand 0 --full
"""
import argparse

from retrieval import CURRENT_VERSION, retrieve
from retrieval.vector import DEFAULT_CHUNK_SET, DEFAULT_MODEL

TITLES = {"rag": "RAG (passages only)", "llm": "LLM (memory only)", "hybrid": "LLM + RAG (both, labelled)"}


def print_retrieval(r, full):
    t = r.timings_ms
    print(f"{r.question!r}")
    print(f"{r.chunk_set} x {r.model} | k={r.k} expand=±{r.expand}"
          f" | {t['total']} ms ({', '.join(f'{k} {v}' for k, v in t.items() if k != 'total')})\n")

    if r.plan:
        res = r.plan.get("sql_result") or {}
        print(f"search text: {r.plan.get('search_text') or '(question as asked)'}")
        print(f"sql: {r.plan.get('sql') or '-'}")
        if res:
            print(f"  -> {res.get('error') or str(len(res['rows'])) + ' rows' + (' (cut)' if res['truncated'] else '')}"
                  f"{' after one fix' if res.get('retried') else ''}")
        print()
    print("hits:")
    for h in r.hits:
        c = h.chunk
        dist = f"{h.distance:.3f}" if h.distance is not None else "  -  "
        if h.scores:
            dist += f"  vector #{h.scores['vector_rank'] or '-'} bm25 #{h.scores['bm25_rank'] or '-'}"
        print(f"  #{h.rank:<2} {dist}  S{c.season}E{c.episode} {c.title}, scenes {c.scene_start}-{c.scene_end}")

    print(f"\npassages ({len(r.passages)}), ordered by their best hit:")
    for p in r.passages:
        a, b = p.scenes
        ranks = ", ".join(f"#{h.rank}" for h in sorted(p.hits, key=lambda h: h.rank))
        print(f"  S{p.season}E{p.episode} {p.title}, scenes {a}-{b} | {len(p.chunks)} chunks | hits {ranks}")
        if full:
            for c in p.chunks:
                print(c.content.split("\n\n", 1)[1])     # drop the per-chunk header, keep scene blocks
                print()


def print_answer(res):
    d, llm = res["data"], res["llm"]
    u = llm["usage"]
    print(f"\n{'=' * 100}\n{TITLES[res['system']]}   [{llm['model_version']}, {res['prompt']}, "
          f"{llm['latency_ms']} ms, tokens in {u['input']} / out {u['output']} / thinking {u['thinking']}]\n")
    if d is None:
        print("(no structured output)\n" + (res["raw"] or ""))
        return

    if "evidence" in d:
        print("evidence:")
        for e in d["evidence"]:
            print(f"  [S{e['season']}E{e['episode']} sc.{e['scene']}] {e['quote']}")
        print()
    if "answerable" in d:
        print(f"answerable: {d['answerable']}")
    if "knows_answer" in d:
        print(f"knows answer: {d['knows_answer']}")
    print(f"\n{d['answer']}\n")
    for key, label in (("uncertain", "uncertain"), ("memory_claims", "from memory"), ("conflicts", "conflicts")):
        if d.get(key):
            print(f"{label}:")
            for item in d[key]:
                print(f"  - {item}")

    c = res["check"]
    if c:
        print(f"\ncitation check: {c['evidence']} evidence quotes, {len(c['bad_evidence'])} problems; "
              f"{c['inline_citations']} inline citations, {len(c['inline_not_sent'])} to scenes not sent")
        for e in c["bad_evidence"]:
            print(f"  ! [S{e['season']}E{e['episode']} sc.{e['scene']}] {', '.join(e['problems'])}: {e['quote'][:80]}")
        for s, e, sc in c["inline_not_sent"]:
            print(f"  ! inline citation [S{s}E{e} sc.{sc}] points to a scene that wasn't sent")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--version", default=CURRENT_VERSION, choices=["v1", "v2"], help="v1 vector, v2 hybrid")
    ap.add_argument("--k", type=int, default=8, help="number of chunks to retrieve")
    ap.add_argument("--expand", type=int, default=1, help="neighbouring chunks to add on each side")
    ap.add_argument("--chunk-set", default=DEFAULT_CHUNK_SET)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--full", action="store_true", help="print the full text of every passage")
    ap.add_argument("--answer", action="store_true", help="also answer with the LLM")
    ap.add_argument("--systems", nargs="+", default=["rag", "llm", "hybrid"], choices=list(TITLES))
    ap.add_argument("--no-log", action="store_true", help="don't write this question to the log tables")
    args = ap.parse_args()

    r = retrieve(args.question, version=args.version, k=args.k, expand=args.expand, chunk_set=args.chunk_set,
                 model=args.model)
    print_retrieval(r, args.full)

    if args.answer:
        from generation.answer import answer
        from generation.llm import get_llm
        llm = get_llm()
        answers = {}
        for system in args.systems:
            answers[system] = answer(args.question, system, r, llm)
            print_answer(answers[system])
        if not args.no_log:
            from common.qalog import log_run
            run_id = log_run(r, answers, source="cli")
            if run_id:
                print(f"\nlogged as run {run_id}")


if __name__ == "__main__":
    main()
