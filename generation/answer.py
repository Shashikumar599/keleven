"""
Three ways to answer a question (Phase 1, Part 5):

    rag     only the retrieved transcript evidence (strict)        prompts/rag_v<N>.md
    llm     only the model's own knowledge, no passages            prompts/memory_v1.md
    hybrid  evidence + own knowledge, every claim labelled         prompts/hybrid_v<N>.md

Prompt files depend on the pipeline version (PROMPT_FILES).

All three use the same model and settings; only the information they get differs. Evidence comes before the
answer in the output structure, so the model collects quotes first and writes the answer from them.

For rag and hybrid, the evidence and inline citations are checked against what was actually sent: a citation to a
scene that wasn't sent, or a "quote" that isn't in the passages, is reported.
"""
import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, Field

from generation.llm import get_llm
from retrieval import CURRENT_VERSION, retrieve, version_of

PROMPTS = Path(__file__).parent / "prompts"
# Prompt files per pipeline version. Files are never edited once a version has been evaluated: a change makes a
# new file. v2 = v1 + how the evidence was found (search text, SQL result block, [SQL] citations); memory unchanged.
PROMPT_FILES = {
    "v1": {"rag": "rag_v1.md", "llm": "memory_v1.md", "hybrid": "hybrid_v1.md"},
    "v2": {"rag": "rag_v2.md", "llm": "memory_v1.md", "hybrid": "hybrid_v2.md"},
}
CITATION = re.compile(r"\[S(\d+)E(\d+) ((?:sc\.\d+(?:,\s*)?)+)\]")   # [S2E1 sc.41] or [S2E1 sc.45, sc.46]


# ---------- output structures (field order = the order the model writes them) ----------

class Evidence(BaseModel):
    quote: str = Field(description="Short exact quote copied from a passage (one line or less)")
    season: int
    episode: int
    scene: int


class RagAnswer(BaseModel):
    evidence: list[Evidence]
    answerable: bool = Field(description="Whether the passages contain the answer")
    answer: str = Field(description="The answer, citing claims inline as [S2E1 sc.41]")


class MemoryAnswer(BaseModel):
    answer: str
    uncertain: list[str] = Field(description="Details you are unsure about")
    knows_answer: bool


class HybridAnswer(BaseModel):
    evidence: list[Evidence]
    answer: str = Field(description="Passage claims cited as [S2E1 sc.41]; own-knowledge claims marked [memory]")
    memory_claims: list[str] = Field(description="Every claim that comes from your own knowledge")
    conflicts: list[str] = Field(description="Where the passages and your own knowledge disagree")


SCHEMAS = {"rag": RagAnswer, "llm": MemoryAnswer, "hybrid": HybridAnswer}


# ---------- building the prompt ----------

def prompt_file(system, version):
    return PROMPT_FILES[version][system]


def load_prompt(system, version):
    return (PROMPTS / prompt_file(system, version)).read_text()


def prompt_sha256(system, version):
    """Hash of the prompt file, logged with each answer so an edited prompt is noticed."""
    return hashlib.sha256((PROMPTS / prompt_file(system, version)).read_bytes()).hexdigest()


def format_passages(retrieval):
    """Passages best first, one header each; per-chunk headers dropped, `Scene N` blocks kept."""
    parts = []
    for i, p in enumerate(retrieval.passages, start=1):
        a, b = p.scenes
        body = "\n\n".join(c.content.split("\n\n", 1)[1] for c in p.chunks)
        parts.append(f"[P{i}] S{p.season}E{p.episode} {p.title}, scenes {a}-{b}\n{body}")
    return "\n\n".join(parts)


