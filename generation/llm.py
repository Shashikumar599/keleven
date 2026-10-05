"""
LLM access behind a provider-agnostic interface.

Callers use `get_llm(provider, model).generate(system, prompt, schema)` and get an `LLMResult` back; they never
touch a provider SDK. Adding another provider (e.g. Claude) means adding one class with the same `generate()`
and registering it in PROVIDERS.

Every request is stateless: the model sees only this request's system instructions and prompt.
"""
import os
import time
from dataclasses import dataclass, field

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.8-flash"     # pinned: a fixed version name, not a "-latest" alias


@dataclass
class LLMResult:
    text: str                       # raw model output
    data: dict | None               # parsed JSON when a schema was given
    provider: str
    model: str                      # what we asked for
    model_version: str              # what the provider says actually answered
    usage: dict = field(default_factory=dict)    # input / output / thinking tokens
    latency_ms: int = 0           # wall time including retries
    attempts: int = 1


class GeminiProvider:
    """Google Gemini via the official google-genai SDK."""
    name = "gemini"
    RETRY_CODES = {429, 500, 503}

    def __init__(self, model=DEFAULT_MODEL):
        from google import genai
        self.model = model
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def generate(self, system, prompt, schema=None, max_output_tokens=16384, attempts=5, thinking_level=None):
        """thinking_level: None = model default (answers); 'low' for quick calls ('minimal' is rejected by 3.8-flash)."""
        from google.genai import errors, types
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json" if schema else None,
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None,
        )
        started = time.perf_counter()
        for attempt in range(attempts):
            try:
                r = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
                break
            except errors.APIError as e:
                if e.code not in self.RETRY_CODES or attempt == attempts - 1:
                    raise
                wait = 2 ** (attempt + 2)
                print(f"  Gemini {e.code}, retrying in {wait}s")
                time.sleep(wait)
        latency_ms = round(1000 * (time.perf_counter() - started))

        data = None
        if schema is not None and r.parsed is not None:
            data = r.parsed.model_dump() if hasattr(r.parsed, "model_dump") else r.parsed
        u = r.usage_metadata
        return LLMResult(
            text=r.text or "", data=data, provider=self.name, model=self.model,
            model_version=r.model_version or self.model,
            usage={"input": u.prompt_token_count, "output": u.candidates_token_count,
                   "thinking": u.thoughts_token_count or 0},
            latency_ms=latency_ms, attempts=attempt + 1,
        )


PROVIDERS = {"gemini": GeminiProvider}


def get_llm(provider=DEFAULT_PROVIDER, model=None):
    cls = PROVIDERS[provider]
    return cls(model) if model else cls()
