"""
Stored answers for a question asked before (dev-mode comparison, memory-answer reuse).

"The same question" = same text after trimming, ignoring case and repeated spaces (index: migration 011).

    stored_memory(question, prompt_file)   the latest good memory-only answer, to reuse instead of an LLM call
    comparable(question)                   the latest good answer of each kind: memory, v1 rag, v1 hybrid, v2 ...
"""
from common.db import connect

NORM = "lower(regexp_replace(btrim({}), '\\s+', ' ', 'g'))"
SYSTEM_LABELS = {"rag": "transcripts only", "hybrid": "transcripts + memory", "llm": "memory only"}


def _answer(row):
    """A stored qa_answers row in the shape generation.answer.answer() returns."""
    (system, prompt_file, prompt_sha, output, raw, error, check, model_version, usage, latency, attempts) = row
    return {"system": system, "prompt": prompt_file, "prompt_sha256": prompt_sha, "data": output, "raw": raw,
            "error": error, "check": check,
            "llm": {"model_version": model_version, "usage": usage or {}, "latency_ms": latency, "attempts": attempts}}


_COLS = """a.system, a.prompt_file, a.prompt_sha256, a.output, a.raw_text, a.error, a.citation_check,
           a.model_version, a.usage, a.latency_ms, a.attempts"""


def stored_memory(question, prompt_file):
    """The latest memory-only answer to this question made with `prompt_file`, without error; None if there is none.
    The returned answer carries `reused_from_run` (the run it was first made in)."""
    with connect("app") as conn:
        row = conn.execute(f"""
            SELECT {_COLS}, coalesce(a.reused_from_run, r.run_id)
            FROM qa_runs r JOIN qa_answers a USING (run_id)
            WHERE {NORM.format('r.question')} = {NORM.format('%s')}
              AND a.system = 'llm' AND a.prompt_file = %s AND a.error IS NULL AND a.output IS NOT NULL
            ORDER BY r.run_id DESC LIMIT 1
        """, (question, prompt_file)).fetchone()
    if not row:
        return None
    return {**_answer(row[:-1]), "reused_from_run": row[-1]}


def comparable(question):
    """[{key, version, system, label, run_id, asked_at, source, answer, sent_scenes}] the latest good answer of each
    kind for this question. Memory is one kind across versions (it doesn't depend on the version)."""
    with connect("app") as conn:
        rows = conn.execute(f"""
            SELECT DISTINCT ON (kind) kind, r.version, r.run_id, r.asked_at, r.source, {_COLS},
                   (SELECT array_agg(DISTINCT c.season || '-' || c.episode || '-' || s)
                    FROM chunks_full c, generate_series(c.scene_start, c.scene_end) s
                    WHERE c.chunk_id = ANY(r.sent_chunk_ids)) AS sent_scenes
            FROM qa_runs r JOIN qa_answers a USING (run_id),
                 LATERAL (SELECT CASE WHEN a.system = 'llm' THEN 'llm' ELSE r.version || ':' || a.system END) k(kind)
            WHERE {NORM.format('r.question')} = {NORM.format('%s')} AND a.error IS NULL AND a.output IS NOT NULL
            ORDER BY kind, r.run_id DESC
        """, (question,)).fetchall()
    out = []
    for kind, version, run_id, asked_at, source, *ans, sent in rows:
        a = _answer(ans)
        system = a["system"]
        label = "Memory only" if system == "llm" else f"{version} · {SYSTEM_LABELS[system]}"
        out.append({"key": kind, "version": version, "system": system, "label": label, "run_id": run_id,
                    "asked_at": asked_at.isoformat(), "source": source, "answer": a, "sent_scenes": sent or []})
    order = {"llm": 0}
    return sorted(out, key=lambda x: (order.get(x["key"], 1), x["key"]))
