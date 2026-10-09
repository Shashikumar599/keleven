"""
Validate one episode's stage 1 extraction (see generation/prompts/extract_v1.md) against the episode's real lines.

Lenient on purpose: a bad detail removes or flags that detail, never the whole episode. No LLM calls, no retries.
  hard (the row or reference is dropped): a cited line id that is not in this episode, a local id that is not defined,
        a relation between a person and themselves, a value outside its list
  flag (kept, marked): a quote not found in the cited lines, a name that is not in the episode, a participant not in the
        cited lines, an over-long event, too many events, near-duplicate events, ...
Episode status: failed (not JSON / not an object / every list empty), flagged (any flag or hard issue; 'info' items such as
participant_not_in_lines do not count), ok.

    python -m graph.validate --file out.json --season 7 --episode 14
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

KINDS = {"romance", "job", "conflict", "prank", "milestone", "family", "other"}
ROLES = {"agent", "patient", "subject", "witness"}
CERTAINTY = {"stated", "implied", "joke_or_false"}
IMPORTANCE = {"major", "minor"}
PLACE_KINDS = {"workplace", "home", "public", "organization", "other"}
REL_TYPES = {"crush", "dating", "engaged", "married", "family", "boss", "rival", "friend"}
REL_CHANGES = {"begins", "ends", "revealed"}


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def load_episode(season, episode):
    from common.db import connect
    with connect("app") as conn:
        rows = conn.execute("SELECT id, scene, speaker, text FROM lines WHERE season=%s AND episode=%s ORDER BY id",
                            (season, episode)).fetchall()
    return {r[0]: {"scene": r[1], "speaker": r[2], "text": r[3]} for r in rows}


class Report:
    def __init__(self):
        self.issues = []          # (severity, section, index, rule, detail)
        self.counts = Counter()   # (section, outcome)

    def add(self, severity, section, i, rule, detail=""):
        self.issues.append({"severity": severity, "section": section, "index": i, "rule": rule, "detail": detail})

    def outcome(self, section, what):
        self.counts[(section, what)] += 1


def _lines(row, lines, rep, section, i):
    """Keep only line ids that exist in this episode; return the clean list."""
    good, bad = [], []
    for x in row.get("lines") or []:
        try:
            x = int(x)
        except (TypeError, ValueError):
            bad.append(x); continue
        (good if x in lines else bad).append(x)
    if bad:
        rep.add("hard", section, i, "line_not_in_episode", f"dropped {bad}")
    return good


def validate(raw, lines):
    """raw: the model's JSON (dict, or a JSON string). lines: {line_id: {scene, speaker, text}}. Returns (clean, report)."""
    rep = Report()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as e:
            rep.add("fatal", "all", None, "not_json", str(e))
            return None, rep
    if not isinstance(raw, dict):
        rep.add("fatal", "all", None, "not_an_object")
        return None, rep

    episode_text = norm(" ".join(l["speaker"] + " " + l["text"] for l in lines.values()))
    clean = {k: [] for k in ("characters", "places", "events", "relations", "refers_back")}
    clean["summary"] = raw.get("summary") or ""

    # characters
    chars = {}
    for i, c in enumerate(raw.get("characters") or []):
        lid = c.get("local_id")
        if not lid or lid in chars:
            rep.add("hard", "characters", i, "bad_or_duplicate_local_id", str(lid)); rep.outcome("characters", "rejected"); continue
        c = {**c, "lines": _lines(c, lines, rep, "characters", i), "flags": []}
        names = [n for n in (c.get("names") or []) if isinstance(n, str)]
        missing = [n for n in names if norm(n) and norm(n) not in episode_text]
        if names and len(missing) == len(names):
            c["flags"].append("name_not_in_episode"); rep.add("flag", "characters", i, "name_not_in_episode", str(names))
        if not names:
            c["flags"].append("no_names"); rep.add("flag", "characters", i, "no_names")
        chars[lid] = c; clean["characters"].append(c)
        rep.outcome("characters", "flagged" if c["flags"] else "accepted")

    # places
    places = {}
    for i, p in enumerate(raw.get("places") or []):
        lid = p.get("local_id")
        if not lid or lid in places:
            rep.add("hard", "places", i, "bad_or_duplicate_local_id", str(lid)); rep.outcome("places", "rejected"); continue
        p = {**p, "lines": _lines(p, lines, rep, "places", i), "flags": []}
        if p.get("kind") not in PLACE_KINDS:
            p["flags"].append("bad_kind"); rep.add("flag", "places", i, "bad_kind", str(p.get("kind"))); p["kind"] = "other"
        places[lid] = p; clean["places"].append(p)
        rep.outcome("places", "flagged" if p["flags"] else "accepted")

    # events
    ev_ids, seen = set(), []
    for i, e in enumerate(raw.get("events") or []):
        eid = e.get("id")
        if not eid or eid in ev_ids or not (e.get("text") or "").strip():
            rep.add("hard", "events", i, "bad_id_or_empty_text", str(eid)); rep.outcome("events", "rejected"); continue
        ev = {**e, "lines": _lines(e, lines, rep, "events", i), "flags": []}
        if not ev["lines"]:
            rep.add("hard", "events", i, "no_valid_lines", str(eid)); rep.outcome("events", "rejected"); continue
        for k, allowed, default in (("kind", KINDS, "other"), ("certainty", CERTAINTY, "implied"), ("importance", IMPORTANCE, "minor")):
            if ev.get(k) not in allowed:
                ev["flags"].append(f"bad_{k}"); rep.add("flag", "events", i, f"bad_{k}", str(ev.get(k))); ev[k] = default
        if ev.get("place") and ev["place"] not in places:
            ev["flags"].append("unknown_place"); rep.add("flag", "events", i, "unknown_place", str(ev["place"])); ev["place"] = None
        parts = []
        for p in ev.get("participants") or []:
            if p.get("character") not in chars:
                rep.add("hard", "events", i, "participant_not_defined", str(p.get("character"))); continue
            if p.get("role") not in ROLES:
                p = {**p, "role": "subject"}; ev["flags"].append("bad_role")
            parts.append(p)
        ev["participants"] = parts
        if not parts:
            ev["flags"].append("no_participants"); rep.add("flag", "events", i, "no_participants", str(eid))
        else:
            cited = norm(" ".join(lines[x]["speaker"] + " " + lines[x]["text"] for x in ev["lines"]))
            for p in parts:
                names = [norm(n) for n in chars[p["character"]].get("names") or []]
                if names and not any(n and n in cited for n in names):
                    ev["flags"].append("participant_not_in_lines"); rep.add("info", "events", i, "participant_not_in_lines", f"{p['character']} in {eid}"); break
        if len((ev["text"]).split()) > 30:
            ev["flags"].append("text_too_long"); rep.add("flag", "events", i, "text_too_long", str(eid))
        key = (frozenset(p["character"] for p in parts), frozenset(ev["lines"]))
        if parts and key in seen:
            ev["flags"].append("near_duplicate"); rep.add("flag", "events", i, "near_duplicate", str(eid))
        seen.append(key)
        ev_ids.add(eid); clean["events"].append(ev)
        rep.outcome("events", "flagged" if ev["flags"] else "accepted")
    if len(clean["events"]) > 35:
        rep.add("flag", "events", None, "too_many_events", str(len(clean["events"])))
    if sum(1 for e in clean["events"] if e.get("importance") == "major") > 8:
        rep.add("flag", "events", None, "too_many_major", "")

    # relations
    for i, r in enumerate(raw.get("relations") or []):
        a, b = r.get("a"), r.get("b")
        if a not in chars or b not in chars:
            rep.add("hard", "relations", i, "end_not_defined", f"{a}, {b}"); rep.outcome("relations", "rejected"); continue
        if a == b:
            rep.add("hard", "relations", i, "same_person", str(a)); rep.outcome("relations", "rejected"); continue
        if r.get("type") not in REL_TYPES or r.get("change") not in REL_CHANGES:
            rep.add("hard", "relations", i, "bad_type_or_change", f"{r.get('type')}/{r.get('change')}"); rep.outcome("relations", "rejected"); continue
        rel = {**r, "lines": _lines(r, lines, rep, "relations", i), "flags": []}
        if not rel["lines"]:
            rep.add("hard", "relations", i, "no_valid_lines", f"{a} {r.get('type')} {b}"); rep.outcome("relations", "rejected"); continue
        if rel.get("certainty") not in CERTAINTY:
            rel["flags"].append("bad_certainty"); rep.add("flag", "relations", i, "bad_certainty", str(rel.get("certainty"))); rel["certainty"] = "implied"
        q = norm(rel.get("quote"))
        cited = norm(" ".join(lines[x]["text"] for x in rel["lines"]))
        if not q:
            rel["flags"].append("no_quote"); rep.add("flag", "relations", i, "no_quote")
        elif q not in cited:
            rel["flags"].append("unverified_quote"); rel["unverified"] = True
            rep.add("flag", "relations", i, "unverified_quote", str(rel.get("quote")))
        clean["relations"].append(rel)
        rep.outcome("relations", "flagged" if rel["flags"] else "accepted")

    # refers_back
    for i, x in enumerate(raw.get("refers_back") or []):
        x = {**x, "lines": _lines(x, lines, rep, "refers_back", i)}
        if x.get("event") and x["event"] not in ev_ids:
            rep.add("flag", "refers_back", i, "unknown_event", str(x["event"])); x["event"] = None
        clean["refers_back"].append(x); rep.outcome("refers_back", "accepted")

    if not any(clean[k] for k in ("characters", "events", "relations")):
        rep.add("fatal", "all", None, "nothing_extracted")
    elif not clean["events"]:
        rep.add("flag", "events", None, "no_events", "")
    if not clean["summary"].strip():
        rep.add("flag", "summary", None, "empty_summary")
    return clean, rep


def status(rep):
    if any(i["severity"] == "fatal" for i in rep.issues):
        return "failed"
    return "flagged" if any(i["severity"] in ("flag", "hard") for i in rep.issues) else "ok"


def print_report(clean, rep):
    print(f"status: {status(rep)}")
    for sec in ("characters", "places", "events", "relations", "refers_back"):
        c = {o: rep.counts[(sec, o)] for o in ("accepted", "flagged", "rejected") if rep.counts[(sec, o)]}
        print(f"  {sec:12} {c or '-'}")
    by = Counter((i["severity"], i["rule"]) for i in rep.issues)
    for (sev, rule), n in sorted(by.items()):
        print(f"  {sev:5} {rule}: {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--out", help="write the clean JSON and the issues here")
    a = ap.parse_args()
    clean, rep = validate(Path(a.file).read_text(), load_episode(a.season, a.episode))
    print_report(clean, rep)
    for i in rep.issues:
        print(" ", i)
    if a.out and clean is not None:
        Path(a.out).write_text(json.dumps({"clean": clean, "issues": rep.issues}, indent=1, ensure_ascii=False))
