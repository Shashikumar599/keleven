"""
The enhancer (v2): one fast LLM call before retrieval that prepares the question for search. It never answers.

    question --enhance_v1.md, low thinking--> {search_text, sql, assumptions}

- search_text: the question rewritten for search (scaffolding removed, quotes kept), or None
- sql:         one SELECT over the transcript tables, or None
- assumptions: what the SQL counts or matches, or None

The prompt forbids adding anything from the model's memory: the output steers retrieval, and a wrong memory would
pull the search toward the wrong scenes. A failed call returns None; callers then search with the plain question.
"""
from pydantic import BaseModel, Field

from generation.answer import PROMPTS
from generation.llm import get_llm

PROMPT_FILE = "enhance_v1.md"
THINKING_LEVEL = "low"           # lowest level gemini-3.8-flash accepts ("minimal" is rejected); no deep reasoning needed
MAX_OUTPUT_TOKENS = 1024         # the JSON is short; this only guards against a runaway output


class Plan(BaseModel):
    search_text: str | None = Field(description="The question rewritten for search, or null")
    sql: str | None = Field(description="One PostgreSQL SELECT, or null if SQL can't help")
    assumptions: str | None = Field(description="What the SQL counts or matches, or null")


def enhance(question, llm=None):
    """(Plan as dict or None, LLMResult or None). Never raises: a failure means plain search."""
    llm = llm or get_llm()
    try:
        result = llm.generate(system=(PROMPTS / PROMPT_FILE).read_text(), prompt=f"Question: {question}",
                              schema=Plan, max_output_tokens=MAX_OUTPUT_TOKENS, thinking_level=THINKING_LEVEL)
    except Exception as e:
        print(f"  enhancer failed: {type(e).__name__}: {e}")
        return None, None
    return result.data, result


def fix_sql(question, sql, error, llm=None):
    """One retry when the SQL failed: the model sees its query and the database error. Returns (sql or None,
    LLMResult or None)."""
    llm = llm or get_llm()
    prompt = (f"Question: {question}\n\nYour SQL for this question failed.\nSQL: {sql}\nError: {error}\n\n"
              "Return the same output with a corrected SQL query (or sql null if SQL can't answer this).")
    try:
        result = llm.generate(system=(PROMPTS / PROMPT_FILE).read_text(), prompt=prompt, schema=Plan,
                              max_output_tokens=MAX_OUTPUT_TOKENS, thinking_level=THINKING_LEVEL)
    except Exception as e:
        print(f"  SQL fix failed: {type(e).__name__}: {e}")
        return None, None
    return (result.data or {}).get("sql"), result
