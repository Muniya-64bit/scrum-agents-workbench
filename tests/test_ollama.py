"""The Ollama provider: a live call goes to a local server with the schema as `format`."""

import io
import json
import urllib.error

import pytest
from pydantic import BaseModel, ValidationError

from workbench import config
from workbench.llm import client as client_module
from workbench.llm.client import LLMClient, LLMError
from workbench.schemas import StoryOut


class Answer(BaseModel):
    summary: str = ""


@pytest.fixture(autouse=True)
def _ollama(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "OLLAMA_URL", "http://ollama.test:11434")
    monkeypatch.setattr(config, "MODEL", "qwen2.5:14b")
    monkeypatch.setattr(client_module, "CACHE_DIR", tmp_path / "llm-cache")


def _server(monkeypatch, replies):
    """Fake `urlopen`: records the requests, answers with the given chat replies."""
    seen: list[dict] = []
    queue = iter(replies)

    def urlopen(request, timeout):
        seen.append({"url": request.full_url, "body": json.loads(request.data), "timeout": timeout})
        reply = next(queue)
        if isinstance(reply, Exception):
            raise reply
        payload = {"message": {"content": reply}, "prompt_eval_count": 120, "eval_count": 30}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(client_module.urllib.request, "urlopen", urlopen)
    return seen


def test_live_call_posts_schema_and_counts_tokens(monkeypatch):
    seen = _server(monkeypatch, [json.dumps({"summary": "ok"})])
    usage: dict = {}
    out = LLMClient(mock=False, use_cache=False).complete_json("sys", "user", Answer, usage=usage)
    assert out.summary == "ok"
    assert (usage["calls"], usage["input_tokens"], usage["output_tokens"]) == (1, 120, 30)
    req = seen[0]
    assert req["url"] == "http://ollama.test:11434/api/chat"
    assert req["body"]["model"] == "qwen2.5:14b"
    assert req["body"]["stream"] is False
    assert req["body"]["format"] == Answer.model_json_schema()
    assert req["body"]["options"]["num_ctx"] == config.OLLAMA_NUM_CTX
    assert [m["role"] for m in req["body"]["messages"]] == ["system", "user"]


def test_invalid_json_is_retried(monkeypatch):
    seen = _server(monkeypatch, ["not json", json.dumps({"summary": "ok"})])
    usage: dict = {}
    out = LLMClient(mock=False, use_cache=False).complete_json("s", "u", Answer, usage=usage)
    assert out.summary == "ok"
    assert usage["invalid_outputs"] == 1 and len(seen) == 2
    assert "Previous attempt invalid" in seen[1]["body"]["messages"][1]["content"]


def test_unreachable_server_is_an_llm_error(monkeypatch):
    _server(monkeypatch, [urllib.error.URLError("connection refused")])
    with pytest.raises(LLMError, match="Ollama call to http://ollama.test:11434 failed"):
        LLMClient(mock=False, use_cache=False).complete_json("s", "u", Answer)


def test_anthropic_stays_the_default_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: '{"summary": "claude"}')
    assert llm.complete_json("s", "u", Answer).summary == "claude"


def test_a_story_needs_at_least_two_acceptance_criteria():
    story = {"title": "t", "as_a": "u", "i_want": "x", "so_that": "y"}
    StoryOut(**story, acceptance_criteria=["Given a When b Then c", "Given d When e Then f"])
    with pytest.raises(ValidationError):
        StoryOut(**story, acceptance_criteria=["Given a When b Then c"])


def test_a_call_can_use_its_own_model(monkeypatch):
    seen = _server(monkeypatch, [json.dumps({"summary": "a"}), json.dumps({"summary": "b"})])
    llm = LLMClient(mock=False, use_cache=False)
    llm.complete_json("s", "u", Answer, model="qwen2.5-coder:14b")
    llm.complete_json("s", "u", Answer)  # the override does not leak into the next call
    assert [r["body"]["model"] for r in seen] == ["qwen2.5-coder:14b", "qwen2.5:14b"]


def test_model_for_reads_the_role_setting(monkeypatch):
    monkeypatch.setenv("WORKBENCH_MODEL_DEVELOPER", "qwen2.5-coder:14b")
    assert config.model_for("developer") == "qwen2.5-coder:14b"
    assert config.model_for("qa") == config.MODEL
