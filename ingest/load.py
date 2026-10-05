#!/usr/bin/env python3
"""
Load the cleaned transcript into Postgres (Phase 1, Part 1).

Usage:
    set -a; source .env; set +a
    python ingest/load.py

Prerequisites: the database is running (docker-compose.db.yml) and migrations 001-003 are applied.

What it does:
    1. Reads data/processed/episodes.parquet and lines.parquet.
    2. (Deleted scenes are already dropped by ingest/clean.py.)
    3. In ONE transaction: empties episodes and lines, and the chunk tables built from them (chunks go stale
       when lines are reloaded; re-run ingest/chunk.py afterwards), then bulk-loads with COPY.
       A failure anywhere rolls back, so the database keeps its previous contents.
    4. Checks the result: row counts, and that Postgres's generated `dialogue` matches
       the dialogue computed during cleaning.

Re-running replaces the data: the Parquet files are the source of truth, the tables are a copy.

Connection: DATABASE_URL if set (hosted), otherwise the POSTGRES_* variables from .env on
localhost:5433. Passing the password as a separate parameter avoids URL-encoding it.
"""
from pathlib import Path

import pandas as pd

from common.db import connect

PROCESSED = Path("data/processed")


def read_processed():
    episodes = pd.read_parquet(PROCESSED / "episodes.parquet")[["season", "episode", "title"]]
    lines = pd.read_parquet(PROCESSED / "lines.parquet")
    return episodes, lines


def copy_rows(cur, table, df):
    """Bulk-load a DataFrame with COPY, one row at a time (no second copy of the data).
    itertuples gives plain Python ints/strs, which psycopg can send."""
    cols = list(df.columns)
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as copy:
        for row in df.itertuples(index=False, name=None):
            copy.write_row(row)


def main():
    episodes, lines = read_processed()
    load_cols = ["id", "season", "episode", "scene", "speaker", "text"]
    print(f"read: {len(episodes)} episodes, {len(lines)} aired lines")

    with connect() as conn:                      # one transaction: commits on success, rolls back on error
        with conn.cursor() as cur:
            # Chunks are built from lines, so reloading lines makes every chunk set stale: clear them too.
            cur.execute("SELECT count(*) FROM chunk_sets")
            n_sets = cur.fetchone()[0]
            cur.execute("TRUNCATE chunks, chunk_sets, lines, episodes")
            print(f"cleared {n_sets} chunk set(s); re-run ingest/chunk.py after loading")
            copy_rows(cur, "episodes", episodes)
            copy_rows(cur, "lines", lines[load_cols])
            print("loaded, checking...")

            cur.execute("""
                SELECT (SELECT count(*) FROM episodes),
                       count(*),
                       count(DISTINCT (season, episode, scene)),
                       count(*) FILTER (WHERE dialogue = '')
                FROM lines
            """)
            n_episodes, n_lines, n_scenes, n_direction_only = cur.fetchone()

            cur.execute("SELECT id, dialogue FROM lines")
            pg_dialogue = dict(cur.fetchall())

            # every episode's scenes must be 1..N with no gaps (renumbered in clean.py)
            cur.execute("""
                SELECT count(*) FROM (
                  SELECT season, episode FROM lines GROUP BY 1, 2
                  HAVING min(scene) <> 1 OR max(scene) <> count(DISTINCT scene)
                ) t
            """)
            n_gappy = cur.fetchone()[0]

        if n_episodes != len(episodes) or n_lines != len(lines):
            raise SystemExit(f"row counts don't match: {n_episodes}/{len(episodes)} episodes, "
                             f"{n_lines}/{len(lines)} lines. Rolled back.")
        if n_gappy:
            raise SystemExit(f"{n_gappy} episodes have gaps in scene numbers or don't start at 1. "
                             f"Re-run ingest/clean.py. Rolled back.")

    expected = dict(zip(lines["id"], lines["dialogue"]))
    mismatches = [i for i, d in expected.items() if pg_dialogue.get(i) != d]

    print(f"episodes:             {n_episodes}")
    print(f"lines:                {n_lines}")
    print(f"scenes:               {n_scenes}")
    print(f"direction-only lines: {n_direction_only}")
    print(f"dialogue mismatches (Postgres vs cleaning): {len(mismatches)}")
    for i in mismatches[:5]:
        print(f"  id {i}:\n    pg:     {pg_dialogue[i]!r}\n    parquet:{expected[i]!r}")


if __name__ == "__main__":
    main()
