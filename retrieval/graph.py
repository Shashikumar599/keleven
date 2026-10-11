"""
Running the enhancer's graph SQL (pipeline v3) and turning its rows into evidence.

The query is untrusted, as in retrieval/sql.py, and uses the same checks and limits (one SELECT, MAX_ROWS rows, the read-only
office_app role with its timeout). Unlike sql.py, values stay as they are (line_ids stays a list), because the rows are enriched:
every row that has `line_ids` gets up to LINES_PER_ROW of those transcript lines (speaker and text) beside it, so the answer can cite
the scene and quote the line. A row that has a `quote` column (relations) shows that quote as well.
"""
import time

from common.db import connect
from retrieval import sql as sqlrun

LINES_PER_ROW = 2
MAX_LINE_CHARS = 220


def _plain(v):
    """Values that survive json.dumps (the plan is logged as JSON): numbers, text, lists and dicts stay, the rest becomes text."""
    if isinstance(v, (int, float, str, bool, type(None))):
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return str(v)


def run(sql):
    """{columns, rows, truncated, error, ms}; rows keep their values (line_ids is a list). Never raises."""
    t0 = time.perf_counter()
    result = {"columns": [], "rows": [], "truncated": False, "error": None, "ms": 0}
    sql = sql.strip().rstrip(";")
    result["error"] = sqlrun.check(sql)
    if result["error"] is None:
        try:
            with connect("app") as conn:
                cur = conn.execute(f"SELECT * FROM ({sql}) AS q LIMIT {sqlrun.MAX_ROWS + 1}")
                rows = cur.fetchall()
                result["columns"] = [d.name for d in cur.description]
            result["truncated"] = len(rows) > sqlrun.MAX_ROWS
            result["rows"] = [[_plain(v) for v in r] for r in rows[:sqlrun.MAX_ROWS]]
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e).strip().splitlines()[0]}"
    result["ms"] = round(1000 * (time.perf_counter() - t0))
    return result


def attach_lines(result):
    """Adds result["lines"]: one list per row of {id, season, episode, scene, speaker, text} (the first lines of its line_ids)."""
    cols = result["columns"]
    result["lines"] = [[] for _ in result["rows"]]
    if result["error"] or "line_ids" not in cols:
        return result
    i = cols.index("line_ids")
    picks = [list(r[i] or [])[:LINES_PER_ROW] for r in result["rows"]]
    wanted = sorted({x for p in picks for x in p})
    if not wanted:
        return result
    with connect("app") as conn:
        found = {r[0]: r for r in conn.execute("SELECT id, season, episode, scene, speaker, text FROM lines WHERE id = ANY(%s)", (wanted,))}
    for n, p in enumerate(picks):
        result["lines"][n] = [dict(zip(("id", "season", "episode", "scene", "speaker", "text"), found[x])) for x in p if x in found]
    return result


def scene_refs(result):
    """{(season, episode, scene)} of the lines shown with the rows."""
    return {(l["season"], l["episode"], l["scene"]) for ls in result.get("lines", []) for l in ls}


def quote_text(result):
    """All text shown with the rows (line texts and quote columns), lower-cased: what a citation check may match against."""
    parts = [x for ls in result.get("lines", []) for l in ls for x in (l["text"], f"{l['speaker']}: {l['text']}")]
    if "quote" in result["columns"]:
        j = result["columns"].index("quote")
        parts += [r[j] for r in result["rows"] if r[j]]
    return " ".join(parts).lower()


def _cell(name, value, row, cols):
    if value is None:
        return "-"
    if name in ("a_name", "b_name"):
        tier = row[cols.index(name[0] + "_tier")] if name[0] + "_tier" in cols else None
        return f"{value} (possible match)" if tier == "possible" else str(value)
    return str(value)


def format_block(plan):
    """The graph evidence block for the answer prompt, or None when no graph query ran."""
    r = (plan or {}).get("graph_result")
    if not r:
        return None
    head = f"Graph result, facts extracted from every episode of the show:\nQuery: {plan['graph_sql']}"
    if plan.get("assumptions"):
        head += f"\nHow the question was read: {plan['assumptions']}"
    if r["error"]:
        return f"{head}\nThe query failed ({r['error']}); there is no graph result."
    cols = [c for c in r["columns"] if c != "line_ids" and not c.endswith("_tier")]
    n = len(r["rows"])
    note = f"{n} row{'' if n == 1 else 's'}" + (", cut: more rows exist" if r["truncated"] else "")
    out = [f"{head}\nRows ({note}); episodes like 311 mean S3E11:", " | ".join(cols)]
    for row, lines in zip(r["rows"], r.get("lines") or [[] for _ in r["rows"]]):
        out.append(" | ".join(_cell(c, row[r["columns"].index(c)], row, r["columns"]) for c in cols))
        for l in lines:
            out.append(f"    [S{l['season']}E{l['episode']} sc.{l['scene']}] {l['speaker']}: {l['text'][:MAX_LINE_CHARS]}")
    return "\n".join(out)
