# The RAG Pipeline

Retrieval-Augmented Generation (RAG) answers a question in two steps: first **retrieve** the pieces of source text
most relevant to the question, then have an LLM **generate** an answer using only those pieces. The model's
answer is grounded in real text it was shown, instead of in what it happens to remember.

Why this matters for The Office: an LLM remembers famous moments, but it gets quotes, speakers, episode numbers and
small details wrong, and it can't tell when it's guessing. With RAG, every answer can point to the exact scene it
came from.

A RAG system has five parts. The first three run once, ahead of time (**indexing**). The last two run for every
question (**querying**).

```
 INDEXING (offline, once)                          QUERYING (per question)

 cleaned lines                                      question
      │                                                 │
      ▼                                                 ▼
 1. Store ──► 2. Chunk ──► 3. Embed & index ──►  4. Retrieve ──► 5. Generate ──► answer + citations
   Postgres     scenes       vectors + text       top-k scenes     Claude
                             index (pgvector)
```

---

## 1. Store

**What it does:** puts the cleaned data somewhere it can be queried, along with its metadata.

**Why it matters:** retrieval quality depends on what you can filter and cite. If the season, episode, scene and
speaker are stored with the text, the system can cite "S2E1, scene 4" and can filter ("only season 3", "only lines
by Dwight").

**In this project:** Postgres with the pgvector extension, so tables, embeddings and (later) graph data live in one
database. Tables: `episodes` (season, episode, title) and `lines` (one row per spoken line, from
`data/processed/lines.parquet`).

---

## 2. Chunk

**What it does:** splits the text into the units that get retrieved. A chunk is what the retriever returns and what
the LLM reads.

**The trade-off:**
- **Too small** (one line): "That's what she said" means nothing without the line before it. Context is lost.
- **Too big** (a whole episode): the one relevant exchange is buried in 300 other lines. The embedding becomes a
  blur of many topics, and you pay to send lots of irrelevant text to the LLM.

**Common strategies:** fixed size (e.g. 500 tokens), fixed size with overlap, split on structure (paragraphs,
sections), or semantic splitting.

**In this project:** one chunk per **scene**. The transcript already marks scene boundaries, and a scene is a
natural unit of meaning (one place, one conversation). Each chunk carries metadata: season, episode, title, scene
number, speakers present, and whether it's a deleted scene. Very long scenes may need to be split, with some overlap.

---

## 3. Embed and index

**What it does:** turns each chunk into a vector (a list of numbers, e.g. 1,024 of them) using an **embedding
model**. Texts with similar meaning end up as vectors that are close together. An **index** makes "find the nearest
vectors" fast, without comparing the question to every chunk.

**Key ideas:**
- **Semantic similarity:** "Michael burns his foot on a George Foreman grill" and "the grill accident episode" share
  few words but end up close together as vectors.
- **Distance metric:** usually cosine similarity, which compares the direction of two vectors.
- **Approximate nearest neighbour (ANN) indexes** (HNSW, IVFFlat in pgvector) trade a little accuracy for a lot of
  speed.
- **The embedding model matters.** Different models give different results, so Phase 1 compares at least two.

**In this project:** embeddings stored in pgvector, plus a Postgres full-text index on the same chunks for keyword
search (see Part 4).

---

## 4. Retrieve

**What it does:** given a question, returns the top-k most relevant chunks (k is often 5–20).

**Two kinds of search:**

| | Vector (semantic) search | Keyword (lexical) search, e.g. BM25 |
|---|---|---|
| Matches | meaning | exact words |
| Good at | paraphrases, vague descriptions ("the episode where they're stuck in a bad hotel") | rare names and exact quotes ("Scott's Tots", "Dundies", "bears, beets, Battlestar Galactica") |
| Weak at | exact rare terms, names, numbers | synonyms and paraphrases |

**Hybrid search** runs both and merges the two rankings, commonly with **Reciprocal Rank Fusion (RRF)**: a chunk
that ranks high in either list scores well. The two methods fail in different ways, so together they catch more.

**Optional refinements:**
- **Re-ranking:** a slower, more accurate model re-scores the top ~50 results and keeps the best few.
- **Metadata filters:** limit the search to a season, speaker or episode when the question names one.
- **Query rewriting:** rephrase the question before searching.

**What retrieval can't do:** counting and aggregate questions ("How many times does Michael say 'that's what she
said'?") need *every* matching line, not the top k. That's why Phase 2 adds SQL.

---

## 5. Generate

**What it does:** sends the question plus the retrieved chunks to the LLM, with instructions to answer **only from
those chunks** and cite them.

**Prompt essentials:**
- Put the retrieved scenes in the prompt, each labelled with its citation (season, episode, scene, title).
- Instruct the model to answer only from the provided scenes and to cite the scene(s) it used.
- Allow "I don't know": if the scenes don't contain the answer, the model should say so rather than fall back on
  memory. This is what separates grounded answers from hallucinations.

**In this project:** Claude via the Anthropic API. Answers include speaker and episode citations, which the
evaluation later checks for correctness (citation correctness is one of the metrics).

---

## Where a RAG system can fail

When an answer is wrong, the cause sits in one of the parts. Finding which one is the point of evaluating each part
separately:

| Symptom | Likely part |
|---|---|
| The right scene exists but was never retrieved | 3 (embedding) or 4 (retrieval): measure **recall@k** |
| The right scene was cut in half or buried in a huge chunk | 2 (chunking) |
| The right scene was retrieved but the answer is still wrong or uncited | 5 (generation) |
| The answer is right but the citation points to the wrong scene | 5 (generation): measure **citation correctness** |
| The question needs counting or aggregation | Not a RAG problem: needs SQL (Phase 2) |
| A wrong speaker or garbled text in the source | 1 (data cleaning, Phase 0) |

## Glossary

- **Chunk:** a unit of text that is retrieved as a whole (here, a scene).
- **Embedding:** a vector representation of text, where similar meanings are close together.
- **Top-k:** the k highest-ranked chunks returned by retrieval.
- **Recall@k:** the share of questions where the correct chunk is among the top k retrieved.
- **BM25:** the standard keyword-ranking formula; it rewards rare words that appear in both the query and the
  chunk.
- **Hybrid search:** combining vector and keyword search results.
- **RRF (Reciprocal Rank Fusion):** a simple way to merge rankings: score = Σ 1 / (60 + rank).
- **Grounding:** making the answer depend on retrieved text rather than the model's memory.
- **Hallucination:** a confident answer that isn't supported by the source.
