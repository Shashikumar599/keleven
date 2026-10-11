"""
Answering for pipeline v3: the v2 answer code plus the graph result block. generation/answer.py (v1 and v2) is only imported.

Prompt files: rag_v3.md, hybrid_v3.md (v2's plus how to read graph rows) and memory_v1.md. The citation check is v2's, then
corrected for the graph: a scene or quote that came with a graph row counts as sent.
"""
import hashlib

from generation.answer import (PROMPTS, SCHEMAS, build_prompt, check_citations, format_sql, parse_citations)
from generation.llm import get_llm
from retrieval import graph as graphrun

PROMPT_FILES_V3 = {"rag": "rag_v3.md", "llm": "memory_v1.md", "hybrid": "hybrid_v3.md"}


def prompt_sha256_v3(system):
    return hashlib.sha256((PROMPTS / PROMPT_FILES_V3[system]).read_bytes()).hexdigest()


def build_prompt_v3(question, retrieval=None):
    """The v2 prompt with the graph block after the SQL block."""
    base = build_prompt(question, retrieval)
    block = graphrun.format_block(retrieval.plan) if retrieval is not None else None
    if not block:
        return base
    tail = f"\n\nQuestion: {question}"
    return base[: -len(tail)] + "\n\n" + block + tail


def check_citations_v3(data, retrieval):
    """v2's check, minus the problems that the graph rows explain (their scenes and quotes were sent too)."""
    check = check_citations(data, retrieval)
    gr = (retrieval.plan or {}).get("graph_result")
    if not gr or gr["error"]:
        return check
    scenes, text = graphrun.scene_refs(gr), graphrun.quote_text(gr)
    kept = []
    for e in check["bad_evidence"]:
        problems = [p for p in e["problems"]
                    if not (p == "scene not sent" and (e["season"], e["episode"], e["scene"]) in scenes)
                    and not (p == "quote not found in passages" and " ".join(e["quote"].split()).lower() in text)]
        if problems:
            kept.append({**e, "problems": problems})
    check["bad_evidence"] = kept
    check["inline_not_sent"] = [s for s in check["inline_not_sent"] if tuple(s) not in scenes]
    return check


def answer_v3(question, system, retrieval=None, llm=None):
    llm = llm or get_llm()
    needs_passages = system in ("rag", "hybrid")
    if needs_passages and retrieval is None:
        raise ValueError(f"{system} needs a retrieval result")
    result = llm.generate(system=(PROMPTS / PROMPT_FILES_V3[system]).read_text(),
                          prompt=build_prompt_v3(question, retrieval if needs_passages else None), schema=SCHEMAS[system])
    return {
        "system": system, "prompt": PROMPT_FILES_V3[system], "prompt_sha256": prompt_sha256_v3(system),
        "data": result.data, "raw": result.text if result.data is None else None,
        "check": check_citations_v3(result.data, retrieval) if needs_passages and result.data else None,
        "llm": {"provider": result.provider, "model": result.model, "model_version": result.model_version,
                "usage": result.usage, "latency_ms": result.latency_ms, "attempts": result.attempts},
    }
