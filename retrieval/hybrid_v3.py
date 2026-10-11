"""
Pipeline v3 retrieval: v2 (hybrid search + optional SQL scenes) plus the graph query of the enhancer.

    question --enhance_v3.md--> {search_text, sql, graph_sql, assumptions}
             hybrid search on search_text  ||  sql  ||  graph_sql (rows with their transcript lines)
             --> passages (incl. SQL scenes) + SQL result + graph result

v2's retrieval/hybrid.py is only imported (search, SQL helpers, constants), never changed.
"""
import time
import types
from concurrent.futures import ThreadPoolExecutor

from common.db import connect
from retrieval import graph as graphrun
from retrieval import sql as sqlrun
from retrieval.hybrid import DEPTH, EnhanceError, _sql_chunks, search
from retrieval.keyword import get_index
from retrieval.vector import DEFAULT_CHUNK_SET, DEFAULT_MODEL, Hit, Retrieval, _chunks, expand_hits


def _run_query(question, field, query, llm, runner):
    """Run a query; on error ask the enhancer once to fix it. Returns (result, query actually run)."""
    from generation.enhance_v3 import fix_query
    result = runner(query)
    result["retried"] = False
    if result["error"]:
        fixed, _ = fix_query(question, field, query, result["error"], llm)
        if fixed and fixed.strip() != query.strip():
            first_error = result["error"]
            result = runner(fixed)
            result.update(retried=True, first_error=first_error)
            query = fixed
    return result, query


def retrieve_graph(question, k=8, expand=1, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL, depth=DEPTH, llm=None,
                   enhancement=None):
    """Pipeline v3: enhancer -> (hybrid search || SQL || graph SQL) -> passages + SQL result + graph result.
    `enhancement` = {"plan": {...}, "model_version", "usage", "latency_ms"} when the enhancer already ran (the eval batch); the
    enhancer call is then skipped."""
    from generation.enhance_v3 import enhance3
    from generation.llm import get_llm
    llm = llm or get_llm()
    t0 = time.perf_counter()
    get_index(chunk_set)
    if enhancement:
        plan, res = enhancement["plan"], types.SimpleNamespace(model_version=enhancement.get("model_version"),
                                                                usage=enhancement.get("usage"), latency_ms=enhancement.get("latency_ms"))
    else:
        plan, res = enhance3(question, llm)
    if plan is None:
        raise EnhanceError("search preparation failed")
    t1 = time.perf_counter()
    text = plan.get("search_text") or question

    with connect("app") as conn, ThreadPoolExecutor(max_workers=2) as pool:
        sql_future = pool.submit(_run_query, question, "sql", plan["sql"], llm, sqlrun.run) if plan.get("sql") else None
        graph_future = pool.submit(_run_query, question, "graph_sql", plan["graph_sql"], llm, graphrun.run) if plan.get("graph_sql") else None
        hits, query_tokens = search(conn, text, k, chunk_set, model, depth)
        t2 = time.perf_counter()
        sql_result, sql_ran = sql_future.result() if sql_future else (None, None)
        graph_result, graph_ran = graph_future.result() if graph_future else (None, None)
        if graph_result:
            graphrun.attach_lines(graph_result)
        t3 = time.perf_counter()

        if sql_result and not sql_result["error"]:
            extra = _sql_chunks(conn, sqlrun.scene_refs(sql_result), chunk_set, {h.chunk.chunk_id for h in hits})
            chunks = _chunks(conn, "chunk_id = ANY(%s)", (extra,)) if extra else {}
            hits += [Hit(len(hits) + i, None, chunks[c], {"sql": True}) for i, c in enumerate(extra, start=1)]
        passages = expand_hits(conn, hits, chunk_set, expand)
        t4 = time.perf_counter()

    return Retrieval(
        question=question, chunk_set=chunk_set, model=model, k=k, expand=expand,
        hits=hits, passages=passages, query_tokens=query_tokens, method="graph",
        plan={"search_text": plan.get("search_text"), "sql": sql_ran or plan.get("sql"),
              "assumptions": plan.get("assumptions"), "sql_result": sql_result,
              "graph_sql": graph_ran or plan.get("graph_sql"), "graph_result": graph_result,
              "enhancer": {"model_version": res.model_version, "usage": res.usage, "latency_ms": res.latency_ms}},
        timings_ms={"enhance": round(1000 * (t1 - t0)), "search": round(1000 * (t2 - t1)),
                    "queries_wait": round(1000 * (t3 - t2)), "expand": round(1000 * (t4 - t3)),
                    "total": round(1000 * (t4 - t0))},
    )
