import json

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import repo
from workbench.llm import client as client_module
from workbench.llm.client import LLMClient, LLMError


class Answer(BaseModel):
    summary: str = ""


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module, "CACHE_DIR", tmp_path / "llm-cache")


def _live(monkeypatch, replies: list[str], use_cache: bool = False) -> LLMClient:
    """A live client whose model calls are faked: each reply costs 100 in and 20 out tokens."""
    llm = LLMClient(mock=False, use_cache=use_cache)
    queue = iter(replies)

    def fake_call(system, prompt, stats):
        stats["calls"] += 1
        stats["input_tokens"] += 100
        stats["output_tokens"] += 20
        return next(queue)

    monkeypatch.setattr(llm, "_call", fake_call)
    return llm


def test_usage_is_counted(monkeypatch):
    llm = _live(monkeypatch, [json.dumps({"summary": "ok"})])
    usage: dict = {}
    out = llm.complete_json("sys", "user", Answer, usage=usage)
    assert out.summary == "ok"
    assert usage == {"calls": 1, "input_tokens": 100, "output_tokens": 20, "cache_hits": 0,
                     "invalid_outputs": 0}
    assert llm.usage == usage


def test_invalid_then_valid_counts_both_calls(monkeypatch):
    llm = _live(monkeypatch, ["not json", json.dumps({"summary": "ok"})])
    usage: dict = {}
    llm.complete_json("sys", "user", Answer, usage=usage)
    assert usage["calls"] == 2 and usage["invalid_outputs"] == 1
    assert usage["input_tokens"] == 200


def test_cached_second_call_is_a_cache_hit(monkeypatch):
    llm = _live(monkeypatch, [json.dumps({"summary": "ok"})], use_cache=True)
    llm.complete_json("sys", "user", Answer)
    usage: dict = {}
    out = llm.complete_json("sys", "user", Answer, usage=usage)
    assert out.summary == "ok"
    assert usage["cache_hits"] == 1 and usage["calls"] == 0
    assert llm.usage["calls"] == 1 and llm.usage["cache_hits"] == 1


def test_error_still_merges_usage(monkeypatch):
    llm = _live(monkeypatch, ["bad", "bad", "bad"])
    usage: dict = {}
    with pytest.raises(LLMError):
        llm.complete_json("sys", "user", Answer, usage=usage)
    assert usage["calls"] == 3 and usage["invalid_outputs"] == 3
    assert llm.usage["calls"] == 3


def test_mock_mode_counts_nothing():
    llm = LLMClient(mock=True)
    usage: dict = {}
    llm.complete_json("sys", "user", Answer, mock=lambda: {"summary": "m"}, usage=usage)
    assert usage == {} and llm.usage["calls"] == 0


class Echo(BaseAgent):
    role = "developer"
    output_schema = Answer

    def build_prompt(self, db, project_id, task):
        return "p"

    def mock_output(self, db, project_id, task):
        return {"summary": "done"}

    def apply(self, tools, out, task):
        pass


def test_agent_finished_carries_usage(db: Session, monkeypatch):
    p = repo.create_project(db, "x", "y")
    Echo(LLMClient(mock=True)).run(db, p.id, {"story_id": 7})
    event = [e for e in repo.events_since(db, p.id) if e.kind == "agent_finished"][0]
    assert event.payload["calls"] == 0 and event.payload["llm_mode"] == "mock"
    assert event.payload["duration_ms"] >= 0 and event.payload["story_id"] == 7
    assert event.payload["model"]
    for key in ("input_tokens", "output_tokens", "cache_hits", "invalid_outputs"):
        assert event.payload[key] == 0

    live = _live(monkeypatch, [json.dumps({"summary": "real"})])
    Echo(live).run(db, p.id)
    event = [e for e in repo.events_since(db, p.id) if e.kind == "agent_finished"][-1]
    assert event.payload["calls"] == 1 and event.payload["input_tokens"] == 100
    assert event.payload["output_tokens"] == 20 and event.payload["llm_mode"] == "live"
    assert event.payload["story_id"] is None


def test_new_event_payload_keys(db: Session):
    p = repo.create_project(db, "x", "y")
    tools = Tools(db, p.id, "scrum_master")
    story = tools.create_story(tools.create_epic("E").id, title="S")
    task = tools.create_task(story.id, "Do it", "developer")
    tools.update_task(task.id, "doing")
    bug = tools.report_bug(story.id, "boom")
    by_kind = {e.kind: e for e in repo.events_since(db, p.id)}
    assert by_kind["task_created"].payload == {"task_id": task.id, "story_id": story.id,
                                               "assignee": "developer"}
    assert by_kind["task_updated"].payload == {"task_id": task.id, "status": "doing",
                                               "story_id": story.id}
    assert by_kind["task_updated"].message == "Do it -> doing"
    assert by_kind["bug_reported"].payload == {"bug_id": bug.id, "story_id": story.id}
