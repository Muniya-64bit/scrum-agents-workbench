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


USAGE_KEYS = ("calls", "input_tokens", "output_tokens", "cache_hits", "invalid_outputs")


class LLMClient:
    def __init__(self, mock: bool | None = None, max_retries: int = 2, use_cache: bool = True):
        self.mock = config.MOCK_LLM if mock is None else mock
        self.max_retries = max_retries
        self.use_cache = use_cache
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self._client = None

    def complete_json[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        mock: Callable[[], dict] | None = None,
        usage: dict | None = None,
    ) -> T:
        """Return a validated `schema` instance. In mock mode `mock()` supplies the dict.

        Usage (calls, tokens, cache hits, invalid outputs) is added to `self.usage` and, when
        given, to `usage`, also when the call ends in an error."""
        if self.mock:
            if mock is None:
                return schema()  # works for models whose fields all have defaults
            return schema.model_validate(mock())

        stats = dict.fromkeys(USAGE_KEYS, 0)
        try:
            return self._complete_live(system, user, schema, stats)
        finally:
            for k, v in stats.items():
                self.usage[k] = self.usage.get(k, 0) + v
                if usage is not None:
                    usage[k] = usage.get(k, 0) + v

    def _complete_live[T: BaseModel](self, system: str, user: str, schema: type[T],
                                     stats: dict) -> T:
        raw = f"{config.MODEL}|{system}|{user}|{schema.__name__}"
        key = hashlib.sha256(raw.encode()).hexdigest()
        cached = CACHE_DIR / f"{key}.json"
        if self.use_cache and cached.exists():
            stats["cache_hits"] += 1
            return schema.model_validate_json(cached.read_text())

        prompt = (
            f"{user}\n\nRespond with ONLY a JSON object matching this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        last_err = ""
        for _ in range(self.max_retries + 1):
            retry = f"\n\nPrevious attempt invalid: {last_err}" if last_err else ""
            text = self._call(system, prompt + retry, stats)
            try:
                obj = schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:500]
                stats["invalid_outputs"] += 1
                continue
            if self.use_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached.write_text(obj.model_dump_json())
            return obj
        raise LLMError(f"No valid output after {self.max_retries + 1} attempts: {last_err}")

    def _call(self, system: str, prompt: str, stats: dict) -> str:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        r = self._client.messages.create(
            model=config.MODEL,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        stats["calls"] += 1
        stats["input_tokens"] += r.usage.input_tokens
        stats["output_tokens"] += r.usage.output_tokens
        return "".join(b.text for b in r.content if b.type == "text")


def _extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]
