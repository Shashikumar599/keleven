"""
Pipeline v3 retrieval: v2 (hybrid search + optional SQL scenes) plus the graph query of the enhancer.

    question --enhance_v3.md--> {search_text, sql, graph_sql, assumptions}
             hybrid search on search_text  ||  sql  ||  graph_sql (rows with their transcript lines)
             --> passages (incl. the scenes the SQL and graph rows point at, unless context is "none") + SQL result + graph result

v2's retrieval/hybrid.py is only imported (search, SQL helpers, constants), never changed.
"""
import time
import types
from concurrent.futures import ThreadPoolExecutor

from common.db import connect
from retrieval import graph as graphrun
from retrieval import sql as sqlrun
from retrieval.hybrid import DEPTH, EnhanceError, search
from retrieval.keyword import get_index
from retrieval.vector import DEFAULT_CHUNK_SET, DEFAULT_MODEL, Hit, Retrieval, _chunks, expand_hits


SCENE_CHUNKS = 6      # at most this many chunks are added from the scenes the SQL and graph rows point at (v2: 4, SQL only)


def scene_targets(context, sql_result, graph_result):
    """[((season, episode, scene), source)] the scenes the queries point at, best first: scenes both queries point at, then SQL
    rows in result order, then the transcript lines shown with the graph rows. Empty when the enhancer said context "none"."""
    if context == "none":
        return []
    sql_refs = sqlrun.scene_refs(sql_result) if sql_result and not sql_result["error"] else []
    graph_refs = []
    if graph_result and not graph_result["error"]:
        for lines in graph_result.get("lines") or []:
            for l in lines:
                ref = (l["season"], l["episode"], l["scene"])
                if ref not in graph_refs:
                    graph_refs.append(ref)
    both = [r for r in sql_refs if r in graph_refs]
    ordered = [(r, "sql" if r in sql_refs else "graph") for r in both + sql_refs + graph_refs]
    seen, out = set(), []
    for ref, source in ordered:
        if ref not in seen:
            seen.add(ref)
            out.append((ref, source))
    return out


def scene_chunks(conn, targets, chunk_set, exclude, cap=SCENE_CHUNKS):
    """[(chunk_id, source)]: the chunks that contain the target scenes, skipping chunks already hit, at most `cap`."""
    out = []
    for (season, episode, scene), source in targets:
        row = conn.execute("""
            SELECT chunk_id FROM chunks_full
            WHERE chunk_set = %s AND season = %s AND episode = %s AND %s BETWEEN scene_start AND scene_end
        """, (chunk_set, season, episode, scene)).fetchone()
        if row and row[0] not in exclude and all(row[0] != c for c, _ in out):
            out.append((row[0], source))
        if len(out) == cap:
            break
    return out


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

        context = plan.get("context") or "scene"
        extra = scene_chunks(conn, scene_targets(context, sql_result, graph_result), chunk_set, {h.chunk.chunk_id for h in hits})
        chunks = _chunks(conn, "chunk_id = ANY(%s)", ([c for c, _ in extra],)) if extra else {}
        hits += [Hit(len(hits) + i, None, chunks[c], {source: True}) for i, (c, source) in enumerate(extra, start=1)]
        passages = expand_hits(conn, hits, chunk_set, expand)
        t4 = time.perf_counter()

    return Retrieval(
        question=question, chunk_set=chunk_set, model=model, k=k, expand=expand,
        hits=hits, passages=passages, query_tokens=query_tokens, method="graph",
        plan={"search_text": plan.get("search_text"), "sql": sql_ran or plan.get("sql"),
              "assumptions": plan.get("assumptions"), "context": context, "sql_result": sql_result,
              "graph_sql": graph_ran or plan.get("graph_sql"), "graph_result": graph_result,
              "enhancer": {"model_version": res.model_version, "usage": res.usage, "latency_ms": res.latency_ms}},
        timings_ms={"enhance": round(1000 * (t1 - t0)), "search": round(1000 * (t2 - t1)),
                    "queries_wait": round(1000 * (t3 - t2)), "expand": round(1000 * (t4 - t3)),
                    "total": round(1000 * (t4 - t0))},
    )
