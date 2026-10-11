#!/usr/bin/env python3
"""
Ask a question with pipeline v3 (v2 + graph query). v1 and v2 are unchanged and still run through ask.py.

    set -a; source .env; set +a
    python ask_v3.py "Whom did Michael date?"                       # enhancer + retrieval: what would be sent (1 LLM call)
    python ask_v3.py "Whom did Michael date?" --answer              # + one answer (rag by default)
    python ask_v3.py "..." --answer --systems rag hybrid
Not logged to qa_runs yet; --out FILE writes the plan, the graph rows and the answers as JSON.
"""
import argparse
import json

from generation.answer_v3 import answer_v3, build_prompt_v3
from generation.llm import get_llm
from retrieval import graph as graphrun
from retrieval.hybrid_v3 import retrieve_graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--answer", action="store_true")
    ap.add_argument("--systems", nargs="+", default=["rag"], choices=["rag", "hybrid"])
    ap.add_argument("--out")
    a = ap.parse_args()
    llm = get_llm()
    r = retrieve_graph(a.question, llm=llm)
    p = r.plan
    print(f"search text: {p['search_text'] or '(question as asked)'}\nsql: {p['sql'] or '-'}\ngraph_sql: {p['graph_sql'] or '-'}")
    for name in ("sql_result", "graph_result"):
        res = p.get(name)
        if res:
            print(f"  {name}: {res['error'] or str(len(res['rows'])) + ' rows'}{' (fixed once)' if res.get('retried') else ''}")
    print(f"hits: {len(r.hits)} chunks, {len(r.passages)} passages | {r.timings_ms}")
    out = {"question": a.question, "plan": p, "timings_ms": r.timings_ms, "answers": {}}
    if a.answer:
        for s in a.systems:
            res = answer_v3(a.question, s, r, llm)
            out["answers"][s] = res
            d = res["data"] or {}
            print(f"\n[{s}, {res['prompt']}] {d.get('answer') or res['raw']}\ncitation check: {res['check']}")
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1, default=str)
        print(f"\nwritten {a.out}")


if __name__ == "__main__":
    main()
