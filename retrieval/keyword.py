"""
Keyword retrieval with BM25 (v2).

    chunks table --strip accents, tokenize--> BM25 index (in memory)
    question --same normalization--> words --BM25 scores--> top-k chunks

BM25 scores a chunk by its matching words: rare words (few chunks contain them) count much more than common ones,
repeats add less and less, and long chunks are scaled down. That catches exact quotes and rare names that vector
search dilutes (a 10-token line inside a 355-token chunk).

Tokenizing keeps every word: no stop words (quotes like "That's what she said" are made of them; BM25 already
gives common words almost no weight), one-letter words kept ("I"), no stemming. Accents are stripped on both sides,
so "Beyoncé" in a question matches "Beyonce" in the transcript.

The index is built from Postgres on first use (about a second) and lives in memory only; nothing is written back.
"""
import re
import time
import unicodedata
from functools import lru_cache

import bm25s

from common.db import connect

DEFAULT_CHUNK_SET = "pack_300t_3s_80min"
TOKEN_PATTERN = r"(?u)\b\w+\b"          # bm25s default needs 2+ characters, which drops "I"


def strip_accents(text):
    """é -> e: split letters from their accent marks (Unicode NFKD), then drop the marks."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def tokenize(texts):
    return bm25s.tokenize([strip_accents(t) for t in texts], lower=True, token_pattern=TOKEN_PATTERN,
                          stopwords=None, stemmer=None, show_progress=False)


class KeywordIndex:
    def __init__(self, chunk_set=DEFAULT_CHUNK_SET):
        t0 = time.perf_counter()
        with connect("app") as conn:
            rows = conn.execute("SELECT chunk_id, content FROM chunks_full WHERE chunk_set = %s ORDER BY chunk_id",
                                (chunk_set,)).fetchall()
        self.chunk_set = chunk_set
        self.chunk_ids = [r[0] for r in rows]
        tokens = tokenize([r[1] for r in rows])
        self.vocab = tokens.vocab                  # word -> id, used to look up query words
        self.bm25 = bm25s.BM25()
        self.bm25.index(tokens, show_progress=False)
        self.build_ms = round(1000 * (time.perf_counter() - t0))

    def search(self, question, k=8):
        """[(chunk_id, score)] best first. Words not in the index are ignored; no match at all gives []."""
        words = [w for w in re.findall(TOKEN_PATTERN, strip_accents(question).lower()) if w in self.vocab]
        if not words:
            return []
        ids = [[self.vocab[w] for w in words]]
        docs, scores = self.bm25.retrieve(ids, k=min(k, len(self.chunk_ids)), show_progress=False)
        return [(self.chunk_ids[d], float(s)) for d, s in zip(docs[0], scores[0]) if s > 0]


@lru_cache(maxsize=4)
def get_index(chunk_set=DEFAULT_CHUNK_SET):
    """One index per chunk set, built on first use and kept for the life of the process."""
    return KeywordIndex(chunk_set)
