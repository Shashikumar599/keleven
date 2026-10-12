"""
Controls for a public deployment (PUBLIC_MODE=1). Off by default: the local app is unchanged.

A public page is open to anyone and every question costs model calls, so a visitor (anyone without the admin password) gets:
- rate limits: PUBLIC_RATE_PER_MIN and PUBLIC_RATE_PER_DAY questions per IP (in memory, per server instance) and a hard
  PUBLIC_DAILY_CAP of web questions per day across everyone (counted in the database, so it holds across instances);
- the default retrieval settings (k, neighbours); the version and the answers to compute are free to choose;
- excerpts instead of passages: a few short lines per scene, because the transcripts are copyrighted and must not be served whole;
- no access to other people's questions (history and stored comparisons need the admin password).
The admin password lifts all of these.
"""
import os
import threading
import time
from collections import defaultdict, deque

from common.db import connect

LINES_PER_SCENE = 3
LINE_CHARS = 160


def enabled():
    return os.environ.get("PUBLIC_MODE") == "1"


def _limit(name, default):
    return int(os.environ.get(name, default))


class _Windows:
    """Per-IP sliding windows of question times, kept in memory."""

    def __init__(self):
        self.times = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, ip, per_minute, per_day, now=None):
        """(allowed, seconds to wait). Records the question only when it is allowed."""
        now = time.time() if now is None else now
        with self.lock:
            q = self.times[ip]
            while q and now - q[0] > 86400:
                q.popleft()
            recent = [t for t in q if now - t <= 60]
            if len(q) >= per_day:
                return False, int(86400 - (now - q[0])) + 1
            if len(recent) >= per_minute:
                return False, int(60 - (now - recent[0])) + 1
            q.append(now)
            return True, 0


_windows = _Windows()


def client_ip(request):
    """The visitor's address; behind the hosting proxy it is the first entry of X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


def check_rate(ip):
    return _windows.hit(ip, _limit("PUBLIC_RATE_PER_MIN", 4), _limit("PUBLIC_RATE_PER_DAY", 40))


def daily_total():
    """Web questions asked so far today (UTC)."""
    with connect("app") as conn:
        return conn.execute("SELECT count(*) FROM qa_runs WHERE source = 'web' "
                            "AND asked_at >= date_trunc('day', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc'").fetchone()[0]


def daily_cap_reached():
    return daily_total() >= _limit("PUBLIC_DAILY_CAP", 300)


def _cut(text):
    return text if len(text) <= LINE_CHARS else text[:LINE_CHARS].rstrip() + "…"


def excerpt_content(content):
    """A chunk's text with only the first few lines of each scene, each line shortened. The first block (the chunk header)
    and the 'Scene N' markers are kept, so the page can still lay it out."""
    blocks = content.split("\n\n")
    out = [blocks[0]]
    for block in blocks[1:]:
        head, *lines = block.split("\n")
        out.append("\n".join([head] + [_cut(l) for l in lines[:LINES_PER_SCENE]]))
    return "\n\n".join(out)


def _cut_cells(rows):
    return [[_cut(v) if isinstance(v, str) else v for v in row] for row in rows]


def trim(response):
    """The /api/ask response as a visitor may see it: everything the page shows in dev mode, but transcript text only as
    excerpts (passages, search hits, SQL and graph rows, graph lines)."""
    r = response["retrieval"]
    for h in r["hits"]:
        h["content"] = excerpt_content(h["content"])
    for p in r["passages"]:
        for c in p["chunks"]:
            c["content"] = excerpt_content(c["content"])
    plan = r.get("plan")
    if plan:
        for key in ("sql_result", "graph_result"):
            res = plan.get(key)
            if res and res.get("rows"):
                res["rows"] = _cut_cells(res["rows"])
        graph = plan.get("graph_result")
        if graph and graph.get("lines"):
            per_scene = defaultdict(int)
            lines = []
            for row in graph["lines"]:                      # the transcript lines the graph rows came from
                kept = []
                for l in row:
                    key = (l["season"], l["episode"], l["scene"])
                    if per_scene[key] < LINES_PER_SCENE:
                        per_scene[key] += 1
                        kept.append({**l, "text": _cut(l["text"])})
                lines.append(kept)
            graph["lines"] = lines
    return response