def format_sql(plan):
    """The v2 SQL evidence block, or None when no SQL ran. Rows come from all transcript lines, not a sample."""
    r = (plan or {}).get("sql_result")
    if not r:
        return None
    head = f"SQL result, computed over all transcript lines in the dataset:\nQuery: {plan['sql']}"
    if plan.get("assumptions"):
        head += f"\nHow the question was read: {plan['assumptions']}"
    if r["error"]:
        return f"{head}\nThe query failed ({r['error']}); there is no SQL result."
    n = len(r["rows"])
    note = f"{n} row{'' if n == 1 else 's'}" + (f", cut at {n}: more rows exist" if r["truncated"] else "")
    table = "\n".join([" | ".join(r["columns"])] + [" | ".join(str(v) for v in row) for row in r["rows"]])
    return f"{head}\nRows ({note}):\n{table}"


def build_prompt(question, retrieval=None):
    if retrieval is None:
        return f"Question: {question}"
    searched = (retrieval.plan or {}).get("search_text")
    head = f"The transcripts were searched for: {searched}\n\n" if searched else ""
    parts = [f"{head}Transcript passages, most relevant first:\n\n{format_passages(retrieval)}"]
    sql = format_sql(retrieval.plan)
    if sql:
        parts.append(sql)
    return "\n\n".join(parts) + f"\n\nQuestion: {question}"


# ---------- checking citations ----------

def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_citations(text):
    """All (season, episode, scene) cited inline in an answer."""
    found = set()
    for season, episode, scenes in CITATION.findall(text):
        for scene in re.findall(r"\d+", scenes):
            found.add((int(season), int(episode), int(scene)))
    return found


def check_citations(data, retrieval):
    """Compare the model's evidence and inline citations with what was actually sent."""
    sent_scenes, sent_text = set(), {}
    for p in retrieval.passages:
        a, b = p.scenes
        sent_scenes |= {(p.season, p.episode, s) for s in range(a, b + 1)}
        sent_text[(p.season, p.episode)] = sent_text.get((p.season, p.episode), "") + " " + \
            _norm(" ".join(c.content for c in p.chunks))

    bad_evidence = []
    for e in data.get("evidence", []):
        where = (e["season"], e["episode"], e["scene"])
        problems = []
        if where not in sent_scenes:
            problems.append("scene not sent")
        if _norm(e["quote"]) not in sent_text.get((e["season"], e["episode"]), ""):
            problems.append("quote not found in passages")
        if problems:
            bad_evidence.append({**e, "problems": problems})

    inline = parse_citations(data.get("answer", ""))
    return {
        "evidence": len(data.get("evidence", [])),
        "bad_evidence": bad_evidence,
        "inline_citations": len(inline),
        "inline_not_sent": sorted(inline - sent_scenes),
    }


# ---------- answering ----------

def answer(question, system, retrieval=None, llm=None, version=None):
    """Answer one question with one system. rag/hybrid need a retrieval result. The prompt files are those of the
    pipeline version (by default the version the retrieval belongs to)."""
    llm = llm or get_llm()
    version = version or (version_of(retrieval) if retrieval else CURRENT_VERSION)
    needs_passages = system in ("rag", "hybrid")
    if needs_passages and retrieval is None:
        raise ValueError(f"{system} needs a retrieval result")
    result = llm.generate(system=load_prompt(system, version),
                          prompt=build_prompt(question, retrieval if needs_passages else None),
                          schema=SCHEMAS[system])
    return {
        "system": system,
        "prompt": prompt_file(system, version),
        "prompt_sha256": prompt_sha256(system, version),
        "data": result.data,
        "raw": result.text if result.data is None else None,
        "check": check_citations(result.data, retrieval) if needs_passages and result.data else None,
        "llm": {"provider": result.provider, "model": result.model, "model_version": result.model_version,
                "usage": result.usage, "latency_ms": result.latency_ms, "attempts": result.attempts},
    }


def answer_all(question, k=8, expand=1, systems=("rag", "llm", "hybrid"), version=CURRENT_VERSION):
    """Retrieve once, then answer with each system. Returns (retrieval, {system: result})."""
    retrieval = retrieve(question, version=version, k=k, expand=expand)
    llm = get_llm()
    return retrieval, {s: answer(question, s, retrieval, llm) for s in systems}
