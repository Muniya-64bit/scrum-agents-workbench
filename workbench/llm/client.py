"""LLM wrapper: JSON-schema validated output, capped retries, usage log, disk cache, mock mode,
and record/replay of answers keyed by meaning."""

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from workbench import config

CACHE_DIR = Path(".cache/llm")
# Model of the call in progress (one agent role can use another model than the default)
_MODEL: ContextVar[str | None] = ContextVar("llm_model", default=None)


def _model() -> str:
    return _MODEL.get() or config.MODEL


class LLMError(RuntimeError):
    pass


USAGE_KEYS = ("calls", "input_tokens", "output_tokens", "cache_hits", "invalid_outputs")
# Per-call flags of record/replay: added to the caller's `usage` dict, never to the totals
FLAG_KEYS = ("replayed", "replay_drift", "replay_fallback", "replay_n")


class LLMClient:
    """`mode`: mock (canned `mock_output`), live (API + disk cache), record (API, every answer
    saved under a semantic key) or replay (answers read back from that scenario directory).
    `mock=True` forces mock mode; `mock=False` means "not mock" (live, unless the config says
    record or replay)."""

    def __init__(self, mock: bool | None = None, max_retries: int = 2, use_cache: bool = True,
                 mode: str | None = None, scenario_dir: str | Path | None = None,
                 fallback: str | None = None):
        if mode is None:
            if mock:
                mode = "mock"
            elif mock is False:
                mode = config.LLM_MODE if config.LLM_MODE != "mock" else "live"
            else:
                mode = config.LLM_MODE
        if mode not in config.LLM_MODES:
            raise ValueError(f"mode={mode!r} is invalid; allowed values: "
                             f"{', '.join(config.LLM_MODES)}")
        self.mode = mode
        self.max_retries = max_retries
        self.use_cache = use_cache
        directory = scenario_dir or config.LLM_SCENARIO_DIR
        self.scenario_dir = Path(directory) if directory else None
        self.fallback = fallback or config.LLM_REPLAY_FALLBACK
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self._client = None
        self._seen: dict[str, int] = {}

    @property
    def mock(self) -> bool:
        return self.mode == "mock"

    def reset_replay(self) -> None:
        """Forget which calls were already served or recorded (start of a new run)."""
        self._seen.clear()

    def complete_json[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
        mock: Callable[[], dict] | None = None,
        usage: dict | None = None,
        key: str | None = None,
        model: str | None = None,
    ) -> T:
        """Return a validated `schema` instance. In mock mode `mock()` supplies the dict.

        Usage (calls, tokens, cache hits, invalid outputs) is added to `self.usage` and, when
        given, to `usage`, also when the call ends in an error. `key` names the call by meaning
        (see `BaseAgent.llm_key`); record and replay need it. `model` overrides the configured
        model for this call. Replay flags (`replayed`,
        `replay_drift`, `replay_fallback`, `replay_n`) are set in `usage` only."""
        if self.mode == "mock":
            if mock is None:
                return schema()  # works for models whose fields all have defaults
            return schema.model_validate(mock())

        stats: dict = dict.fromkeys(USAGE_KEYS, 0)
        token = _MODEL.set(model)
        try:
            if self.mode == "replay":
                return self._replay(system, user, schema, mock, stats, key)
            if self.mode == "record":
                return self._record(system, user, schema, mock, stats, key)
            return self._complete_live(system, user, schema, stats, mock)
        finally:
            _MODEL.reset(token)
            for k, v in stats.items():
                if k in FLAG_KEYS:
                    if usage is not None:
                        usage[k] = v
                    continue
                self.usage[k] = self.usage.get(k, 0) + v
                if usage is not None:
                    usage[k] = usage.get(k, 0) + v

    # --- record / replay ----------------------------------------------------------------------

    def _slot(self, key: str | None) -> tuple[Path, int]:
        """File of this call and its 1-based number among the calls with the same key."""
        if not key or self.scenario_dir is None:
            raise LLMError(f"LLM mode '{self.mode}' needs a call key and LLM_SCENARIO_DIR")
        n = self._seen.get(key, 0) + 1
        self._seen[key] = n
        return self.scenario_dir / "calls" / f"{key}.{n}.json", n

    def _record[T: BaseModel](self, system: str, user: str, schema: type[T],
                              mock: Callable[[], dict] | None, stats: dict,
                              key: str | None) -> T:
        path, n = self._slot(key)
        tokens_in, tokens_out = stats["input_tokens"], stats["output_tokens"]
        obj = self._live(system, user, schema, stats, mock)
        data = {
            "key": key, "n": n, "schema": schema.__name__,
            "prompt_sha256": _prompt_hash(system, user),
            "output": obj.model_dump(mode="json"),
            "usage": {"input_tokens": stats["input_tokens"] - tokens_in,
                      "output_tokens": stats["output_tokens"] - tokens_out},
            "source": "recorded", "model": _model(),
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return obj

    def _replay[T: BaseModel](self, system: str, user: str, schema: type[T],
                              mock: Callable[[], dict] | None, stats: dict,
                              key: str | None) -> T:
        path, n = self._slot(key)
        stats["replay_n"] = n
        if not path.is_file():
            if self.fallback == "mock" and mock is not None:
                stats["replay_fallback"] = 1
                return schema.model_validate(mock())
            raise LLMError(f"No recorded response for {key} #{n} in {self.scenario_dir}. "
                           "Record it with LLM_MODE=record or author it.")
        data = json.loads(path.read_text(encoding="utf-8"))
        obj = schema.model_validate(data["output"])
        recorded = data.get("usage") or {}
        stats["calls"] += 1
        stats["input_tokens"] += int(recorded.get("input_tokens", 0))
        stats["output_tokens"] += int(recorded.get("output_tokens", 0))
        stats["replayed"] = 1
        recorded_hash = data.get("prompt_sha256")
        if recorded_hash and recorded_hash != _prompt_hash(system, user):
            stats["replay_drift"] = 1
        return obj

    # --- live ---------------------------------------------------------------------------------

    def _complete_live[T: BaseModel](self, system: str, user: str, schema: type[T], stats: dict,
                                     mock: Callable[[], dict] | None = None) -> T:
        raw = f"{_model()}|{system}|{user}|{schema.__name__}"
        key = hashlib.sha256(raw.encode()).hexdigest()
        cached = CACHE_DIR / f"{key}.json"
        if self.use_cache and cached.exists():
            stats["cache_hits"] += 1
            return schema.model_validate_json(cached.read_text())
        obj = self._live(system, user, schema, stats, mock)
        if self.use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_text(obj.model_dump_json())
        return obj

    def _live[T: BaseModel](self, system: str, user: str, schema: type[T], stats: dict,
                            mock: Callable[[], dict] | None = None) -> T:
        """The API call with JSON extraction and validation retries. `mock` is ignored here;
        tests monkeypatch this method to stand in for the model."""
        prompt = (
            f"{user}\n\nRespond with ONLY a JSON object matching this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        last_err = ""
        for _ in range(self.max_retries + 1):
            retry = f"\n\nPrevious attempt invalid: {last_err}" if last_err else ""
            if config.LLM_PROVIDER == "ollama":
                text = self._call_ollama(system, prompt + retry, stats, schema)
            else:
                text = self._call(system, prompt + retry, stats)
            try:
                return schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:500]
                stats["invalid_outputs"] += 1
        raise LLMError(f"No valid output after {self.max_retries + 1} attempts: {last_err}")

    def _call(self, system: str, prompt: str, stats: dict) -> str:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        r = self._client.messages.create(
            model=_model(),
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        stats["calls"] += 1
        stats["input_tokens"] += r.usage.input_tokens
        stats["output_tokens"] += r.usage.output_tokens
        return "".join(b.text for b in r.content if b.type == "text")

    def _call_ollama(self, system: str, prompt: str, stats: dict, schema: type[BaseModel]) -> str:
        """One chat call to a local Ollama server. `format` is the JSON schema, so Ollama only
        produces tokens that fit it and the answer is almost always valid JSON."""
        body = json.dumps({
            "model": _model(),
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {"num_ctx": config.OLLAMA_NUM_CTX, "num_predict": 8000, "temperature": 0.2},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        }).encode()
        request = urllib.request.Request(f"{config.OLLAMA_URL}/api/chat", data=body,
                                         headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=config.OLLAMA_TIMEOUT) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise LLMError(f"Ollama call to {config.OLLAMA_URL} failed ({_model()}): {e}") \
                from e
        stats["calls"] += 1
        stats["input_tokens"] += int(data.get("prompt_eval_count") or 0)
        stats["output_tokens"] += int(data.get("eval_count") or 0)
        return (data.get("message") or {}).get("content", "")


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()


def _extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]
