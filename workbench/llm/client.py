"""LLM wrapper: JSON-schema validated output, capped retries, usage log, disk cache, mock mode."""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from workbench import config

CACHE_DIR = Path(".cache/llm")


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, mock: bool | None = None, max_retries: int = 2, use_cache: bool = True):
        self.mock = config.MOCK_LLM if mock is None else mock
        self.max_retries = max_retries
        self.use_cache = use_cache
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._client = None

    def complete_json[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        mock: Callable[[], dict] | None = None,
    ) -> T:
        """Return a validated `schema` instance. In mock mode `mock()` supplies the dict."""
        if self.mock:
            if mock is None:
                return schema()  # works for models whose fields all have defaults
            return schema.model_validate(mock())

        raw = f"{config.MODEL}|{system}|{user}|{schema.__name__}"
        key = hashlib.sha256(raw.encode()).hexdigest()
        cached = CACHE_DIR / f"{key}.json"
        if self.use_cache and cached.exists():
            return schema.model_validate_json(cached.read_text())

        prompt = (
            f"{user}\n\nRespond with ONLY a JSON object matching this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        last_err = ""
        for _ in range(self.max_retries + 1):
            retry = f"\n\nPrevious attempt invalid: {last_err}" if last_err else ""
            text = self._call(system, prompt + retry)
            try:
                obj = schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:500]
                continue
            if self.use_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached.write_text(obj.model_dump_json())
            return obj
        raise LLMError(f"No valid output after {self.max_retries + 1} attempts: {last_err}")

    def _call(self, system: str, prompt: str) -> str:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        r = self._client.messages.create(
            model=config.MODEL,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self.usage["calls"] += 1
        self.usage["input_tokens"] += r.usage.input_tokens
        self.usage["output_tokens"] += r.usage.output_tokens
        return "".join(b.text for b in r.content if b.type == "text")


def _extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]
