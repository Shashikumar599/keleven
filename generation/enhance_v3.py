"""
The enhancer for pipeline v3: the v2 enhancer plus `graph_sql`. v2's generation/enhance.py is not touched and stays the v2 enhancer.

    question --enhance_v3.md, low thinking--> {search_text, sql, assumptions, graph_sql}

graph_sql is one SELECT over the graph views (migrations 014 to 016). The prompt gets no table schema for the graph beyond those
views and forbids adding anything from memory, as in v2. A failed call returns None; a failed query gets one fix attempt.
"""
from pydantic import BaseModel, Field

from generation.answer import PROMPTS
from generation.enhance import MAX_OUTPUT_TOKENS, THINKING_LEVEL
from generation.llm import get_llm

PROMPT_FILE = "enhance_v3.md"


class Plan3(BaseModel):
    search_text: str | None = Field(description="The question rewritten for search, or null")
    sql: str | None = Field(description="One PostgreSQL SELECT over the transcript tables, or null")
    assumptions: str | None = Field(description="What the SQL and the graph SQL count or match, or null")
    graph_sql: str | None = Field(description="One PostgreSQL SELECT over the graph views, or null")


def enhance3(question, llm=None):
    """(Plan3 as dict or None, LLMResult or None). Never raises: a failure means plain search."""
    llm = llm or get_llm()
    try:
        result = llm.generate(system=(PROMPTS / PROMPT_FILE).read_text(), prompt=f"Question: {question}",
                              schema=Plan3, max_output_tokens=MAX_OUTPUT_TOKENS, thinking_level=THINKING_LEVEL)
    except Exception as e:
        print(f"  enhancer failed: {type(e).__name__}: {e}")
        return None, None
    return result.data, result


def fix_query(question, field, query, error, llm=None):
    """One retry for a failed query: field is "sql" or "graph_sql". Returns (corrected query or None, LLMResult or None)."""
    llm = llm or get_llm()
    prompt = (f"Question: {question}\n\nYour {field} for this question failed.\n{field}: {query}\nError: {error}\n\n"
              f"Return the same output with a corrected {field} (or {field} null if it can't answer this).")
    try:
        result = llm.generate(system=(PROMPTS / PROMPT_FILE).read_text(), prompt=prompt, schema=Plan3,
                              max_output_tokens=MAX_OUTPUT_TOKENS, thinking_level=THINKING_LEVEL)
    except Exception as e:
        print(f"  {field} fix failed: {type(e).__name__}: {e}")
        return None, None
    return (result.data or {}).get(field), result
