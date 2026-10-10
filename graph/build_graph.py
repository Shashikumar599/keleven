"""
Stage 2c: load the graph tables (migration 013) from the stored extractions and the linking result. No LLM.

Reads: episode_extractions (stage 'reviewed') of one extraction run, graph/out/certain_entities.json (link_certain.py) and
graph/out/tiered_entities.json (link_tiers.py). Writes one build into the graph_* tables; running it again with the same
label replaces that build. Dry run unless --run.

    python -m graph.build_graph --label v3-extract-001 --build v3-graph-001          # counts only
    python -m graph.build_graph --label v3-extract-001 --build v3-graph-001 --run
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from common.db import connect
from graph.link_characters import norm

OUT = Path(__file__).parent / "out"


def load_links(label):
    cert = json.loads((OUT / "certain_entities.json").read_text())
    if cert["label"] != label:
        raise SystemExit(f"certain_entities.json was made for {cert['label']}, not {label}; rerun graph.link_certain")
    tiers = json.loads((OUT / "tiered_entities.json").read_text())
    return cert, tiers


def entity_table(cert, tiers):
    """name -> entity dict; every primary name that maps to an entity points at it."""
    ents = {}
    for e in cert["entities"]:
        ents[e["entity"]] = {"name": e["entity"], "names": e["primary_names"], "tier": "certain", "note": e["note"]}
    for r in tiers:
        if r["tier"] in ("probable", "possible"):
            ents[r["name"]] = {"name": r["name"], "names": [r["name"]], "tier": r["tier"], "note": None, "possible_of": r["possible_of"]}
    by_primary = {n: e for e in ents.values() for n in e["names"]}
    return ents, by_primary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="extraction run label")
    ap.add_argument("--build", required=True, help="label of the graph build to write")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    cert, tiers = load_links(a.label)
    ents, by_primary = entity_table(cert, tiers)
    with connect("admin") as c:
        run_id = c.execute("SELECT run_id FROM extraction_runs WHERE label=%s", (a.label,)).fetchone()[0]
        rows = c.execute("SELECT season, episode, payload FROM episode_extractions WHERE run_id=%s AND stage='reviewed' AND payload IS NOT NULL ORDER BY 1,2", (run_id,)).fetchall()
        chars, places, events, parts, rels, sums, backs = [], [], [], [], [], [], []
        stats = defaultdict(lambda: {"cards": 0, "eps": set(), "seasons": set()})
        for s, e, p in rows:
            for ch in p["characters"]:
                names = [norm(n) for n in ch["names"] if norm(n)]
                ent = by_primary.get(names[0]) if names else None
                if ent:
                    st = stats[ent["name"]]
                    st["cards"] += 1; st["eps"].add((s, e)); st["seasons"].add(s)
                chars.append((s, e, ch["local_id"], ch["names"], ch["description"], ch["present"], ch["lines"], ent["name"] if ent else None))
            places += [(s, e, x["local_id"], x["name"], x["kind"], x["description"], x["lines"]) for x in p["places"]]
            for ev in p["events"]:
                events.append((s, e, ev["id"], ev["text"], ev["kind"], ev["place"], ev["certainty"], ev["importance"], ev["lines"]))
                parts += [(s, e, ev["id"], q["character"], q["role"]) for q in ev["participants"]]
            rels += [(s, e, r["rid"], r["a"], r["b"], r["type"], r["change"], r["detail"], r["quote"], r["certainty"], r["lines"]) for r in p["relations"]]
            backs += [(s, e, i, x["event"], x["text"], x["lines"]) for i, x in enumerate(p["refers_back"])]
            sums.append((s, e, p["summary"]))
        counts = {"episodes": len(rows), "characters": len(chars), "linked": sum(1 for x in chars if x[7]), "entities": len(stats),
                  "places": len(places), "events": len(events), "participants": len(parts), "relations": len(rels), "refers_back": len(backs)}
        by_tier = defaultdict(int)
        for x in chars:
            if x[7]:
                by_tier[ents[x[7]]["tier"]] += 1
        print(counts, dict(by_tier))
        if not a.run:
            print("dry run; add --run to write")
            return
        c.execute("DELETE FROM graph_builds WHERE label=%s", (a.build,))
        rules = {"extraction_run": a.label, "certain": {"min_episodes": 40}, "probable_possible": {"min_episodes": 3},
                 "inputs": ["certain_entities.json", "tiered_entities.json"]}
        bid = c.execute("INSERT INTO graph_builds (label, run_id, rules, counts) VALUES (%s,%s,%s,%s) RETURNING build_id",
                        (a.build, run_id, json.dumps(rules), json.dumps(counts))).fetchone()[0]
        with c.cursor() as cur:
            for name, st in stats.items():
                en = ents[name]
                cur.execute("INSERT INTO graph_entities (build_id, name, names, tier, cards, episodes, seasons, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (bid, name, en["names"], en["tier"], st["cards"], len(st["eps"]), sorted(st["seasons"]), en["note"]))
            for name in stats:
                en = ents[name]
                if en["tier"] == "possible":
                    for anchor in en.get("possible_of", []):
                        target = by_primary[anchor]["name"] if anchor in by_primary else None
                        if target in stats and target != name:
                            cur.execute("INSERT INTO graph_entity_links VALUES (%s,%s,%s,'possible_same') ON CONFLICT DO NOTHING", (bid, name, target))
            for s_, e_, lid, names, desc, present, lines, ename in chars:
                cur.execute("INSERT INTO graph_characters VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (bid, s_, e_, lid, names, desc, present, lines, ename, ents[ename]["tier"] if ename else None))
            cur.executemany("INSERT INTO graph_places VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", [(bid, *x) for x in places])
            cur.executemany("INSERT INTO graph_events VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [(bid, *x) for x in events])
            cur.executemany("INSERT INTO graph_event_participants VALUES (%s,%s,%s,%s,%s,%s)", [(bid, *x) for x in parts])
            cur.executemany("INSERT INTO graph_relations VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [(bid, *x) for x in rels])
            cur.executemany("INSERT INTO graph_refers_back VALUES (%s,%s,%s,%s,%s,%s,%s)", [(bid, *x) for x in backs])
            cur.executemany("INSERT INTO graph_episode_summaries VALUES (%s,%s,%s,%s)", [(bid, *x) for x in sums])
            cur.execute("INSERT INTO graph_current (only_row, build_id) VALUES (true, %s) ON CONFLICT (only_row) DO UPDATE SET build_id = EXCLUDED.build_id", (bid,))
        c.commit()
        print("written build", a.build, "id", bid)


if __name__ == "__main__":
    main()
