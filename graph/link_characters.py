"""
Stage 2a: link character cards across episodes using only evidence in the data (no LLM, nothing written to the database).

A card is one character in one episode (from the reviewed extraction). Cards are grouped by their primary name (first name on the
card). Two groups are merged only when ALL of these hold:
  - strong evidence: cards of one list the other's primary name as an alias, on at least MIN_LISTED cards in total
  - never together: they never appear as separate cards in one episode (a person has one card per episode), and this still holds
    for the whole merged set (so a shared short name cannot bridge two people)
  - no name conflict: same first name but different surnames (David Wallace / David Brent) are different people
Weaker pairs (listed once) are written to a review list and are NOT merged. Everything else stays separate; generic roles are never
linked across episodes (each primary name is its own entity). Merging is never transitive without these checks.

    python -m graph.link_characters --label v3-extract-001
Writes graph/out/character_links.json and graph/out/character_link_review.md.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from common.db import connect

OUT = Path(__file__).parent / "out"
MIN_LISTED = 2
TITLES = r"^(mr|mrs|ms|miss|dr|sir|mister|senator|officer|detective|captain)\.?\s+"


def norm(n):
    n = re.sub(r"[^a-z0-9' .\-]", "", n.lower().strip())
    return " ".join(re.sub(TITLES, "", n).split())


def surname_conflict(a, b):
    ta, tb = a.split(), b.split()
    return len(ta) >= 2 and len(tb) >= 2 and ta[0] == tb[0] and ta[-1] != tb[-1]


def load_cards(label):
    with connect("app") as c:
        rows = c.execute("""SELECT x.season, x.episode, x.payload FROM episode_extractions x JOIN extraction_runs r USING (run_id)
                            WHERE r.label=%s AND x.stage='reviewed' ORDER BY 1, 2""", (label,)).fetchall()
    cards = []
    for s, e, p in rows:
        for ch in p["characters"]:
            names = [norm(n) for n in ch["names"] if norm(n)]
            if names:
                cards.append({"ep": (s, e), "lid": ch["local_id"], "names": names, "desc": ch["description"], "present": ch["present"]})
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    cards = load_cards(a.label)
    groups = defaultdict(list)
    for cd in cards:
        groups[cd["names"][0]].append(cd)
    eps = {g: {cd["ep"] for cd in cs} for g, cs in groups.items()}
    # evidence: how many cards of A list B's primary name (and the reverse)
    listed = Counter()
    for cd in cards:
        for other in cd["names"][1:]:
            if other in groups and other != cd["names"][0]:
                listed[frozenset((cd["names"][0], other))] += 1
    comp = {g: {g} for g in groups}            # group -> its component (set of primary names)
    comp_eps = {g: set(eps[g]) for g in groups}

    def component(g):
        return comp[g]

    merged, blocked, weak = [], [], []
    for pair, n in sorted(listed.items(), key=lambda kv: (-kv[1], sorted(kv[0]))):
        x, y = sorted(pair)
        cx, cy = comp[x], comp[y]
        if cx is cy:
            continue
        together = len(eps[x] & eps[y])
        reason = None
        if together:
            reason = f"appear together as separate people in {together} episode(s)"
        elif any(surname_conflict(p, q) for p in cx for q in cy):
            reason = "surnames conflict inside the merged set: " + ", ".join(sorted(cx | cy))
        elif comp_eps[x] & comp_eps[y]:
            reason = "merged set would have two cards in one episode"
        row = {"a": x, "b": y, "listed": n, "sizes": [len(groups[x]), len(groups[y])]}
        if reason:
            blocked.append({**row, "why": reason}); continue
        if n < MIN_LISTED:
            weak.append(row); continue
        new = cx | cy
        ne = comp_eps[x] | comp_eps[y]
        for g in new:
            comp[g] = new
            comp_eps[g] = ne
        merged.append(row)

    seen, entities = set(), []
    for g in groups:
        if id(comp[g]) in seen:
            continue
        seen.add(id(comp[g]))
        members = sorted(comp[g], key=lambda m: -len(groups[m]))
        entities.append({"entity": members[0], "primary_names": members, "cards": sum(len(groups[m]) for m in members),
                         "episodes": len(comp_eps[g]), "merged": len(members) > 1})
    entities.sort(key=lambda e: -e["cards"])
    OUT.mkdir(exist_ok=True)
    (OUT / "character_links.json").write_text(json.dumps({"label": a.label, "entities": entities, "merged": merged, "blocked": blocked, "weak": weak}, indent=1))

    md = [f"# Character linking for run {a.label}", "",
          f"{len(cards)} cards -> {len(groups)} primary names -> **{len(entities)} entities** ({sum(e['merged'] for e in entities)} of them merged from 2+ names).", "",
          f"## Merged automatically ({len(merged)} pairs: listed on {MIN_LISTED}+ cards, never together, no surname conflict)", "",
          "| A | B | cards listing the other name | group sizes |", "|---|---|---|---|"]
    md += [f"| {r['a']} | {r['b']} | {r['listed']} | {r['sizes'][0]} / {r['sizes'][1]} |" for r in merged]
    md += ["", f"## Blocked ({len(blocked)}): evidence exists but a rule says they cannot be merged", "", "| A | B | listed | why |", "|---|---|---|---|"]
    md += [f"| {r['a']} | {r['b']} | {r['listed']} | {r['why']} |" for r in blocked]
    md += ["", f"## Weak ({len(weak)}): listed once, NOT merged (a known limitation; review if you want any)", "", "| A | B | sizes |", "|---|---|---|"]
    md += [f"| {r['a']} | {r['b']} | {r['sizes'][0]} / {r['sizes'][1]} |" for r in weak]
    md += ["", "## Entities with 2+ names", "", "| entity | names | cards | episodes |", "|---|---|---|---|"]
    md += [f"| {e['entity']} | {', '.join(e['primary_names'])} | {e['cards']} | {e['episodes']} |" for e in entities if e["merged"]]
    (OUT / "character_link_review.md").write_text("\n".join(md) + "\n")
    print(f"{len(cards)} cards, {len(groups)} primary names -> {len(entities)} entities; merged pairs {len(merged)}, blocked {len(blocked)}, weak {len(weak)}")
    print("merged:", [(r["a"], r["b"], r["listed"]) for r in merged])
    print("blocked:", [(r["a"], r["b"], r["listed"], r["why"][:40]) for r in blocked][:12])


if __name__ == "__main__":
    main()
