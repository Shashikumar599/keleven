"""
Stage 2b: confidence tiers for the characters that are not certain (link_certain.py). No LLM, nothing written to the database.

Certain entities come from link_certain.py (40+ episodes, one card per episode). Here the remaining primary-name groups get a
tier, stored per group so a query can filter by it:
  probable  a full name (2+ words) with cards in MIN_EPISODES+ episodes and never two cards in one episode
  possible  a one-word name with cards in MIN_EPISODES+ episodes and one card per episode (it may be a role or several people), and
            a one-word group that matches the first or last word of a certain/probable entity and never appears in an episode
            together with it: listed as a candidate link ("possible_of"), never merged
Groups are never chained and never merged into each other; a possible_of link only points at one named entity.

    python -m graph.link_tiers --label v3-extract-001
Writes graph/out/tiered_entities.json and graph/out/tiered_entities.md.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from graph.link_characters import load_cards

OUT = Path(__file__).parent / "out"
MIN_EPISODES = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    cards = load_cards(a.label)
    cert = json.loads((OUT / "certain_entities.json").read_text())
    certain = {n: e for e in cert["entities"] for n in e["primary_names"]}      # primary name -> certain entity
    groups = defaultdict(list)
    for cd in cards:
        groups[cd["names"][0]].append(cd)
    eps = {g: {cd["ep"] for cd in cs} for g, cs in groups.items()}
    rows = []
    for g, cs in groups.items():
        if g in certain or len(eps[g]) < MIN_EPISODES:
            continue
        one_per_ep = len(eps[g]) == len(cs)
        words = len(g.split())
        if words >= 2 and one_per_ep:
            tier = "probable"
        elif words == 1 and one_per_ep:
            tier = "possible"
        else:
            tier = "unlinked"           # two cards in one episode: more than one person under this name
        rows.append({"name": g, "tier": tier, "cards": len(cs), "episodes": len(eps[g]), "seasons": sorted({e[0] for e in eps[g]}),
                     "sample_desc": cs[0]["desc"][:100], "possible_of": []})
    anchors = {r["name"]: r for r in rows if r["tier"] == "probable"} | {n: {"name": n, "episodes": e["episodes"]} for n, e in certain.items()}
    for r in rows:
        if r["tier"] != "possible":
            continue
        for an, ent in anchors.items():
            w = an.split()
            if len(w) >= 2 and r["name"] in (w[0], w[-1]) and not (eps[r["name"]] & eps.get(an, set())):
                r["possible_of"].append(an)
    rows.sort(key=lambda r: (r["tier"] != "probable", r["tier"] != "possible", -r["episodes"]))
    OUT.mkdir(exist_ok=True)
    (OUT / "tiered_entities.json").write_text(json.dumps(rows, indent=1))
    md = [f"# Confidence tiers for non-certain characters, run {a.label}", "",
          f"Groups with cards in {MIN_EPISODES}+ episodes. probable = full name, one card per episode. possible = one-word name, one card per "
          "episode; possible_of lists named entities it might be the same as (never merged). unlinked = several cards in one episode.", ""]
    for t in ("probable", "possible", "unlinked"):
        rs = [r for r in rows if r["tier"] == t]
        md += [f"## {t} ({len(rs)})", "", "| name | cards | episodes | seasons | possible_of | description of first card |", "|---|---|---|---|---|---|"]
        md += [f"| {r['name']} | {r['cards']} | {r['episodes']} | {r['seasons'][0]}-{r['seasons'][-1]} | {', '.join(r['possible_of']) or '-'} | {r['sample_desc']} |" for r in rs]
        md.append("")
    (OUT / "tiered_entities.md").write_text("\n".join(md))
    from collections import Counter
    print(Counter(r["tier"] for r in rows), "cards covered:", {t: sum(r["cards"] for r in rows if r["tier"] == t) for t in ("probable", "possible", "unlinked")})
    for r in rows[:40]:
        print(r["tier"], r["name"], r["cards"], r["episodes"], r["possible_of"])


if __name__ == "__main__":
    main()
