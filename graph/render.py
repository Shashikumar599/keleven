"""
Render a validated stage 1 extraction as a readable Markdown file.

    python -m graph.render --name S2E18 --title "Take Your Daughter to Work Day"
Reads graph/out/<name>.clean.json and .meta.json, writes docs/samples/<name>.stage1.md.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent


def render(name, title):
    data = json.loads((ROOT / "out" / f"{name}.clean.json").read_text())
    c, issues = data["clean"], data["issues"]
    meta = json.loads((ROOT / "out" / f"{name}.meta.json").read_text())
    who = {x["local_id"]: x["names"][0] if x["names"] else x["local_id"] for x in c["characters"]}
    place = {p["local_id"]: p["name"] for p in c["places"]}
    out = [f"# {name} {title}: stage 1 extraction (sample)", "",
           f"Model {meta['model']}, thinking {meta['thinking']}, prompt {meta['prompt_sha256']}, schema {meta['schema_sha256']}. "
           f"Tokens: {meta['usage']['input']} in, {meta['usage']['output']} out, {meta['latency_ms'] // 1000} s. "
           "Line numbers are ids in the `lines` table. Not hand-corrected: errors are part of the sample.", "",
           "## Summary", "", c["summary"], "", "## Characters (local to this episode)", "",
           "| id | names | here | description |", "|---|---|---|---|"]
    for x in c["characters"]:
        out.append(f"| {x['local_id']} | {', '.join(x['names'])} | {'present' if x['present'] else 'mentioned'} | {x['description']} |")
    out += ["", "## Places", "", "| id | name | kind | description |", "|---|---|---|---|"]
    for p in c["places"]:
        out.append(f"| {p['local_id']} | {p['name']} | {p['kind']} | {p['description']} |")
    out += ["", "## Events", "", "| id | kind | importance | certainty | place | who (role) | lines | text |", "|---|---|---|---|---|---|---|---|"]
    for e in c["events"]:
        ppl = "; ".join(f"{who.get(p['character'], p['character'])} ({p['role']})" for p in e["participants"])
        out.append(f"| {e['id']} | {e['kind']} | {e['importance']} | {e['certainty']} | {place.get(e.get('place'), '-')} | {ppl} | "
                   f"{', '.join(map(str, e['lines']))} | {e['text']}" + (f" ⚑ {', '.join(e['flags'])}" if e["flags"] else "") + " |")
    out += ["", "## Relations", "", "| a | b | type | change | certainty | lines | quote |", "|---|---|---|---|---|---|---|"]
    for r in c["relations"]:
        out.append(f"| {who.get(r['a'], r['a'])} | {who.get(r['b'], r['b'])} | {r['type']} | {r['change']} | {r['certainty']} | "
                   f"{', '.join(map(str, r['lines']))} | {r.get('quote') or ''}" + (f" ⚑ {', '.join(r['flags'])}" if r["flags"] else "") + " |")
    out += ["", "## Points back to earlier events", ""]
    out += [f"- \"{x['text']}\" (lines {', '.join(map(str, x['lines']))})" for x in c["refers_back"]] or ["- none"]
    out += ["", "## Validator", ""]
    out += [f"- {i['severity']} · {i['section']} · {i['rule']} · {i['detail']}" for i in issues] or ["- no issues"]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    dest = ROOT.parent / "docs" / "samples" / f"{a.name}.stage1.md"
    dest.write_text(render(a.name, a.title))
    print("wrote", dest)
