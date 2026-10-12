# RAG interview questions: the 20 that come up most

Each question has a plain-English **answer** you can say out loud, a small **example**, the **key points** to hit, and the
**follow-up** an interviewer usually asks next. Stars: ★★★ asked almost everywhere, ★★ common, ★ senior or system-design rounds.

Contents: [Basics](#basics) · [Chunking](#chunking) · [Retrieval](#retrieval) · [Generation](#generation) ·
[Evaluation](#evaluation) · [Production](#production) · [Design question](#answering-a-design-question)

---

## Basics

### 1. What is RAG, and why use it instead of just an LLM or fine-tuning? ★★★
**Answer.** An LLM only knows what it learned in training. It can be out of date, it knows nothing about your private
documents, and it sometimes makes things up. RAG (retrieval-augmented generation) fixes this: when a question arrives, you
first *search* your documents for the relevant passages, then hand those passages to the LLM and ask it to answer from them.
So there are two parts: a **retriever** that finds the text, and a **generator** (the LLM) that writes the answer.

**Example.** Ask a plain LLM "What is our refund policy?" and it guesses. With RAG, the system finds the refund-policy page,
gives it to the model, and the model answers from it and can point to the page.

**Key points**
- RAG gives the model *knowledge*. Fine-tuning changes its *behaviour* (tone, format, skills). They solve different problems and can be combined.
- To update knowledge you re-index documents. No retraining.
- You can show sources, so answers can be checked.

**Follow-up.** When would you fine-tune instead?  *Answer:* when the problem is style, format or a skill, not missing facts.

### 2. Do we still need RAG now that models have huge context windows? ★★★
**Answer.** Yes. A big window lets you paste more text, but it is slow and expensive (you pay for every token on every
question), models are worse at finding a fact buried in the middle of a very long prompt, and most real collections are far
bigger than any window. RAG sends only the few passages that matter.

**Example.** Ten thousand documents will not fit in a prompt, and even if they did, you would pay to send them with every question.

**Key points**
- Long context is fine for small, stable collections (some teams just cache the whole thing).
- RAG also makes it easier to control who can see what, to cite sources and to keep content fresh.

**Follow-up.** How would you decide which one to use?  *Answer:* test both on your own questions and compare accuracy, latency and cost.

### 3. Walk me through how a RAG system works end to end. ★★★
**Answer.** Two phases.
*Preparation (done ahead of time):* load the documents, clean them, split them into chunks, turn each chunk into a vector
(an embedding), and store the vectors with some metadata in a search index.
*Answering (done per question):* turn the question into a vector, find the most similar chunks, optionally re-order them with a better
model, put the best ones into a prompt, let the LLM write the answer, and show the sources.

**Key points**
- Name the settings you can tune: chunk size, embedding model, how many chunks (k), re-ranking, the prompt.
- Say that you would tune retrieval first, because the generator cannot answer from text it never received.

**Follow-up.** Which steps can run in parallel or be cached?  *Answer:* embedding the question and keyword search can run together; embeddings and common answers can be cached.

---

## Chunking

### 4. How do you choose the chunk size and overlap? ★★★
**Answer.** Chunking means cutting documents into pieces before indexing. Small chunks are precise, because each one is about
a single idea, but they can lose the surrounding context. Big chunks keep the context but mix several ideas, so they match less
sharply and fill the prompt with noise. Overlap repeats a little text at the edges so a fact is not cut in half. There is no
perfect size: try a few and **measure** which retrieves the right chunk most often.

**Example.** A chunk of 100 words may contain only the sentence "The deadline is May 5" with no hint of which project it is
about. A chunk of 500 words includes the project name but may also include three unrelated topics.

**Key points**
- Common methods: fixed size, split by paragraph/sentence, split by document structure (headings, tables), semantic splitting (cut where the topic changes).
- Useful tricks: put the document or section title on every chunk; search small chunks but return the larger parent text.
- Match the chunk to the question: short facts want small chunks; "why" questions want a whole section.

**Follow-up.** What goes wrong with chunks that are too large or too small?  *Answer:* too large dilutes the match and wastes space; too small loses context.

---

## Retrieval

### 5. What are embeddings, and how do you pick an embedding model? ★★★
**Answer.** An embedding turns text into a list of numbers so that texts with similar meaning end up close together. Searching
then means "find the vectors nearest to the question's vector". Pick a model by how well it retrieves **on your kind of
text**, not by reputation: check a public benchmark such as MTEB, then test two or three on your own questions. Also consider
languages, maximum input length, vector size (storage and speed) and price.

**Example.** "How do I reset my password?" lands near "Steps to recover your account", even though they share no words.

**Key points**
- Cosine similarity compares the direction of two vectors. If vectors are normalised it equals the dot product.
- If you change the embedding model you must re-embed everything, because the spaces are not compatible.

**Follow-up.** Why not just use the biggest model?  *Answer:* it can be slower, costlier and no better on your data. Measure.

### 6. What is a vector database, and do you always need one? ★★
**Answer.** It stores vectors and finds the nearest ones quickly. Comparing the question against every vector is exact but gets
slow at scale, so databases use **approximate nearest neighbour (ANN)** search: a tiny loss in accuracy for a big gain in speed.
Two common methods are HNSW, a layered graph you walk towards the answer, and IVF, which groups vectors into clusters and only
searches the closest clusters.

**Key points**
- You do not always need a dedicated vector database. A normal database with a vector extension (such as pgvector), a search engine, or even an in-memory index is enough for small and medium collections.
- Choose by size, filtering needs, how often data changes and what you can run.
- Quantisation (storing vectors with fewer bits) shrinks memory with a small accuracy cost.

**Follow-up.** What does HNSW trade off?  *Answer:* more memory and a build step for fast, high-recall search.

### 7. Dense, sparse and hybrid search: what are they and when do you use which? ★★★
**Answer.** *Dense* search uses embeddings and matches **meaning**. *Sparse* search (keyword search such as BM25) matches **exact
words**. Dense handles paraphrases but can miss exact names, codes and rare terms; keyword search is the reverse. **Hybrid**
runs both and merges the two ranked lists, so you get the best of each. Use hybrid when questions contain names, IDs or
technical terms, which is most real data.

**Example.** "error E-4021" is a keyword job; "why does the app crash when I log in" is a meaning job. Real users ask both.

**Key points**
- The usual way to merge is reciprocal rank fusion: each result gets 1 / (60 + its rank) from each list and the scores are added. It needs no score tuning.
- Hybrid costs a second index to maintain.

**Follow-up.** Give a query where each one fails.  *Answer:* dense fails on exact IDs and rare names; keyword fails when the question uses different words than the document.

### 8. Why add a re-ranker, and why a cross-encoder? ★★★
**Answer.** The first search is fast but rough. A re-ranker takes the top 50 or so results and re-scores them more carefully, so
the best few end up first. It uses a **cross-encoder**, which reads the question and the passage *together*, so it is much more
accurate than the first stage (a **bi-encoder**, which embeds the question and the passage separately). It is too slow to
run on the whole collection, so it only runs on the short list.

**Key points**
- Cost: extra latency and compute. Control it by limiting how many candidates you re-rank.
- Prove it helps by checking nDCG or recall before and after.

**Follow-up.** Twenty chunks come back but only five fit in the prompt. How do you choose?  *Answer:* re-rank and keep the top five.

### 9. How do you improve a user's question before searching? ★★
**Answer.** People ask vague or partial questions. Common fixes: **rewrite** it into a clear standalone question (especially in a
chat, where "what about the second one?" needs the earlier turns), **split** a multi-part question into smaller ones, ask
the model for **several paraphrases** and merge the results, or use **HyDE**, where the model writes a pretend answer and you
search with that, because a pretend answer often looks more like the real passages than the question does.

**Key points**
- Every extra model call adds latency, cost and a risk of drifting from what the user meant, so check that each one actually helps.
- If a question is truly ambiguous, ask a clarifying question.

**Follow-up.** Which would you pick with a tight latency budget?  *Answer:* a single cheap rewrite, or none.

### 10. When does basic RAG fail, and how do you fix it? ★★
**Answer.** Plain similarity search returns the few passages closest in meaning. It struggles with questions that need
**counting or totals** ("how many times…"), **complete lists** ("every…"), **combining facts from several documents** (multi-hop),
**relationships** between things, and **filters** on dates or categories. Fixes: use structured queries (SQL) for counts and
filters, metadata filters, a knowledge graph for relationships, or an agent that searches, reads, then searches again. A router
can choose the right tool per question.

**Example.** "Who reports to the manager of the team that shipped project X?" needs two lookups chained together, and one similarity search will not do it.

**Key points**
- Each extra tool adds cost, delay and new failure modes, so add one only when measurements show a failure it fixes.
- Safe model-written queries: read-only access, one statement, a row limit and a time limit.

**Follow-up.** How do you decide whether to add the extra tool?  *Answer:* group the failing questions by type and see which tool would fix the biggest group.

---

## Generation

### 11. How is a RAG prompt different from a normal prompt? ★★★
**Answer.** It includes the retrieved passages and tells the model three things: answer **only from this text**, **cite** where each
claim comes from, and **say "I can't tell from the sources"** when the text does not contain the answer. That last instruction is what
stops it guessing.

**Key points**
- Put the best passages first. Models use the start and the end of a long prompt better than the middle.
- Use a low temperature for factual answers.
- Ask for structured output (answer plus the exact supporting quote) so you can check it automatically.

**Follow-up.** What if two passages contradict each other?  *Answer:* tell the model to say so and prefer the newer or more authoritative one; show both.

### 12. Does RAG stop hallucinations? Why can it still go wrong? ★★★
**Answer.** It reduces them a lot, because the model now has facts to quote and you can check them, but it does not remove them. The
retriever may miss the right passage, so the model fills the gap from memory. It may return irrelevant or conflicting text. Or the model
may ignore or misread what it was given.

**Key points**
- Most "RAG hallucinations" are really retrieval problems, so fix retrieval first.
- Mitigations: a "say you don't know" instruction, checking that every quote really appears in the retrieved text, a faithfulness check, a lower temperature.

**Follow-up.** Which is worse, a weak retriever or a weak generator?  *Answer:* usually the retriever, because no generator can answer from missing text.

---

## Evaluation

### 13. How do you measure retrieval quality? ★★★
**Answer.** Make a set of questions where you know which passages are the right ones, then measure:
- **Recall@k**: was a right passage in the top k results?
- **Precision@k**: what share of the top k are right?
- **MRR**: how high was the *first* right result (1/rank, averaged)?
- **nDCG**: are the right results near the top, counting more relevant ones higher?

For RAG, recall matters most. The model cannot use a passage it never received, while a little noise is tolerable.

**Example.** The right passage at rank 3 gives a reciprocal rank of 1/3 for that question; MRR is the average over all questions.

**Key points**
- MRR only looks at the first hit, so use MAP or nDCG when several passages matter.
- High recall but low precision means the answer is there but buried in noise, so expect distracted answers.

**Follow-up.** When would you favour precision?  *Answer:* when the prompt space is tight or noise visibly hurts answers.

### 14. How do you measure the answer itself? What is faithfulness? ★★★
**Answer.** Three common questions, used by tools such as RAGAS and TruLens:
- **Faithfulness (groundedness):** is every claim in the answer supported by the retrieved text? You split the answer into claims and check each; the supported share is the score.
- **Answer relevance:** does it actually answer the question?
- **Context precision / recall:** did retrieval bring back the right material, and enough of it?

Faithfulness checks the answer against the retrieved text, **not** against the truth. If retrieval fetched the wrong text, a faithful answer can still be wrong.

**Key points**
- Word-overlap scores (BLEU, ROUGE) reward wording, not correctness, so teams use an LLM as a judge, then check the judge against human labels.
- Judge pitfalls: a judge from the same model family tends to favour its own answers; when comparing two answers it can prefer whichever comes first, so swap the order and average.

**Follow-up.** Faithfulness is 0.9 but users complain. Why?  *Answer:* the context itself is wrong or incomplete, so look at context relevance and recall.

### 15. How do you build an evaluation set without labelling thousands of examples? ★★
**Answer.** A few hundred good questions are enough to catch regressions. Collect real questions where you can, and have a model
generate more from your documents (each one then has a known source). Throw out bad ones, **read a sample by hand**, and freeze the
result as a "golden set". Run it after every change so you get before-and-after numbers.

**Key points**
- Include hard types (multi-step, counting, questions with no answer), not only easy facts.
- Keep a separate test portion that you never tune on.
- Save the retrieved passages with every answer so you can trace failures.
- Add real failures from production back into the set.

**Follow-up.** How do you stop generated questions being too easy?  *Answer:* filter and review them, and mix in real user questions.

### 16. Users say about a third of the answers are wrong. How do you find out why? ★★★
**Answer.** First decide for each wrong answer whether it was a **retrieval** failure or a **generation** failure, using the logs. If the
right passage was *not* among the retrieved ones, retrieval failed (chunking, embeddings, keyword search, query rewriting, k). If it *was* there
and the answer ignored or contradicted it, generation failed (prompt, ordering, model). Count each group, fix the bigger one, and
re-run your fixed question set to confirm.

**Key points**
- Also look for outdated or missing documents, ambiguous questions, and cases where the system should have said "I don't know".
- Use recall@k for the retrieval bucket and faithfulness for the generation bucket.

**Follow-up.** How do you avoid fixing one thing and breaking another?  *Answer:* run the full fixed set after every change.

---

## Production

### 17. How do you reduce latency and cost? ★★
**Answer.** Measure where the time goes first (embedding, search, re-ranking, the LLM call). Then: cache embeddings and repeated
answers, run independent steps in parallel, use a smaller model for simple steps such as rewriting, limit how many candidates go to
the re-ranker, send fewer and better passages (shorter prompt), and stream the answer so users see text early.

**Key points**
- The LLM call usually dominates, and its cost grows with input and output length, so sending better, fewer passages helps quality and cost together.
- Be careful with answer caches: they can serve stale results.

**Follow-up.** What would you drop to halve the latency?  *Answer:* the optional steps with the least measured benefit, such as multi-query or re-ranking on easy questions.

### 18. How do you keep the data fresh? ★★
**Answer.** Treat indexing as a pipeline. Detect documents that were added, changed or deleted; re-chunk and re-embed only those;
and version the index so you can roll back. Store dates and sources as metadata so search can filter or prefer recent content.
Remove deleted or replaced documents so they can never be cited.

**Key points**
- Changing the embedding model or chunking means a full rebuild: build the new index alongside the old one, test it, then switch.
- Add a freshness check to your evaluation set.

**Follow-up.** How do you handle a document that must be removed immediately?  *Answer:* delete it from the index and any caches, and verify it no longer appears.

### 19. How do you handle security, privacy and permissions? ★★
**Answer.** Enforce who can see what **when searching**, by filtering on user or team metadata. Never rely on telling the model to hide
something. Remove or mask personal data when documents are ingested, encrypt data, and keep audit logs. Treat retrieved text as
**untrusted**: a document can contain instructions such as "ignore previous instructions" (prompt injection), so keep
instructions separate from content and limit what the model is allowed to do.

**Key points**
- Rate-limit public endpoints and cap spending.
- Give any tool or database the model can use the minimum access it needs.

**Follow-up.** How do you stop one customer's data appearing in another's answers?  *Answer:* a mandatory tenant filter on every search, enforced in code, not in the prompt.

### 20. What advanced RAG variants should I know? ★
**Answer.** Know the name and the problem each one solves:
- **Agentic RAG:** an agent decides what to search for and can search several times.
- **Corrective RAG (CRAG):** grades the retrieved passages and searches again or falls back when they are poor.
- **Self-RAG:** the model decides when to retrieve and critiques its own answer.
- **GraphRAG:** retrieves over a graph of entities and relationships, good for multi-hop questions.
- **Adaptive RAG:** routes easy and hard questions differently.
- **Multimodal RAG:** retrieves images, tables and charts as well as text.
- **CAG (cache-augmented generation):** preloads a small, stable knowledge base into the model's context and caches it.

**Key points.** Tie each variant to a measured failure it fixes, and mention the extra latency and complexity it adds.

**Follow-up.** Which would you try first when multi-step questions fail?  *Answer:* GraphRAG or an agentic loop, after confirming that is where failures are.

---

## Answering a design question

"Design a RAG system for X" is the most common senior-round format. A reliable order:

1. **Clarify first:** who the users are, what kinds of questions, how big the data is, how often it changes, latency and cost limits, who may see what, and how you will know an answer is correct.
2. **Data side:** parse, chunk (justify the size), embed, index (vectors, plus keyword search if exact terms matter), with metadata.
3. **Question side:** rewrite if needed, hybrid search, re-rank, grounded prompt with citations, generate, check.
4. **Evaluation:** a golden question set, retrieval metrics, faithfulness, a regression run after every change, and a way to feed real failures back in.
5. **Production:** latency budget, caching, a freshness pipeline, permissions, monitoring, spending limits, and a fallback when nothing relevant is found.
6. **Add extras only when the numbers demand it** (SQL, graphs, agents), not up front.

---

## Sources

- [40 RAG Interview Questions and Answers, Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/02/rag-interview-questions-and-answers/)
- [Top RAG Interview Questions and Answers, DataCamp](https://www.datacamp.com/blog/rag-interview-questions)
- [RAG Interview Questions and Answers Hub, KalyanKS-NLP on GitHub](https://github.com/KalyanKS-NLP/RAG-Interview-Questions-and-Answers-Hub)
- [What RAG evaluation interviews test beyond recall@k, techinterview.org](https://www.techinterview.org/rag-evaluation-interview-questions/)
- [40 Generative AI Interview Questions That Actually Get Asked in 2026, Towards AI](https://pub.towardsai.net/40-generative-ai-interview-questions-that-actually-get-asked-in-2026-with-answers-b4c647f1e2e8)
- [Evaluating RAG: interview questions and answers, Medium](https://skphd.medium.com/evaluating-rag-interview-questions-and-answers-df52559d55c1)
