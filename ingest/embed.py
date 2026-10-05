#!/usr/bin/env python3
"""
Embed one chunk set with one Voyage model (Phase 1, Part 3).

Usage:
    set -a; source .env; set +a
    python ingest/embed.py --dry-run              # show what would be embedded, call nothing
    python ingest/embed.py --limit 20             # embed a few chunks to try it out
    python ingest/embed.py                        # embed everything that's missing or stale

What it does:
    1. Registers the model in embedding_models (name '<model>@<dimensions>'). If that name already exists with
       different settings, it stops: vectors made with different settings must never be mixed.
    2. Selects chunks of the chunk set that have no vector for this model, or whose content changed since they
       were embedded (hash mismatch). Re-running only does what's missing, so the script is resumable.
    3. Sends them to Voyage in batches (input_type "document"), retrying on rate limits and server errors.
    4. Checks every vector has the expected size, then upserts it with the SHA-256 of the content.
       Each batch is committed on its own, so progress survives an interruption.

Connection: common/db.py (admin role). Voyage: common/voyage.py, VOYAGE_API_KEY and VOYAGE_API_URL
(default https://ai.mongodb.com/v1/embeddings, the endpoint for keys created in MongoDB Atlas).
"""
import argparse
import hashlib
import json
import time

from common.db import connect
from common.voyage import embed as voyage_embed, to_pgvector

MODEL_CONTEXT = 32_000        # voyage-4 family input limit per text (tokens)


# ---------- database ----------

def register_model(conn, name, model, dimensions, settings):
    conn.execute("""
        INSERT INTO embedding_models (name, provider, model, dimensions, settings)
        VALUES (%s, 'voyage (mongodb atlas)', %s, %s, %s)
        ON CONFLICT (name) DO NOTHING
    """, (name, model, dimensions, json.dumps(settings)))
    model_id, stored_dims, stored_settings = conn.execute(
        "SELECT model_id, dimensions, settings FROM embedding_models WHERE name = %s", (name,)).fetchone()
    if stored_dims != dimensions or stored_settings != settings:
        raise SystemExit(f"{name} already exists with different settings: {stored_dims} {stored_settings}. "
                         f"Use a new name instead of mixing vectors.")
    conn.commit()
    return model_id


def chunks_to_embed(conn, chunk_set_id, model_id, limit):
    """Chunks with no vector for this model, or whose content changed since embedding."""
    return conn.execute("""
        SELECT c.chunk_id, c.content, c.token_count
        FROM chunks c
        LEFT JOIN chunk_embeddings e
               ON e.model_id = %s AND e.chunk_set_id = c.chunk_set_id AND e.chunk_id = c.chunk_id
        WHERE c.chunk_set_id = %s
          AND (e.chunk_id IS NULL
               OR e.content_sha256 <> encode(sha256(convert_to(c.content, 'UTF8')), 'hex'))
        ORDER BY c.chunk_id
        LIMIT %s
    """, (model_id, chunk_set_id, limit)).fetchall()


def batches(rows, max_texts, max_tokens):
    """Group chunks so each request stays under max_texts and (estimated) max_tokens."""
    batch, tokens = [], 0
    for row in rows:
        if batch and (len(batch) >= max_texts or tokens + row[2] > max_tokens):
            yield batch
            batch, tokens = [], 0
        batch.append(row)
        tokens += row[2]
    if batch:
        yield batch


