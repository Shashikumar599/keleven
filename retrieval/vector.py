"""
Vector retrieval (Phase 1, Part 4, v1).

    question --embed (query mode)--> vector --exact cosine search--> top-k chunks
             --neighbour expansion (+/- n positions, same episode)--> passages

An "experiment" is (chunk set x embedding model); retrieval always searches exactly one. Questions are embedded
with the same model and dimensions as the chunks, in "query" mode. Connects as the read-only app role.

No vector index: exact search over one experiment's ~4,700 vectors takes milliseconds and has perfect recall.
"""
import time
from dataclasses import dataclass, field

from common.db import connect
from common.voyage import embed, to_pgvector

DEFAULT_CHUNK_SET = "pack_300t_3s_80min"
DEFAULT_MODEL = "voyage-4-large@1024"


@dataclass
class Chunk:
    chunk_id: int
    season: int
    episode: int
    title: str
    position: int
    scene_start: int
    scene_end: int
    content: str


@dataclass
class Hit:
    rank: int                     # 1 = closest
    distance: float | None        # cosine distance (0 = same direction); only the ranking is meaningful.
                                  # None for a hybrid hit that vector search didn't return
    chunk: Chunk
    scores: dict = field(default_factory=dict)      # hybrid only: vector_rank, bm25_rank, bm25, rrf


@dataclass
class Passage:
    """Consecutive chunks of one episode: one or more hits plus their neighbours, merged where they overlap."""
    season: int
    episode: int
    title: str
    chunks: list = field(default_factory=list)       # in episode order
    hits: list = field(default_factory=list)         # the matched chunks among them

    @property
    def best_rank(self):
        return min(h.rank for h in self.hits)

    @property
    def scenes(self):
        return self.chunks[0].scene_start, self.chunks[-1].scene_end


@dataclass
class Retrieval:
    question: str
    chunk_set: str
    model: str
    k: int
    expand: int
    hits: list
    passages: list
    query_tokens: int
    timings_ms: dict
    method: str = "vector"        # "vector" (v1), "hybrid" (experiments) or "enhanced" (v2: hybrid + enhancer + SQL)
    plan: dict | None = None      # v2: the enhancer's output and the SQL result (logged in qa_runs.plan)


def _experiment(conn, chunk_set, model):
    row = conn.execute("""
        SELECT s.chunk_set_id, m.model_id, m.model, m.dimensions
        FROM chunk_sets s, embedding_models m
        WHERE s.name = %s AND m.name = %s
    """, (chunk_set, model)).fetchone()
    if not row:
        raise ValueError(f"no experiment {chunk_set} x {model}")
    return row


def _chunks(conn, where, params):
    rows = conn.execute(f"""
        SELECT chunk_id, season, episode, title, position, scene_start, scene_end, content
        FROM chunks_full WHERE {where}
    """, params).fetchall()
    return {r[0]: Chunk(*r) for r in rows}


def _passages(hits, neighbours):
    """Group hits and neighbours by episode, then merge runs of consecutive positions into passages."""
    by_episode = {}
    for c in neighbours.values():
        by_episode.setdefault((c.season, c.episode), []).append(c)
    hit_ids = {h.chunk.chunk_id: h for h in hits}
    passages = []
    for (season, episode), chunks in by_episode.items():
        chunks.sort(key=lambda c: c.position)
        current = None
        for c in chunks:
            if current is None or c.position != current.chunks[-1].position + 1:
                current = Passage(season, episode, c.title)
                passages.append(current)
            current.chunks.append(c)
            if c.chunk_id in hit_ids:
                current.hits.append(hit_ids[c.chunk_id])
    passages = [p for p in passages if p.hits]
    return sorted(passages, key=lambda p: p.best_rank)


def vector_top(conn, question, n, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL):
    """[(chunk_id, distance)] for the n closest chunks, and the query's token count."""
    chunk_set_id, model_id, provider_model, dims = _experiment(conn, chunk_set, model)
    (qvec,), query_tokens = embed([question], provider_model, dims, "query")
    top = conn.execute("""
        SELECT chunk_id, embedding <=> %s::vector AS distance
        FROM chunk_embeddings
        WHERE model_id = %s AND chunk_set_id = %s
        ORDER BY distance
        LIMIT %s
    """, (to_pgvector(qvec), model_id, chunk_set_id, n)).fetchall()
    return top, query_tokens


def expand_hits(conn, hits, chunk_set, expand):
    """Passages: the hits plus +/- `expand` neighbouring chunks of the same episode, merged where they touch."""
    neighbours = _chunks(conn, """
        chunk_set = %s AND (season, episode, position) IN (
            SELECT h.season, h.episode, h.position + d
            FROM unnest(%s::int[], %s::int[], %s::int[]) AS h(season, episode, position),
                 generate_series(-%s::int, %s::int) AS d)
    """, (chunk_set,
          [h.chunk.season for h in hits], [h.chunk.episode for h in hits], [h.chunk.position for h in hits],
          expand, expand))
    return _passages(hits, neighbours)


def retrieve(question, k=8, expand=1, chunk_set=DEFAULT_CHUNK_SET, model=DEFAULT_MODEL):
    """Top-k chunks for a question by cosine distance, plus passages built from them and +/- `expand`
    neighbouring chunks."""
    t0 = time.perf_counter()
    with connect("app") as conn:
        t1 = time.perf_counter()
        top, query_tokens = vector_top(conn, question, k, chunk_set, model)
        t2 = time.perf_counter()
        hit_chunks = _chunks(conn, "chunk_id = ANY(%s)", ([cid for cid, _ in top],))
        hits = [Hit(rank, dist, hit_chunks[cid]) for rank, (cid, dist) in enumerate(top, start=1)]
        passages = expand_hits(conn, hits, chunk_set, expand)
        t3 = time.perf_counter()

    return Retrieval(
        question=question, chunk_set=chunk_set, model=model, k=k, expand=expand,
        hits=hits, passages=passages, query_tokens=query_tokens,
        timings_ms={"connect": round(1000 * (t1 - t0)), "embed+search": round(1000 * (t2 - t1)),
                    "expand": round(1000 * (t3 - t2)), "total": round(1000 * (t3 - t0))},
    )
