"""
Stage 2a (strict): the only character entities are the ones the data proves. Everything else stays unlinked (each card is a local
node of its episode and is still found through event text and the v2 search). No LLM, nothing written to the database.

A primary-name group (cards whose first name is the same) is CERTAIN when it has cards in at least MIN_EPISODES (40) episodes and never
two cards in one episode. A name that recurs in 40+ episodes cannot be a one-off collision between different people, so no name or
description test is needed (those tests failed on maiden and married names, and on a one-card surname). Smaller groups are
attached only on strong evidence: the certain group's cards list the name on 2+ cards and the two never appear together in an
episode. Everything else stays unlinked. Any surname variants inside a certain group are only reported as a note. Merging is never
transitive.

    python -m graph.link_certain --label v3-extract-001
Writes graph/out/certain_entities.json and graph/out/certain_entities.md.
"""
import argparse
import itertools
import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from graph.link_characters import load_cards

OUT = Path(__file__).parent / "out"
MIN_CARDS, MIN_EPISODES, MIN_LISTED = 10, 40, 2


def same_surname(a, b):
    a, b = a.rstrip(".").replace("-", " "), b.rstrip(".").replace("-", " ")
    return a == b or a.startswith(b) or b.startswith(a) or SequenceMatcher(None, a, b).ratio() >= 0.75


def conflicts(full_names, cards):
    """Pairs of full names with the same first name and different surnames that no card lists together."""
    found = []
    for a, b in itertools.combinations(sorted(full_names), 2):
        ta, tb = a.split(), b.split()
        if ta[0] != tb[0] or len(ta) < 2 or len(tb) < 2 or same_surname(ta[-1], tb[-1]):
            continue
        if any(a in cd["names"] and b in cd["names"] for cd in cards):
            continue
        found.append((a, b))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    cards = load_cards(a.label)
    groups = defaultdict(list)
    for cd in cards:
        groups[cd["names"][0]].append(cd)
    eps = {g: {cd["ep"] for cd in cs} for g, cs in groups.items()}
    certain, rejected = {}, []
    for g, cs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(eps[g]) < MIN_EPISODES:
            continue
        first = g.split()[0]
        full = Counter(n for cd in cs for n in set(cd["names"]) if len(n.split()) >= 2 and n.split()[0] == first)
        full = {n for n, k in full.items() if k >= 2}          # a name on one card only is noise
        why = None
        bad = conflicts(full, cs)
        if len({cd["ep"] for cd in cs}) < len(cs):
            why = "two cards for this name in one episode"
        if why:
            rejected.append({"name": g, "cards": len(cs), "why": why})
        else:
            certain[g] = {"entity": g, "primary_names": [g], "cards": len(cs), "episodes": len(eps[g]),
                          "seasons": sorted({e[0] for e in eps[g]}),
                          "note": ("surname variants listed: " + "; ".join(f"{x} / {y}" for x, y in bad[:3])) if bad else None}
    # attach smaller groups on strong evidence
    listed = Counter()
    for cd in cards:
        for other in cd["names"][1:]:
            if other in groups and other != cd["names"][0]:
                listed[(cd["names"][0], other)] += 1
    attached = []
    taken = set()
    for (x, y), n in sorted(listed.items(), key=lambda kv: -kv[1]):
        for big, small in ((x, y), (y, x)):
            if big in certain and small not in certain and small not in taken and n + listed.get((y, x), 0) * (big == x) >= MIN_LISTED:
                together = eps[big] & eps[small]
                full = {nm for cd in groups[big] + groups[small] for nm in cd["names"] if len(nm.split()) >= 2}
                if together or conflicts({nm for nm in full if nm.split()[0] == small.split()[0] or nm.split()[0] == big.split()[0]}, groups[big] + groups[small]):
                    continue
                if len(listed) and n >= MIN_LISTED:
                    certain[big]["primary_names"].append(small)
                    certain[big]["cards"] += len(groups[small])
                    eps[big] = eps[big] | eps[small]
                    certain[big]["episodes"] = len(eps[big])
                    taken.add(small)
                    attached.append({"into": big, "name": small, "listed": n, "cards": len(groups[small])})
    covered = sum(e["cards"] for e in certain.values())
    ents = sorted(certain.values(), key=lambda e: -e["cards"])
    OUT.mkdir(exist_ok=True)
    (OUT / "certain_entities.json").write_text(json.dumps({"label": a.label, "entities": ents, "attached": attached, "rejected": rejected}, indent=1))
    md = [f"# Certain character entities, run {a.label}", "",
          f"Rule: cards in {MIN_EPISODES}+ episodes and one card per episode; smaller groups attach only on {MIN_LISTED}+ listings and never together in an episode.", "",
          f"**{len(ents)} certain entities cover {covered} of {len(cards)} cards ({100 * covered // len(cards)}%).** The other {len(cards) - covered} cards stay unlinked (local to their episode).", "",
          "| entity | names merged in | cards | episodes | seasons | note |", "|---|---|---|---|---|---|"]
    md += [f"| {e['entity']} | {', '.join(e['primary_names'][1:]) or '-'} | {e['cards']} | {e['episodes']} | {e['seasons'][0]}-{e['seasons'][-1]} | {e['note'] or ''} |" for e in ents]
    md += ["", "## Large groups rejected (not certain)", "", "| name | cards | why |", "|---|---|---|"] + [f"| {r['name']} | {r['cards']} | {r['why']} |" for r in rejected]
    md += ["", "## Small groups attached on strong evidence", "", "| attached | into | listed | cards |", "|---|---|---|---|"] + [f"| {r['name']} | {r['into']} | {r['listed']} | {r['cards']} |" for r in attached]
    (OUT / "certain_entities.md").write_text("\n".join(md) + "\n")
    print(f"{len(ents)} certain entities cover {covered} of {len(cards)} cards ({100 * covered // len(cards)}%); rejected {len(rejected)}; attached {len(attached)}")
    print("rejected:", [(r["name"], r["cards"], r["why"][:70]) for r in rejected])
    print("attached:", [(r["name"], r["into"], r["listed"]) for r in attached])
    print("entities:", [(e["entity"], e["cards"]) for e in ents])


if __name__ == "__main__":
    main()