def store(conn, model_id, chunk_set_id, rows, vectors, dimensions):
    for (chunk_id, _, _), vec in zip(rows, vectors):
        if len(vec) != dimensions:
            raise SystemExit(f"chunk {chunk_id}: got {len(vec)} dimensions, expected {dimensions}")
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO chunk_embeddings (model_id, chunk_set_id, chunk_id, content_sha256, embedding)
            VALUES (%s, %s, %s, %s, %s::vector)
            ON CONFLICT (model_id, chunk_set_id, chunk_id)
            DO UPDATE SET content_sha256 = EXCLUDED.content_sha256,
                          embedding      = EXCLUDED.embedding,
                          embedded_at    = now()
        """, [(model_id, chunk_set_id, chunk_id,
               hashlib.sha256(content.encode("utf-8")).hexdigest(),
               to_pgvector(vec))
              for (chunk_id, content, _), vec in zip(rows, vectors)])
    conn.commit()


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-set", default="pack_300t_3s_80min")
    ap.add_argument("--model", default="voyage-4-large")
    ap.add_argument("--dimensions", type=int, default=1024)
    ap.add_argument("--batch-texts", type=int, default=128, help="max chunks per request")
    ap.add_argument("--batch-tokens", type=int, default=60_000, help="max estimated tokens per request")
    ap.add_argument("--limit", type=int, default=None, help="embed at most this many chunks")
    ap.add_argument("--dry-run", action="store_true", help="count what would be embedded, call nothing")
    args = ap.parse_args()

    name = f"{args.model}@{args.dimensions}"
    # only what changes the vectors (the endpoint doesn't: it proxies the same model)
    settings = {"input_type_documents": "document", "input_type_queries": "query", "output_dtype": "float"}

    with connect() as conn:
        row = conn.execute("SELECT chunk_set_id FROM chunk_sets WHERE name = %s", (args.chunk_set,)).fetchone()
        if not row:
            raise SystemExit(f"chunk set {args.chunk_set} not found")
        chunk_set_id = row[0]

        if args.dry_run:
            model_row = conn.execute("SELECT model_id FROM embedding_models WHERE name = %s", (name,)).fetchone()
            todo = chunks_to_embed(conn, chunk_set_id, model_row[0], args.limit) if model_row else \
                conn.execute("SELECT chunk_id, content, token_count FROM chunks WHERE chunk_set_id = %s "
                             "LIMIT %s", (chunk_set_id, args.limit)).fetchall()
            n_batches = sum(1 for _ in batches(todo, args.batch_texts, args.batch_tokens))
            print(f"{name} on {args.chunk_set}: {len(todo)} chunks to embed, "
                  f"~{sum(r[2] for r in todo):,} tokens (tiktoken estimate), {n_batches} requests")
            print("dry run: nothing called, nothing written")
            return

        model_id = register_model(conn, name, args.model, args.dimensions, settings)
        todo = chunks_to_embed(conn, chunk_set_id, model_id, args.limit)
        too_long = [r[0] for r in todo if r[2] > MODEL_CONTEXT]
        if too_long:
            raise SystemExit(f"{len(too_long)} chunks exceed the model's {MODEL_CONTEXT}-token input limit")
        print(f"{name} on {args.chunk_set} (chunk_set_id {chunk_set_id}): {len(todo)} chunks to embed")

        started, done, used = time.time(), 0, 0
        for batch in batches(todo, args.batch_texts, args.batch_tokens):
            vectors, tokens = voyage_embed([r[1] for r in batch], args.model, args.dimensions, "document")
            store(conn, model_id, chunk_set_id, batch, vectors, args.dimensions)
            done, used = done + len(batch), used + tokens
            print(f"  {done}/{len(todo)} chunks, {used:,} tokens")

        n_total, n_stale = conn.execute("""
            SELECT (SELECT count(*) FROM chunk_embeddings WHERE model_id = %s AND chunk_set_id = %s),
                   (SELECT count(*) FROM stale_embeddings WHERE model = %s AND chunk_set_id = %s)
        """, (model_id, chunk_set_id, name, chunk_set_id)).fetchone()
        n_chunks = conn.execute("SELECT count(*) FROM chunks WHERE chunk_set_id = %s", (chunk_set_id,)).fetchone()[0]

    print(f"\nembedded {done} chunks, {used:,} tokens (Voyage count), {time.time() - started:.0f}s")
    print(f"vectors for this experiment: {n_total}/{n_chunks} chunks, stale: {n_stale}")


if __name__ == "__main__":
    main()
