"""
Local web app: ask a question, see retrieval and the three answers side by side; browse the history.

Run (from the repo root):
    set -a; source .env; set +a
    .venv/bin/uvicorn app.server:app --port 8000
then open http://localhost:8000

Admin: ADMIN_PASSWORD (.env) unlocks the retrieval settings, writing reviews, and seeing feedback/reviews in the
history. Checked on the server for every request that needs it (header X-Admin-Password).

Local only for now: the page shows full retrieved passages, which the public demo must not (short excerpts only).
"""
import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import gate
from app import public as publicmode
from common.db import connect
from common.qalog import log_feedback, log_review, log_run
from common.stored import comparable, stored_memory
from generation.answer import answer, prompt_file, prompt_sha256
from generation.answer_v3 import PROMPT_FILES_V3, answer_v3, prompt_sha256_v3
from generation.llm import DEFAULT_MODEL as LLM_MODEL, get_llm
from retrieval import retrieve
from retrieval.hybrid import EnhanceError
from retrieval.vector import DEFAULT_CHUNK_SET, DEFAULT_MODEL as EMBEDDING_MODEL

STATIC = Path(__file__).parent / "static"
SYSTEMS = ("rag", "llm", "hybrid")
DEFAULT_K, DEFAULT_EXPAND = 8, 1
APP_DEFAULT_VERSION = "v3"       # what the page asks with unless dev mode picks another; retrieval.CURRENT_VERSION (v2) stays the default of the research tools

app = FastAPI(title="Keleven")
app.middleware("http")(gate.middleware)          # optional site password (SITE_PASSWORD); off when unset
app.mount("/static", StaticFiles(directory=STATIC), name="static")   # audio, images, quotes


# ---------- admin ----------

def is_admin(password):
    """True if `password` matches ADMIN_PASSWORD. Not set = nobody is admin. Constant-time comparison."""
    expected = os.environ.get("ADMIN_PASSWORD", "")
    return bool(expected) and hmac.compare_digest((password or "").encode(), expected.encode())


def require_admin(password):
    if not os.environ.get("ADMIN_PASSWORD"):
        raise HTTPException(403, "No admin password has been set.")
    if not is_admin(password):
        raise HTTPException(403, "Wrong admin password.")


class AdminRequest(BaseModel):
    password: str


@app.post("/api/admin/check")
def admin_check(req: AdminRequest):
    require_admin(req.password)
    return {"admin": True}


# ---------- asking ----------

