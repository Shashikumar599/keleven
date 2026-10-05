#!/usr/bin/env python3
"""
Build one chunk set from the lines in Postgres (Phase 1, Part 2).

Usage:
    set -a; source .env; set +a
    python ingest/chunk.py --dry-run          # build and print a summary, write nothing
    python ingest/chunk.py                    # build and store as a new chunk set

Rules (see findings/decisions.md, Part 2):
    - Pack consecutive whole scenes of one episode. Start a new chunk when the next scene would push the
      content over --max-tokens or over --max-scenes. A scene is never split: a big scene stands alone.
    - Afterwards, merge any chunk under --min-tokens into its smaller neighbour (may exceed the target).
    - Never cross an episode.
    - Tokens are counted with tiktoken on the full content (header + "Speaker: text" lines), which is
      exactly what gets embedded. Any chunk over --hard-limit stops the run.

Content format:
    S3E20 Product Recall | scenes 6-7
    <blank line>
    Scene 6
    Speaker: text            (one per line, script order, stage directions included)
    ...
    <blank line>
    Scene 7
    Speaker: text

The chunk set and all its chunks are written in one transaction. --replace deletes an existing set with the
same name first (in the same transaction).
"""
import argparse
import json
import statistics
from itertools import groupby

import tiktoken

from common.db import connect

TOKENIZER = "cl100k_base"
ENC = tiktoken.get_encoding(TOKENIZER)


def n_tokens(text):
    return len(ENC.encode(text))


# ---------- reading ----------

def read_episodes(conn):
    """Yield (season, episode, title, scenes); scenes = [(scene_no, [(line_id, "Speaker: text"), ...]), ...]."""
    rows = conn.execute("""
        SELECT season, episode, title, scene, id, speaker, text
        FROM lines_full
        ORDER BY id
    """).fetchall()
    for (season, episode, title), ep_rows in groupby(rows, key=lambda r: r[:3]):
        scenes = [(scene, [(r[4], f"{r[5]}: {r[6]}") for r in sc_rows])
                  for scene, sc_rows in groupby(ep_rows, key=lambda r: r[3])]
        yield season, episode, title, scenes


# ---------- building ----------

def render(season, episode, title, scenes):
    """Header, then one block per scene: a "Scene N" line followed by its lines. Blocks are separated by a
    blank line so scene cuts stay visible (e.g. a promise in one scene, everyone knowing in the next)."""
    first, last = scenes[0][0], scenes[-1][0]
    label = f"scene {first}" if first == last else f"scenes {first}-{last}"
    blocks = [f"Scene {scene_no}\n" + "\n".join(text for _, text in sc_lines) for scene_no, sc_lines in scenes]
    return f"S{season}E{episode} {title} | {label}\n\n" + "\n\n".join(blocks)


def pack(season, episode, title, scenes, max_tokens, max_scenes):
    """Greedy packing of whole scenes; returns a list of groups (each a list of scenes)."""
    groups, current = [], []
    for sc in scenes:
        candidate = current + [sc]
        too_big = n_tokens(render(season, episode, title, candidate)) > max_tokens
        too_many = len(candidate) > max_scenes
        if current and (too_big or too_many):
            groups.append(current)
            current = [sc]
        else:
            current = candidate
    groups.append(current)
    return groups


def merge_small(season, episode, title, groups, min_tokens, hard_limit):
    """Merge groups under min_tokens into their smaller neighbour, as long as the result stays under hard_limit."""
    tok = lambda g: n_tokens(render(season, episode, title, g))
    merged = 0
    i = 0
    while len(groups) > 1 and i < len(groups):
        if tok(groups[i]) >= min_tokens:
            i += 1
            continue
        neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(groups)]
        neighbours.sort(key=lambda j: tok(groups[j]))
        for j in neighbours:
            lo, hi = min(i, j), max(i, j)
            combined = groups[lo] + groups[hi]
            if tok(combined) <= hard_limit:
                groups[lo:hi + 1] = [combined]
                merged += 1
                i = max(lo - 1, 0)          # re-check around the merge
                break
        else:
            i += 1                           # can't merge without breaking the hard limit; leave it
    return groups, merged


