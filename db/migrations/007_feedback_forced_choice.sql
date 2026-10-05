-- Dev-mode preference is a forced choice between the two answers: RAG or LLM.
-- 'both_good' / 'both_bad' are removed: an easy middle option gets picked too often and hides the comparison.
-- Feedback stays optional, so someone who likes neither answer simply doesn't vote (or leaves a comment).
-- The page shows RAG and LLM in random positions so voting isn't biased towards one side (nothing recorded).

ALTER TABLE qa_feedback DROP CONSTRAINT IF EXISTS qa_feedback_preferred_check;
ALTER TABLE qa_feedback ADD CONSTRAINT qa_feedback_preferred_check CHECK (preferred IN ('rag', 'llm'));