# Pipeline versions offered in dev mode. Not locked: every version costs the same per question.
VERSIONS = [
    {"version": "v1", "label": "Vector", "ready": True,
     "description": "Finds scenes by meaning only (embedding similarity)."},
    {"version": "v2", "label": "Hybrid", "ready": True,
     "description": "Rewrites the question for search, finds scenes by meaning and by exact words, and can "
                    "query the full transcripts with SQL for counts and lists."},
    {"version": "v3", "label": "Graph", "ready": True,
     "description": "Hybrid plus a graph of relationships and events extracted from every episode, which the "
                    "question can query for lists and histories (who dated whom, what happened to someone)."},
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    version: Literal["v1", "v2", "v3"] = APP_DEFAULT_VERSION
    k: int = Field(default=DEFAULT_K, ge=1, le=20)
    expand: int = Field(default=DEFAULT_EXPAND, ge=0, le=3)
    systems: list[str] = list(SYSTEMS)
    mode: Literal["user", "dev"] = "user"     # display only; `systems` decides which answers are computed (the page asks user mode for two)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.on_event("startup")
def warm_up():
    """Build the keyword index now (about a second) instead of on the first question."""
    try:
        from retrieval.keyword import get_index
        get_index(DEFAULT_CHUNK_SET)
    except Exception as e:                         # the page still starts; the first question builds it
        print(f"  keyword index warm-up skipped: {type(e).__name__}: {e}")


class LoginRequest(BaseModel):
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(req: LoginRequest, request: Request):
    from fastapi.responses import JSONResponse
    if not gate.enabled():
        return {"ok": True}
    gate.throttle(request)
    if not gate.check_password(req.password):
        raise HTTPException(401, "Wrong password.")
    value, max_age = gate.make_cookie()
    response = JSONResponse({"ok": True})
    proto = request.headers.get("cloudfront-forwarded-proto") or request.headers.get("x-forwarded-proto") or request.url.scheme
    secure = proto == "https"
    response.set_cookie(gate.COOKIE, value, max_age=max_age, httponly=True, samesite="lax", secure=secure)
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/ask")
def ask(req: AskRequest, request: Request, x_admin_password: str | None = Header(default=None)):
    unlocked = is_admin(x_admin_password)
    visitor = publicmode.enabled() and not unlocked        # public deployment: limits, defaults, excerpts only
    if visitor:
        allowed, wait = publicmode.check_rate(publicmode.client_ip(request))
        if not allowed:
            raise HTTPException(429, f"Too many questions. Please try again in {wait} seconds.")
        if publicmode.daily_cap_reached():
            raise HTTPException(429, "The demo has reached today's question limit. Please come back tomorrow.")
    k, expand = (req.k, req.expand) if unlocked else (DEFAULT_K, DEFAULT_EXPAND)   # locked: ignore what was sent
    try:
        r = retrieve(req.question, version=req.version, k=k, expand=expand)
    except EnhanceError:                             # v2 can't run without the enhancer: the request fails
        raise HTTPException(502, "Search preparation failed. Please try again.")
    llm = get_llm()
    systems = [s for s in req.systems if s in SYSTEMS]

    v3 = req.version == "v3"                         # v3 has its own answer code and prompt files; v1 and v2 are as before
    file_of = (lambda system: PROMPT_FILES_V3[system]) if v3 else (lambda system: prompt_file(system, req.version))
    sha_of = prompt_sha256_v3 if v3 else (lambda system: prompt_sha256(system, req.version))

    def run(system):
        try:
            return answer_v3(req.question, system, r, llm) if v3 else answer(req.question, system, r, llm)
        except Exception as e:                       # one failing system shouldn't hide the others
            return {"system": system, "prompt": file_of(system), "prompt_sha256": sha_of(system),
                    "error": f"{type(e).__name__}: {e}"}

    # The memory-only answer doesn't depend on the version: reuse a stored one instead of calling the LLM again.
    reused = stored_memory(req.question, file_of("llm")) if "llm" in systems else None
    to_compute = [s for s in systems if not (s == "llm" and reused)]
    with ThreadPoolExecutor(max_workers=len(to_compute) or 1) as pool:   # the answers run in parallel
        answers = dict(zip(to_compute, pool.map(run, to_compute)))
    if reused:
        answers["llm"] = reused

    run_id = log_run(r, answers, source="web", mode=req.mode)     # None if logging failed; answers still returned

    response = {
        "run_id": run_id,
        "settings_locked": not unlocked,
        "question": r.question,
        "retrieval": {
            "chunk_set": r.chunk_set, "model": r.model, "k": r.k, "expand": r.expand, "method": r.method,
            "version": req.version, "plan": r.plan, "timings_ms": r.timings_ms, "query_tokens": r.query_tokens,
            "hits": [{"rank": h.rank, "distance": None if h.distance is None else round(h.distance, 4),
                      "scores": h.scores, **asdict(h.chunk)} for h in r.hits],
            "passages": [{
                "season": p.season, "episode": p.episode, "title": p.title,
                "scene_start": p.scenes[0], "scene_end": p.scenes[1],
                "hit_ranks": sorted(h.rank for h in p.hits),
                "chunks": [{**asdict(c), "is_hit": any(h.chunk.chunk_id == c.chunk_id for h in p.hits)}
                           for c in p.chunks],
            } for p in r.passages],
        },
        "answers": answers,
    }
    return publicmode.trim(response) if visitor else response


# ---------- feedback (anyone) and reviews (admin) ----------

class FeedbackRequest(BaseModel):
    run_id: int
    kind: Literal["satisfied", "preference"]
    satisfied: bool | None = None                     # user mode: was the LLM + RAG answer satisfactory?
    preferred: Literal["rag", "llm"] | None = None    # dev mode: which of the two answers is better


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if (req.kind == "satisfied") != (req.satisfied is not None) or (req.kind == "preference") != (req.preferred is not None):
        raise HTTPException(422, "send 'satisfied' with kind=satisfied, or 'preferred' with kind=preference")
    if not log_feedback(req.run_id, req.kind, satisfied=req.satisfied, preferred=req.preferred):
        raise HTTPException(500, "feedback could not be saved")
    return {"saved": True}


class ReviewRequest(BaseModel):
    run_id: int
    system: Literal["rag", "llm", "hybrid"]
    verdict: Literal["correct", "partial", "wrong", "refused"]
    notes: str | None = Field(default=None, max_length=2000)


@app.post("/api/review")
def review(req: ReviewRequest, x_admin_password: str | None = Header(default=None)):
    require_admin(x_admin_password)
    if not log_review(req.run_id, req.system, "me", req.verdict, notes=req.notes):
        raise HTTPException(500, "review could not be saved")
    return {"saved": True}


# ---------- history (anyone; feedback and reviews only for admin) ----------

def _passages(chunks):
    """Chunks in prompt order -> passages: consecutive positions of one episode merged."""
    passages = []
    for c in chunks:
        p = passages[-1] if passages else None
        if p and (p["season"], p["episode"]) == (c["season"], c["episode"]) and c["position"] == p["chunks"][-1]["position"] + 1:
            p["chunks"].append(c)
            p["scene_end"] = c["scene_end"]
        else:
            passages.append({"season": c["season"], "episode": c["episode"], "title": c["title"],
                             "scene_start": c["scene_start"], "scene_end": c["scene_end"], "chunks": [c]})
    return passages


@app.get("/api/history")
def history(before: int | None = None, x_admin_password: str | None = Header(default=None)):
    """One logged question at a time, newest first: the run before `before` (or the latest)."""
    if publicmode.enabled():                       # other visitors' questions and full passages: admin only
        require_admin(x_admin_password)
    admin = is_admin(x_admin_password)
    with connect("app") as conn:
        run = conn.execute("""
            SELECT run_id, asked_at, source, mode, version, question, k, expand, hits, sent_chunk_ids, plan
            FROM qa_runs WHERE (%s::bigint IS NULL OR run_id < %s)
            ORDER BY run_id DESC LIMIT 1
        """, (before, before)).fetchone()
        if run is None:
            return {"run": None, "has_more": False}
        run_id, asked_at, source, mode, version, question, k, expand, hits, sent, plan = run

        answers = {}
        for system, output, raw, error, check, model_version, usage, latency, attempts, prompt in conn.execute("""
                SELECT system, output, raw_text, error, citation_check, model_version, usage, latency_ms, attempts, prompt_file
                FROM qa_answers WHERE run_id = %s""", (run_id,)):
            answers[system] = {"system": system, "data": output, "raw": raw, "error": error, "check": check,
                               "prompt": prompt, "llm": {"model_version": model_version, "usage": usage or {},
                                                         "latency_ms": latency or 0, "attempts": attempts or 1}}

        rows = conn.execute("""
            SELECT chunk_id, season, episode, title, position, scene_start, scene_end, content
            FROM chunks_full WHERE chunk_id = ANY(%s)""", (sent,)).fetchall()
        by_id = {r[0]: dict(zip(("chunk_id", "season", "episode", "title", "position", "scene_start", "scene_end",
                                 "content"), r)) for r in rows}
        hit_ids = {h["chunk_id"] for h in hits}
        chunks = [{**by_id[cid], "is_hit": cid in hit_ids} for cid in sent if cid in by_id]

        has_more = conn.execute("SELECT EXISTS (SELECT 1 FROM qa_runs WHERE run_id < %s)", (run_id,)).fetchone()[0]

        extra = {}
        if admin:
            extra["feedback"] = [dict(zip(("kind", "satisfied", "preferred"), r)) for r in conn.execute(
                "SELECT kind, satisfied, preferred FROM qa_feedback WHERE run_id = %s", (run_id,))]
            extra["reviews"] = [dict(zip(("system", "reviewer", "verdict", "grounded", "failure_type", "notes"), r))
                                for r in conn.execute("""
                SELECT system, reviewer, verdict, grounded, failure_type, notes
                FROM qa_reviews WHERE run_id = %s ORDER BY reviewer, system""", (run_id,))]

    return {
        "has_more": has_more,
        "run": {"run_id": run_id, "asked_at": asked_at.isoformat(), "source": source, "mode": mode,
                "version": version, "question": question, "k": k, "expand": expand, "plan": plan,
                "passages": _passages(chunks), "answers": answers, **extra},
    }


@app.get("/api/compare")
def compare(question: str, x_admin_password: str | None = Header(default=None)):
    """Dev mode: the latest stored answer of each kind (memory, v1 rag, v1 hybrid, v2 ...) for this exact question."""
    if publicmode.enabled():
        require_admin(x_admin_password)
    return {"question": question, "answers": comparable(question)}


@app.get("/api/info")
def info():
    """What the pipeline is, for the dev-mode explainer (shown before any question is asked)."""
    with connect("app") as conn:
        passages = conn.execute(
            "SELECT count(*) FROM chunks c JOIN chunk_sets s USING (chunk_set_id) WHERE s.name = %s",
            (DEFAULT_CHUNK_SET,)).fetchone()[0]
    return {"llm": LLM_MODEL, "embedding_model": EMBEDDING_MODEL, "chunk_set": DEFAULT_CHUNK_SET,
            "version": APP_DEFAULT_VERSION, "versions": VERSIONS,
            "passages": passages, "default_k": DEFAULT_K, "default_expand": DEFAULT_EXPAND,
            "admin_password_set": bool(os.environ.get("ADMIN_PASSWORD")), "public_mode": publicmode.enabled()}
