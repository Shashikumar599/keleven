"""
Logging questions and answers to Postgres (tables from db/migrations/006_logging.sql).

    log_run(retrieval, answers, source, mode)   one question: the run + one row per answer, in one transaction
    log_feedback(run_id, kind, ...)             optional feedback from the web page (insert or update)
    log_review(run_id, system, reviewer, ...)   a review by the owner ("me") or the Claude skill (insert or update)

Prompts aren't stored: they are rebuilt from the pipeline version, the chunk ids sent (`sent_chunk_ids`, in prompt
order) and the prompt file (its hash is logged per answer).

Connects as the app role. office_app sessions are read-only by default, so every write opens an explicit READ WRITE
transaction; its grants allow writing to the log tables only. A logging failure never breaks answering: it is
reported and the function returns None.
"""
import json

from common.db import connect
from retrieval import version_of



def _write(fn):
    """Run fn(conn) in one READ WRITE transaction as the app role. Returns its result, or None on failure."""
    try:
        with connect("app") as conn:
            conn.read_only = False                  # BEGIN READ WRITE instead of the role's read-only default
            return fn(conn)
    except Exception as e:                          # logging must never break answering
        print(f"  logging failed: {type(e).__name__}: {e}")
        return None


def log_run(retrieval, answers, source, mode="dev", version=None, question_id=None, eval_label=None):
    """Log one question with its retrieval and answers. `answers` is {system: result from generation.answer}.
    The pipeline version defaults to the one matching the retrieval method. Returns the new run_id."""
    version = version or version_of(retrieval)
    hits = [{"rank": h.rank, "chunk_id": h.chunk.chunk_id,
             "distance": round(h.distance, 6) if h.distance is not None else None, **h.scores}
            for h in retrieval.hits]
    sent = [c.chunk_id for p in retrieval.passages for c in p.chunks]

    def write(conn):
        run_id = conn.execute("""
            INSERT INTO qa_runs (source, mode, eval_label, question_id, question, version,
                                 chunk_set_id, model_id, k, expand, hits, sent_chunk_ids, query_tokens, retrieval_ms,
                                 plan)
            VALUES (%s, %s, %s, %s, %s, %s,
                    (SELECT chunk_set_id FROM chunk_sets WHERE name = %s),
                    (SELECT model_id FROM embedding_models WHERE name = %s),
                    %s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
        """, (source, mode, eval_label, question_id, retrieval.question, version,
              retrieval.chunk_set, retrieval.model, retrieval.k, retrieval.expand,
              json.dumps(hits), sent, retrieval.query_tokens, json.dumps(retrieval.timings_ms),
              json.dumps(retrieval.plan) if retrieval.plan else None)).fetchone()[0]

        for system, a in answers.items():
            llm = a.get("llm") or {}
            conn.execute("""
                INSERT INTO qa_answers (run_id, system, prompt_file, prompt_sha256, provider, model, model_version,
                                        output, raw_text, error, citation_check, usage, latency_ms, attempts,
                                        reused_from_run)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (run_id, system, a.get("prompt", ""), a.get("prompt_sha256", ""),
                  llm.get("provider"), llm.get("model"), llm.get("model_version"),
                  json.dumps(a["data"]) if a.get("data") is not None else None,
                  a.get("raw"), a.get("error"),
                  json.dumps(a["check"]) if a.get("check") else None,
                  json.dumps(llm["usage"]) if llm.get("usage") else None,
                  llm.get("latency_ms"), llm.get("attempts"), a.get("reused_from_run")))
        return run_id

    return _write(write)


def replace_answer(run_id, system, a):
    """Overwrite one logged answer (e.g. an eval answer re-run after a failure). `a` is a result from
    generation.answer."""
    llm = a.get("llm") or {}

    def write(conn):
        conn.execute("""
            UPDATE qa_answers
               SET prompt_file = %s, prompt_sha256 = %s, provider = %s, model = %s, model_version = %s,
                   output = %s, raw_text = %s, error = %s, citation_check = %s, usage = %s, latency_ms = %s,
                   attempts = %s
             WHERE run_id = %s AND system = %s
        """, (a.get("prompt", ""), a.get("prompt_sha256", ""), llm.get("provider"), llm.get("model"),
              llm.get("model_version"), json.dumps(a["data"]) if a.get("data") is not None else None,
              a.get("raw"), a.get("error"), json.dumps(a["check"]) if a.get("check") else None,
              json.dumps(llm["usage"]) if llm.get("usage") else None, llm.get("latency_ms"), llm.get("attempts"),
              run_id, system))
        return True

    return _write(write)


def log_review(run_id, system, reviewer, verdict, notes=None, grounded=None, failure_type=None, details=None):
    """Record or change a review of one answer (`system`) or of the whole run (`system` None)."""
    def write(conn):
        conn.execute("""
            INSERT INTO qa_reviews (run_id, system, reviewer, verdict, grounded, failure_type, notes, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, system, reviewer) DO UPDATE
               SET verdict = EXCLUDED.verdict, grounded = EXCLUDED.grounded, failure_type = EXCLUDED.failure_type,
                   notes = EXCLUDED.notes, details = EXCLUDED.details, updated_at = now()
        """, (run_id, system, reviewer, verdict, grounded, failure_type, notes,
              json.dumps(details) if details is not None else None))
        return True

    return _write(write)


def log_feedback(run_id, kind, satisfied=None, preferred=None, comment=None):
    """Record or change feedback for a run: kind 'satisfied' (yes/no) or 'preference' (rag/llm/both_good/both_bad)."""
    def write(conn):
        conn.execute("""
            INSERT INTO qa_feedback (run_id, kind, satisfied, preferred, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (run_id, kind) DO UPDATE
               SET satisfied = EXCLUDED.satisfied, preferred = EXCLUDED.preferred,
                   comment = EXCLUDED.comment, updated_at = now()
        """, (run_id, kind, satisfied, preferred, comment))
        return True

    return _write(write)
