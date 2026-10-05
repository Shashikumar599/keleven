"""
Hybrid retrieval: vector search + BM25 keyword search, merged with reciprocal rank fusion (RRF).

    text --vector search--> top `depth` chunks by meaning      ┐
         --BM25 search----> top `depth` chunks by rare words   ┴--RRF--> top k --neighbour expansion--> passages

RRF uses only ranks, because cosine distances and BM25 scores are on different scales: each list gives a chunk
1 / (rrf_k + rank), and the scores add up. A chunk ranked well in both lists beats one that tops only one of them;
rrf_k = 60 (the value from the original RRF paper) dampens the gap between rank 1 and rank 2 so neither list
dominates. Not tuned: there is no dev split to tune on.

Pipeline v2 is `retrieve_enhanced`: the enhancer (generation/enhance.py) first rewrites the question for search and
may write one SQL query; hybrid search runs on the rewritten text while the SQL runs; scenes the SQL points at are
added as extra passages. Plain `retrieve` (hybrid on the question as is) stays for experiments.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from common.db import connect
from retrieval import sql as sqlrun
from retrieval.keyword import get_index
from retrieval.vector import (DEFAULT_CHUNK_SET, DEFAULT_MODEL, Hit, Retrieval, _chunks, expand_hits,
                              vector_top)

DEPTH = 50        # candidates taken from each list before fusing
RRF_K = 60
SQL_CHUNKS = 4    # at most this many chunks added from scenes the SQL result points at


class EnhanceError(Exception):
    """The enhancer call failed; v2 can't run without it (the request fails)."""


def rrf(*rankings, rrf_k=RRF_K):
    """{chunk_id: fused score} from ranked lists of chunk ids (best first)."""
    fused = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return fused


def search(conn, text, k, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL, depth=DEPTH):
    """Top-k hybrid hits for `text`, and the query's token count."""
    keyword = get_index(chunk_set).search(text, k=depth)                # [(chunk_id, bm25 score)]
    vector, query_tokens = vector_top(conn, text, depth, chunk_set, model)   # [(chunk_id, distance)]
    fused = rrf([c for c, _ in vector], [c for c, _ in keyword])
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    v_rank = {c: i for i, (c, _) in enumerate(vector, start=1)}
    v_dist = dict(vector)
    b_rank = {c: i for i, (c, _) in enumerate(keyword, start=1)}
    b_score = dict(keyword)
    chunks = _chunks(conn, "chunk_id = ANY(%s)", (top,))
    hits = [Hit(rank, v_dist.get(c), chunks[c],
                {"rrf": round(fused[c], 6), "vector_rank": v_rank.get(c), "bm25_rank": b_rank.get(c),
                 "bm25": round(b_score[c], 3) if c in b_score else None})
            for rank, c in enumerate(top, start=1)]
    return hits, query_tokens


def retrieve(question, k=8, expand=1, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL, depth=DEPTH):
    """Plain hybrid retrieval on the question as asked (experiments; not a pipeline version on its own)."""
    t0 = time.perf_counter()
    get_index(chunk_set)                               # built on first use, then cached
    t1 = time.perf_counter()
    with connect("app") as conn:
        hits, query_tokens = search(conn, question, k, chunk_set, model, depth)
        t2 = time.perf_counter()
        passages = expand_hits(conn, hits, chunk_set, expand)
        t3 = time.perf_counter()
    return Retrieval(
        question=question, chunk_set=chunk_set, model=model, k=k, expand=expand,
        hits=hits, passages=passages, query_tokens=query_tokens, method="hybrid",
        timings_ms={"index": round(1000 * (t1 - t0)), "search": round(1000 * (t2 - t1)),
                    "expand": round(1000 * (t3 - t2)), "total": round(1000 * (t3 - t0))},
    )


def _run_sql(question, sql, llm):
    """Run the enhancer's SQL; on error ask the enhancer once to fix it. Returns (result, sql actually run)."""
    from generation.enhance import fix_sql
    result = sqlrun.run(sql)
    result["retried"] = False
    if result["error"]:
        fixed, _ = fix_sql(question, sql, result["error"], llm)
        if fixed and fixed.strip() != sql.strip():
            first_error = result["error"]
            result = sqlrun.run(fixed)
            result.update(retried=True, first_error=first_error)
            sql = fixed
    return result, sql


def _sql_chunks(conn, refs, chunk_set, exclude):
    """Chunks containing the scenes the SQL pointed at, in result order, skipping chunks already hit."""
    out = []
    for season, episode, scene in refs:
        row = conn.execute("""
            SELECT chunk_id FROM chunks_full
            WHERE chunk_set = %s AND season = %s AND episode = %s AND %s BETWEEN scene_start AND scene_end
        """, (chunk_set, season, episode, scene)).fetchone()
        if row and row[0] not in exclude and row[0] not in out:
            out.append(row[0])
        if len(out) == SQL_CHUNKS:
            break
    return out


def retrieve_enhanced(question, k=8, expand=1, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL, depth=DEPTH,
                      llm=None):
    """Pipeline v2: enhancer -> (hybrid search on search_text || SQL) -> passages incl. SQL scenes."""
    from generation.enhance import enhance
    from generation.llm import get_llm
    llm = llm or get_llm()
    t0 = time.perf_counter()
    get_index(chunk_set)
    plan, res = enhance(question, llm)
    if plan is None:
        raise EnhanceError("search preparation failed")
    t1 = time.perf_counter()
    text = plan.get("search_text") or question

    with connect("app") as conn, ThreadPoolExecutor(max_workers=1) as pool:
        sql_future = pool.submit(_run_sql, question, plan["sql"], llm) if plan.get("sql") else None
        hits, query_tokens = search(conn, text, k, chunk_set, model, depth)
        t2 = time.perf_counter()
        sql_result, sql_ran = sql_future.result() if sql_future else (None, None)
        t3 = time.perf_counter()

        if sql_result and not sql_result["error"]:
            extra = _sql_chunks(conn, sqlrun.scene_refs(sql_result), chunk_set, {h.chunk.chunk_id for h in hits})
            chunks = _chunks(conn, "chunk_id = ANY(%s)", (extra,)) if extra else {}
            hits += [Hit(len(hits) + i, None, chunks[c], {"sql": True}) for i, c in enumerate(extra, start=1)]
        passages = expand_hits(conn, hits, chunk_set, expand)
        t4 = time.perf_counter()

    return Retrieval(
        question=question, chunk_set=chunk_set, model=model, k=k, expand=expand,
        hits=hits, passages=passages, query_tokens=query_tokens, method="enhanced",
        plan={"search_text": plan.get("search_text"), "sql": sql_ran or plan.get("sql"),
              "assumptions": plan.get("assumptions"), "sql_result": sql_result,
              "enhancer": {"model_version": res.model_version, "usage": res.usage, "latency_ms": res.latency_ms}},
        timings_ms={"enhance": round(1000 * (t1 - t0)), "search": round(1000 * (t2 - t1)),
                    "sql_wait": round(1000 * (t3 - t2)), "expand": round(1000 * (t4 - t3)),
                    "total": round(1000 * (t4 - t0))},
    )
