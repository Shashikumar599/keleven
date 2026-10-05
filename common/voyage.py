"""Voyage embeddings (keys created in MongoDB Atlas use the ai.mongodb.com endpoint)."""
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://ai.mongodb.com/v1/embeddings"
RETRY_STATUS = {429, 500, 502, 503, 504}


def embed(texts, model, dimensions, input_type, attempts=6):
    """Embed a batch of texts ("document" for chunks, "query" for questions).
    Returns (vectors, tokens_used). Retries with backoff on rate limits and server errors."""
    body = json.dumps({"input": texts, "model": model, "input_type": input_type,
                       "output_dimension": dimensions}).encode()
    req = urllib.request.Request(
        os.environ.get("VOYAGE_API_URL", DEFAULT_URL), data=body, method="POST",
        headers={"Authorization": f"Bearer {os.environ['VOYAGE_API_KEY']}", "Content-Type": "application/json"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.load(r)
            vectors = [d["embedding"] for d in sorted(resp["data"], key=lambda d: d["index"])]
            return vectors, resp["usage"]["total_tokens"]
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == attempts - 1:
                raise SystemExit(f"Voyage error {e.code}: {e.read().decode()[:300]}")
            wait = 2 ** attempt
            print(f"  Voyage {e.code}, retrying in {wait}s")
            time.sleep(wait)


def to_pgvector(vec):
    """A vector as pgvector's text form, e.g. '[0.1,0.2]', for a %s::vector parameter."""
    return "[" + ",".join(map(str, vec)) + "]"