def build(conn, max_tokens, max_scenes, min_tokens, hard_limit):
    chunks, merged_total = [], 0
    for season, episode, title, scenes in read_episodes(conn):
        groups = pack(season, episode, title, scenes, max_tokens, max_scenes)
        groups, merged = merge_small(season, episode, title, groups, min_tokens, hard_limit)
        merged_total += merged
        for position, g in enumerate(groups, start=1):
            content = render(season, episode, title, g)
            tokens = n_tokens(content)
            if tokens > hard_limit:
                raise SystemExit(f"S{season}E{episode} chunk {position} has {tokens} tokens "
                                 f"(> hard limit {hard_limit}). Nothing written.")
            line_ids = [lid for _, sc_lines in g for lid, _ in sc_lines]
            chunks.append({
                "season": season, "episode": episode, "position": position,
                "first_line_id": line_ids[0], "last_line_id": line_ids[-1],
                "content": content, "token_count": tokens, "n_scenes": len(g),
            })
    return chunks, merged_total


# ---------- writing ----------

def write(conn, name, params, chunks, replace):
    with conn.transaction():
        if replace:
            deleted = conn.execute("DELETE FROM chunk_sets WHERE name = %s", (name,)).rowcount
            if deleted:
                print(f"replaced existing chunk set {name} (its chunks are deleted with it)")
        chunk_set_id = conn.execute(
            "INSERT INTO chunk_sets (name, params) VALUES (%s, %s) RETURNING chunk_set_id",
            (name, json.dumps(params)),
        ).fetchone()[0]
        cols = ["chunk_set_id", "season", "episode", "position", "first_line_id", "last_line_id",
                "content", "token_count"]
        with conn.cursor().copy(f"COPY chunks ({', '.join(cols)}) FROM STDIN") as copy:
            for c in chunks:
                copy.write_row([chunk_set_id] + [c[k] for k in cols[1:]])
    return chunk_set_id


# ---------- summary ----------

def summarize(chunks, merged, max_tokens, max_scenes):
    toks = sorted(c["token_count"] for c in chunks)
    q = lambda p: toks[min(len(toks) - 1, int(p * len(toks)))]
    scenes = [c["n_scenes"] for c in chunks]
    print(f"chunks:            {len(chunks)}")
    print(f"tokens:            min {toks[0]}, median {statistics.median(toks):.0f}, p90 {q(0.9)}, "
          f"p99 {q(0.99)}, max {toks[-1]}")
    print(f"over target {max_tokens}:   {sum(t > max_tokens for t in toks)} "
          f"(single big scenes or merged small chunks)")
    print(f"scenes per chunk:  " + ", ".join(f"{k}: {scenes.count(k)}" for k in sorted(set(scenes))))
    print(f"over {max_scenes} scenes:      {sum(s > max_scenes for s in scenes)} (from merging small chunks)")
    print(f"small chunks merged: {merged}")
    print(f"total tokens:      {sum(toks)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=250)
    ap.add_argument("--max-scenes", type=int, default=3)
    ap.add_argument("--min-tokens", type=int, default=80)
    ap.add_argument("--hard-limit", type=int, default=2048)
    ap.add_argument("--dry-run", action="store_true", help="build and summarize, write nothing")
    ap.add_argument("--replace", action="store_true", help="delete an existing chunk set with the same name first")
    args = ap.parse_args()

    name = f"pack_{args.max_tokens}t_{args.max_scenes}s_{args.min_tokens}min"
    params = {
        "strategy": "pack_scenes",
        "max_tokens": args.max_tokens, "max_scenes": args.max_scenes,
        "min_tokens": args.min_tokens, "hard_limit": args.hard_limit,
        "tokenizer": f"tiktoken:{TOKENIZER}",
        "header": "S{season}E{episode} {title} | scene(s) {first}-{last}",
        "scene_format": "Scene {n}, then its lines; scenes separated by a blank line",
        "line_format": "{speaker}: {text}",
        "source": "lines (aired only)",
    }

    with connect() as conn:
        chunks, merged = build(conn, args.max_tokens, args.max_scenes, args.min_tokens, args.hard_limit)
        print(f"chunk set: {name}\n")
        summarize(chunks, merged, args.max_tokens, args.max_scenes)
        if args.dry_run:
            print("\ndry run: nothing written")
            return
        chunk_set_id = write(conn, name, params, chunks, args.replace)
        print(f"\nwritten as chunk_set_id {chunk_set_id}")


if __name__ == "__main__":
    main()
