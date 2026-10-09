"""
Build a review file from a stored run: a high-level analysis plus a random sample of events and relations, each with the
lines it cites, for the owner to read. No LLM calls. Written to graph/out/ (not committed: it quotes transcript lines).

    python -m graph.make_sample --label v3-extract-001 --events 30 --relations 20 --seed 7
"""
import argparse
import random
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from common.db import connect
from graph.validate import load_episode

OUT = Path(__file__).parent / "out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--events", type=int, default=30)
    ap.add_argument("--relations", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    with connect("app") as c:
        rows = c.execute("""SELECT x.season, x.episode, x.stage, x.status, x.payload, x.issues FROM episode_extractions x
                            JOIN extraction_runs r USING (run_id) WHERE r.label=%s AND x.stage IN ('reviewed','validated')
                            ORDER BY 1, 2""", (a.label,)).fetchall()
        titles = dict(((s, e), t) for s, e, t in c.execute("SELECT season, episode, title FROM episodes").fetchall())
    reviewed = {(s, e): (st_, p, i) for s, e, stage, st_, p, i in rows if stage == "reviewed"}
    rng = random.Random(a.seed)

    # ---- analysis
    per_season = defaultdict(Counter)
    events, relations = [], []
    flag_rules = Counter()
    for (s, e), (status, p, issues) in reviewed.items():
        per_season[s]["episodes"] += 1
        for k in ("characters", "places", "events", "relations"):
            per_season[s][k] += len(p[k])
        per_season[s]["major"] += sum(1 for ev in p["events"] if ev["importance"] == "major")
        per_season[s]["flagged episodes"] += status == "flagged"
        for i in issues:
            flag_rules[(i["severity"], i["rule"])] += 1
        names = {x["local_id"]: (x["names"][0] if x["names"] else x["local_id"]) for x in p["characters"]}
        places = {x["local_id"]: x["name"] for x in p["places"]}
        for ev in p["events"]:
            events.append((s, e, ev, names, places))
        for r in p["relations"]:
            relations.append((s, e, r, names))
    n_ev = len(events)
    ev_flag = sum(1 for x in events if x[2]["flags"])
    part_flag = sum(1 for x in events if "participant_not_in_lines" in x[2]["flags"])
    words = [len(x[2]["text"].split()) for x in events]
    ppl = [len(x[2]["participants"]) for x in events]
    lines_per_ev = [len(x[2]["lines"]) for x in events]

    md = [f"# Quality sample of run {a.label}", "",
          f"Random sample (seed {a.seed}) of {a.events} events and {a.relations} relations from the reviewed version of every episode, "
          "each with the lines it cites. Mark each item and add notes; the verdict boxes are for you. "
          "This file quotes transcript lines: it is in graph/out/ and not committed.", "",
          "## High-level analysis", "", f"{len(reviewed)} episodes, {n_ev} events, {len(relations)} relations.", "",
          "### Per season", "", "| season | episodes | characters | places | events | major events | relations | flagged episodes |", "|---|---|---|---|---|---|---|---|"]
    for s in sorted(per_season):
        d = per_season[s]
        md.append(f"| {s} | {d['episodes']} | {d['characters']} | {d['places']} | {d['events']} | {d['major']} ({100 * d['major'] // max(d['events'], 1)}%) | {d['relations']} | {d['flagged episodes']} |")
    md += ["", "### Events", "",
           f"- text length: median {st.median(words)} words (max {max(words)}); participants per event: median {st.median(ppl)}; cited lines per event: median {st.median(lines_per_ev)}",
           f"- events with at least one validator flag: {ev_flag} ({100 * ev_flag // n_ev}%); of these participant_not_in_lines: {part_flag}",
           f"- kind: {dict(Counter(x[2]['kind'] for x in events).most_common())}",
           f"- importance: {dict(Counter(x[2]['importance'] for x in events))}; certainty: {dict(Counter(x[2]['certainty'] for x in events))}",
           f"- events without a place: {sum(1 for x in events if not x[2].get('place'))} ({100 * sum(1 for x in events if not x[2].get('place')) // n_ev}%)", "",
           "### Relations", "",
           f"- type: {dict(Counter(x[2]['type'] for x in relations).most_common())}",
           f"- change: {dict(Counter(x[2]['change'] for x in relations))}; certainty: {dict(Counter(x[2]['certainty'] for x in relations))}",
           f"- episodes with no relation: {sum(1 for v in reviewed.values() if not v[1]['relations'])} of {len(reviewed)}",
           f"- relations with a flag: {sum(1 for x in relations if x[2]['flags'])}", "",
           "### Validator findings after review", ""]
    md += [f"- {sev} · {rule}: {n}" for (sev, rule), n in flag_rules.most_common()]

    # ---- samples
    def lines_block(s, e, ids, cache={}):
        if (s, e) not in cache:
            cache[(s, e)] = load_episode(s, e)
        L = cache[(s, e)]
        return [f"  - [L{i}] {L[i]['speaker']}: {L[i]['text'][:260]}" for i in ids if i in L]

    md += ["", f"## Events ({a.events})", ""]
    for n, (s, e, ev, names, places) in enumerate(rng.sample(events, min(a.events, n_ev)), 1):
        who = "; ".join(f"{names.get(p['character'], p['character'])} ({p['role']})" for p in ev["participants"]) or "(none)"
        md += [f"### E{n:02d} · S{s}E{e} {titles[(s, e)]} · {ev['id']} · {ev['kind']} · {ev['importance']} · {ev['certainty']}", "",
               f"**Event:** {ev['text']}", "", f"**Who:** {who}  ", f"**Place:** {places.get(ev.get('place'), '-')}  ",
               f"**Validator:** {', '.join(ev['flags']) or 'no flags'}", "", "**Cited lines:**"]
        md += lines_block(s, e, ev["lines"])
        md += ["", "**Verdict:** [ ] correct  [ ] partly  [ ] wrong  [ ] importance wrong  · Notes:", ""]
    md += [f"## Relations ({a.relations})", ""]
    for n, (s, e, r, names) in enumerate(rng.sample(relations, min(a.relations, len(relations))), 1):
        md += [f"### R{n:02d} · S{s}E{e} {titles[(s, e)]} · {r['rid'] if 'rid' in r else ''} · {r['type']} · {r['change']} · {r['certainty']}", "",
               f"**Relation:** {names.get(r['a'], r['a'])} – {names.get(r['b'], r['b'])}: {r['type']} ({r['change']})  ",
               f"**Quote:** {r.get('quote') or '(none)'}  ", f"**Validator:** {', '.join(r['flags']) or 'no flags'}", "", "**Cited lines:**"]
        md += lines_block(s, e, r["lines"])
        md += ["", "**Verdict:** [ ] correct  [ ] partly  [ ] wrong  [ ] certainty wrong  · Notes:", ""]
    OUT.mkdir(exist_ok=True)
    dest = OUT / "quality-sample.md"
    dest.write_text("\n".join(md) + "\n")
    print("wrote", dest, f"({len(md)} lines)")


if __name__ == "__main__":
    main()
