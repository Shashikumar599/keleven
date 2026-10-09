"""
Extract ONE episode (stage 1, see generation/prompts/extract_v1.md) and validate it. Nothing is written to the database.

    python -m graph.extract_one --season 7 --episode 14            # dry run: show what would be sent, call nothing
    python -m graph.extract_one --season 7 --episode 14 --run      # one Gemini call (LLM), then validate

Writes graph/out/S7E14.raw.json (what the model returned), .clean.json (after validation) and .meta.json (model,
prompt hash, tokens). graph/out/ is derived data and is not committed.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import tiktoken

from graph.validate import load_episode, print_report, validate
from generation.llm import DEFAULT_MODEL, get_llm

ROOT = Path(__file__).parent
PROMPT = ROOT.parent / "generation" / "prompts" / "extract_v1.md"
SCHEMA = ROOT / "stage1_schema.json"
OUT = ROOT / "out"
THINKING = "low"
MAX_OUTPUT = 32768


def build_prompt(season, episode, lines, title):
    labels = Counter(l["speaker"] for l in lines.values())
    parts = [f"Episode: S{season}E{episode}" + (f' "{title}"' if title else ""),
             "Speaker labels in this episode (number of lines): " + ", ".join(f"{k} ({v})" for k, v in labels.most_common()),
             "", "EPISODE TEXT"]
    scene = None
    for lid, l in lines.items():
        if l["scene"] != scene:
            scene = l["scene"]
            parts += ["", f"Scene {scene}"]
        parts.append(f"[L{lid}] {l['speaker']}: {l['text']}")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--run", action="store_true", help="make the Gemini call (default: dry run)")
    a = ap.parse_args()

    from common.db import connect
    with connect("app") as conn:
        row = conn.execute("SELECT title FROM episodes WHERE season=%s AND episode=%s", (a.season, a.episode)).fetchone()
    lines = load_episode(a.season, a.episode)
    system = PROMPT.read_text()
    prompt = build_prompt(a.season, a.episode, lines, row[0] if row else None)
    schema = json.loads(SCHEMA.read_text())

    from google.genai import types
    types.Schema.model_validate(schema)        # the SDK accepts this schema (offline check)

    enc = tiktoken.get_encoding("cl100k_base")
    print(f"S{a.season}E{a.episode}: {len(lines)} lines, system prompt ~{len(enc.encode(system))} tokens, "
          f"episode message ~{len(enc.encode(prompt))} tokens (cl100k estimate), model {DEFAULT_MODEL}, "
          f"thinking {THINKING}, max output {MAX_OUTPUT}")
    if not a.run:
        print("dry run: nothing sent. First lines of the message:\n")
        print("\n".join(prompt.splitlines()[:12]))
        return

    result = get_llm().generate(system=system, prompt=prompt, schema=schema, max_output_tokens=MAX_OUTPUT,
                                thinking_level=THINKING)
    name = f"S{a.season}E{a.episode}"
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.raw.json").write_text(result.text)
    meta = {"model": result.model, "model_version": result.model_version, "usage": result.usage,
            "latency_ms": result.latency_ms, "attempts": result.attempts, "thinking": THINKING,
            "prompt_sha256": hashlib.sha256(system.encode()).hexdigest()[:8],
            "schema_sha256": hashlib.sha256(SCHEMA.read_bytes()).hexdigest()[:8]}
    (OUT / f"{name}.meta.json").write_text(json.dumps(meta, indent=1))
    print("model returned:", meta)
    clean, rep = validate(result.text, lines)
    print_report(clean, rep)
    if clean is not None:
        (OUT / f"{name}.clean.json").write_text(json.dumps({"clean": clean, "issues": rep.issues}, indent=1, ensure_ascii=False))
    print(f"saved to graph/out/{name}.*")


if __name__ == "__main__":
    main()
