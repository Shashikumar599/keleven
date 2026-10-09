"""
Review pass (see generation/prompts/review_v1.md): a second call checks a validated stage 1 extraction against the episode
text and returns corrections only (edit / set / drop on items by id). Code applies them, validates again and keeps both
versions. Nothing is written to the database.

    python -m graph.review --season 2 --episode 18             # dry run
    python -m graph.review --season 2 --episode 18 --run       # one Gemini call (LLM)

Reads graph/out/S2E18.clean.json; writes S2E18.review.json (corrections, what was applied, tokens) and
S2E18.reviewed.json (the corrected extraction plus the validator's issues).
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from generation.llm import DEFAULT_MODEL, get_llm
from graph.extract_one import build_prompt
from graph.validate import load_episode, print_report, validate

ROOT = Path(__file__).parent
PROMPT = ROOT.parent / "generation" / "prompts" / "review_v1.md"
SCHEMA = ROOT / "review_schema.json"
OUT = ROOT / "out"
SECTION_KEY = {"characters": "local_id", "places": "local_id", "events": "id", "relations": "rid"}
TEXT_FIELDS = {"characters": {"description"}, "places": {"description", "kind"},
               "events": {"text", "certainty", "place", "importance", "kind"}, "relations": {"certainty", "detail"}}


def with_rids(clean):
    c = copy.deepcopy(clean)
    for i, r in enumerate(c["relations"], 1):
        r["rid"] = f"r{i}"
    for sec in ("characters", "places", "events", "relations"):
        for item in c[sec]:
            item.pop("flags", None)
            item.pop("unverified", None)
    return c


STOP = set("""a an the and or but if then than so as at by for from in into of on onto to with without about after before while
during over under up down out off again also is are was were be been being am do does did done has have had having it its
this that these those he him his she her hers they them their theirs we us our you your i me my who whom whose which what
when where why how not no yes can could will would should may might must just very more most some any each every both all
other another same such own only too there here one two three first second new back away get gets got going goes went make
makes made take takes took see sees saw say says said tell tells told ask asks asked""".split())


def _stem(w):
    w = w.lower().replace("'s", "")
    for suf in ("ing", "ed", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def _words(t):
    import re
    return [_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", t or "")]


def hint_words(shown, lines):
    """Per item: the words of its own text that occur nowhere in the episode text (stemmed, common words dropped).
    Only pointers for the reviewer, who decides."""
    vocab = set(_words(" ".join(l["speaker"] + " " + l["text"] for l in lines.values())))

    def seen(w):
        return w in vocab or any(len(w) >= 4 and (v.startswith(w) or w.startswith(v)) and len(v) >= 4 for v in vocab)

    def unseen(text):
        return sorted({w for w in _words(text) if w not in STOP and len(w) > 2 and not seen(w)})
    hints = {}
    for c in shown["characters"]:
        hints[c["local_id"]] = unseen(c["description"])
    for p in shown["places"]:
        hints[p["local_id"]] = unseen(p["name"] + " " + p["description"])
    for e in shown["events"]:
        hints[e["id"]] = unseen(e["text"])
    for r in shown["relations"]:
        hints[r["rid"]] = unseen(r.get("detail") or "")
    return {k: v for k, v in hints.items() if v}


def evidence_block(shown, lines):
    """For every item, the text of the lines it cites, so each claim can be checked against its own evidence."""
    out = []
    for sec, key in (("characters", "local_id"), ("places", "local_id"), ("events", "id"), ("relations", "rid")):
        for item in shown[sec]:
            cited = [x for x in item.get("lines") or [] if x in lines]
            if cited:
                out.append(f"{item[key]}:")
                out += [f"  [L{x}] {lines[x]['speaker']}: {lines[x]['text'][:220]}" for x in cited]
    return "\n".join(out)


def apply_corrections(c, corrections, allowed_words=None):
    """Apply to a copy of c. Returns (new, log) where log has one entry per correction: applied / skipped (and why)."""
    new, log = copy.deepcopy(c), []
    for corr in corrections:
        parts = (corr.get("target") or "").split(".")
        entry = {"target": corr.get("target"), "action": corr.get("action"), "problem": corr.get("problem"), "status": "skipped"}
        log.append(entry)
        if len(parts) < 2 or parts[0] not in SECTION_KEY:
            entry["why"] = "unknown target"; continue
        sec, ident = parts[0], parts[1]
        key = SECTION_KEY[sec]
        item = next((x for x in new[sec] if x.get(key) == ident), None)
        if item is None:
            entry["why"] = "no such item"; continue
        act, val = corr.get("action"), corr.get("new_value")
        try:
            if act == "drop" and len(parts) == 2:
                entry["old"] = json.dumps({k: item[k] for k in item if k in ("text", "description", "names", "name", "type")}, ensure_ascii=False)
                new[sec].remove(item)
            elif act == "drop" and sec == "events" and len(parts) == 4 and parts[2] == "participants":
                before = len(item["participants"])
                item["participants"] = [p for p in item["participants"] if p.get("character") != parts[3]]
                if len(item["participants"]) == before:
                    entry["why"] = "no such participant"; continue
            elif act in ("edit", "set") and len(parts) == 3 and parts[2] in TEXT_FIELDS[sec]:
                entry["old"] = item.get(parts[2])
                if act == "edit" and allowed_words is not None and isinstance(val, str):
                    # an edit may only delete or reorder: every word of the new text must already be in the old text or in the episode
                    added = sorted({w for w in _words(val) if w not in STOP and len(w) > 2} - set(_words(entry["old"])) - allowed_words)
                    if added:
                        # repair: take the added words out again (and a leading who / that left behind), so the edit only deletes
                        import re
                        kept = [w for w in re.findall(r"\S+", val) if not (set(_words(w)) & set(added))]
                        while kept and kept[0].lower() in ("who", "that", "which", "and"):
                            kept = kept[1:]
                        if not kept:
                            entry["why"] = f"edit adds words that are in neither the old text nor the episode: {added}"; continue
                        val = " ".join(kept)
                        val = val[0].upper() + val[1:]
                        entry["repaired"] = f"removed added words {added}"
                item[parts[2]] = val if val is not None or parts[2] == "place" else item.get(parts[2])
            else:
                entry["why"] = "action or field not allowed"; continue
        except Exception as e:                      # a malformed correction never stops the rest
            entry["why"] = f"error: {e}"; continue
        entry["new"] = val
        entry["status"] = "applied"
    return new, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    name = f"S{a.season}E{a.episode}"
    from common.db import connect
    with connect("app") as conn:
        row = conn.execute("SELECT title FROM episodes WHERE season=%s AND episode=%s", (a.season, a.episode)).fetchone()
    lines = load_episode(a.season, a.episode)
    stage1 = json.loads((OUT / f"{name}.clean.json").read_text())["clean"]
    shown = with_rids(stage1)
    system = PROMPT.read_text()
    hints = hint_words(shown, lines)
    prompt = (build_prompt(a.season, a.episode, lines, row[0] if row else None) + "\n\nEXTRACTION\n" + json.dumps(shown, ensure_ascii=False)
              + "\n\nEVIDENCE (the lines each item cites)\n" + evidence_block(shown, lines)
              + "\n\nHINTS (words in an item that occur nowhere in the episode text)\n"
              + "\n".join(f"{k}: {', '.join(v)}" for k, v in hints.items()))
    schema = json.loads(SCHEMA.read_text())
    from google.genai import types
    types.Schema.model_validate(schema)
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    print(f"{name}: system ~{len(enc.encode(system))} tokens, message ~{len(enc.encode(prompt))} tokens, model {DEFAULT_MODEL}")
    print(f"hint words: {sum(len(v) for v in hints.values())} in {len(hints)} items")
    if not a.run:
        print("\n".join(f"  {k}: {', '.join(v)}" for k, v in hints.items()))
        print("dry run: nothing sent"); return

    res = get_llm().generate(system=system, prompt=prompt, schema=schema, max_output_tokens=32768, thinking_level="low")
    out = json.loads(res.text)
    corrections = out.get("corrections", [])
    all_ids = ({c["local_id"] for c in shown["characters"]} | {p["local_id"] for p in shown["places"]}
               | {e["id"] for e in shown["events"]} | {r["rid"] for r in shown["relations"]})
    missed = sorted(all_ids - set(out.get("checked", [])))
    print(f"checked {len(set(out.get('checked', [])) & all_ids)} of {len(all_ids)} items; not mentioned: {missed or 'none'}")
    vocab = set(_words(" ".join(l["speaker"] + " " + l["text"] for l in lines.values())))
    new, log = apply_corrections(shown, corrections, vocab)
    clean, rep = validate(new, lines)
    meta = {"model": res.model_version, "usage": res.usage, "latency_ms": res.latency_ms,
            "prompt_sha256": hashlib.sha256(system.encode()).hexdigest()[:8]}
    (OUT / f"{name}.review.json").write_text(json.dumps({"meta": meta, "checked": out.get("checked", []), "not_checked": missed, "hints": hints, "corrections": corrections, "log": log}, indent=1, ensure_ascii=False))
    (OUT / f"{name}.reviewed.json").write_text(json.dumps({"clean": clean, "issues": rep.issues}, indent=1, ensure_ascii=False))
    print(f"tokens {res.usage}, {res.latency_ms // 1000} s; {len(corrections)} corrections, "
          f"{sum(1 for e in log if e['status'] == 'applied')} applied")
    for e in log:
        print(f"- [{e['status']}] {e['action']} {e['target']}: {e['problem']}")
        if e.get("old") is not None:
            print(f"    was: {e['old']}")
        if e["status"] == "applied" and e["action"] != "drop":
            print(f"    now: {e['new']}")
        if e.get("why"):
            print(f"    ({e['why']})")
    print_report(clean, rep)


if __name__ == "__main__":
    main()
