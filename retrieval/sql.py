"""
Running the enhancer's SQL safely (v2).

The query comes from an LLM, so it is treated as untrusted:
- the database enforces safety: it runs as office_app (read-only transactions, SELECT grants only, 5 s timeout);
- this module adds limits: one SELECT (or WITH) statement only, at most MAX_ROWS rows (the query is wrapped, so
  the cap holds whatever the LLM wrote), and cells cut to MAX_CELL characters.

A result that has season, episode and scene columns points at scenes; scene_refs() lists them so their chunks can
be added to the passages and cited like any other scene.
"""
import re
import time

from common.db import connect

MAX_ROWS = 50
MAX_CELL = 300
_START = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(r";|--|/\*")          # a second statement or a comment


def check(sql):
    """None if the query may run, else the reason it may not."""
    if not _START.match(sql):
        return "only a SELECT (or WITH ... SELECT) query is allowed"
    if _FORBIDDEN.search(sql.strip().rstrip(";")):
        return "only one statement, without comments, is allowed"
    return None


def run(sql):
    """{columns, rows, truncated, error, ms}. Never raises: problems are returned in `error`."""
    t0 = time.perf_counter()
    result = {"columns": [], "rows": [], "truncated": False, "error": None, "ms": 0}
    sql = sql.strip().rstrip(";")
    result["error"] = check(sql)
    if result["error"] is None:
        try:
            with connect("app") as conn:
                cur = conn.execute(f"SELECT * FROM ({sql}) AS q LIMIT {MAX_ROWS + 1}")
                rows = cur.fetchall()
                result["columns"] = [d.name for d in cur.description]
            result["truncated"] = len(rows) > MAX_ROWS
            result["rows"] = [[_cell(v) for v in r] for r in rows[:MAX_ROWS]]
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e).strip().splitlines()[0]}"
    result["ms"] = round(1000 * (time.perf_counter() - t0))
    return result


def _cell(v):
    if isinstance(v, str) and len(v) > MAX_CELL:
        return v[:MAX_CELL] + "…"
    return v if isinstance(v, (int, float, str, bool)) or v is None else str(v)


def scene_refs(result):
    """[(season, episode, scene)] in result order, without duplicates, if the result has those columns."""
    cols = result["columns"]
    if not all(c in cols for c in ("season", "episode", "scene")):
        return []
    i, j, k = cols.index("season"), cols.index("episode"), cols.index("scene")
    seen = []
    for r in result["rows"]:
        ref = (r[i], r[j], r[k])
        if ref not in seen:
            seen.append(ref)
    return seen
