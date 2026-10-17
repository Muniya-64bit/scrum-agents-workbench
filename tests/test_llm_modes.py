"""LLM modes: config, record, replay with semantic keys, drift, fallback, round trip."""

import importlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tests.factories import agents_for
from workbench import config
from workbench.agents.base import BaseAgent
from workbench.agents.scrum_master import SprintPlanner
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient, LLMError
from workbench.orchestrator.engine import Orchestrator
from workbench.workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent


class Answer(BaseModel):
    summary: str = ""


class Echo(BaseAgent):
    role = "product_owner"
    output_schema = Answer
    prompt = "prompt v1"

    def build_prompt(self, db, project_id, task):
        return self.prompt

    def mock_output(self, db, project_id, task):
        return {"summary": "from mock"}

    def apply(self, tools, out, task):
        pass


def _fake_model(self, system, user, schema, stats, mock=None):
    """Stands in for `LLMClient._live`: answers from the agent's mock output, costs 10/5 tokens."""
    stats["calls"] += 1
    stats["input_tokens"] += 10
    stats["output_tokens"] += 5
    return schema.model_validate(mock())


def _no_model(self, system, user, schema, stats, mock=None):
    raise AssertionError("the model must not be called in replay")


def _events(db, project_id, kind):
    return [e for e in repo.events_since(db, project_id) if e.kind == kind]


# --- config ----------------------------------------------------------------------------------


@pytest.fixture
def reload_config(monkeypatch):
    """Reload `workbench.config` under a given environment; restore it afterwards."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)

    def load(**env: str | None):
        for name in ("LLM_MODE", "MOCK_LLM", "LLM_SCENARIO_DIR", "LLM_REPLAY_FALLBACK"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            if value is not None:
                monkeypatch.setenv(name, value)
        return importlib.reload(config)

    yield load
    monkeypatch.undo()
    importlib.reload(config)


def test_config_defaults_follow_mock_llm(reload_config):
    cfg = reload_config()
    assert cfg.LLM_MODE == "mock" and cfg.MOCK_LLM is True
    assert cfg.LLM_REPLAY_FALLBACK == "error" and cfg.LLM_SCENARIO_DIR == ""
    cfg = reload_config(MOCK_LLM="0")
    assert cfg.LLM_MODE == "live" and cfg.MOCK_LLM is False


def test_config_llm_mode_wins_over_mock_llm(reload_config):
    cfg = reload_config(LLM_MODE="record", MOCK_LLM="1", LLM_SCENARIO_DIR="x")
    assert cfg.LLM_MODE == "record" and cfg.MOCK_LLM is False and cfg.LLM_SCENARIO_DIR == "x"
    # replay never calls a model, so the DevOps agent must not start docker builds either
    assert reload_config(LLM_MODE="replay").MOCK_LLM is True


def test_config_rejects_unknown_values(reload_config):
    with pytest.raises(ValueError, match="mock, live, record, replay"):
        reload_config(LLM_MODE="turbo")
    with pytest.raises(ValueError, match="error, mock"):
        reload_config(LLM_REPLAY_FALLBACK="ignore")


def test_client_mode_resolution(reload_config):
    assert LLMClient(mock=True).mode == "mock" and LLMClient(mock=True).mock is True
    assert LLMClient(mock=False).mode == "live"
    assert LLMClient(mode="replay").mock is False
    with pytest.raises(ValueError, match="allowed values"):
        LLMClient(mode="nope")


def test_mock_mode_without_a_mock_callable_builds_the_defaults():
    assert LLMClient(mock=True).complete_json("s", "u", Answer) == Answer()


# --- keys ------------------------------------------------------------------------------------


def test_key_format(db: Session):
    p = repo.create_project(db, "x", "y")
    agent = Echo(LLMClient(mock=True))
    assert agent.llm_key(db, p.id, {}) == "product_owner.Echo.none.s0"
    assert agent.llm_key(db, p.id, {"phase": "backlog"}) == "product_owner.Echo.backlog.s0"
    tools = Tools(db, p.id, "scrum_master")
    tools.create_sprint("goal")
    story = tools.create_story(tools.create_epic("E").id, title="Create an item!")
    assert agent.llm_key(db, p.id, {"phase": "execution", "story_id": story.id}) == (
        "product_owner.Echo.execution.s1.create-an-item")
    assert agent.llm_key(db, p.id, {"phase": "execution", "sprint_number": 4}) == (
        "product_owner.Echo.execution.s4")
    long = tools.create_story(tools.create_epic("E2").id, title="A " * 40)
    key = agent.llm_key(db, p.id, {"story_id": long.id})
    assert key.rsplit(".", 1)[1] == "a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a"[:40].strip("-")
    assert len(key.rsplit(".", 1)[1]) <= 40


def test_handlers_use_their_own_class_name(db: Session):
    p = repo.create_project(db, "x", "y")
    planner = SprintPlanner(LLMClient(mock=True))
    assert planner.llm_key(db, p.id, {"phase": "sprint_planning"}) == (
        "scrum_master.SprintPlanner.sprint_planning.s0")


# --- record ----------------------------------------------------------------------------------


def test_record_writes_numbered_files(db: Session, tmp_path, monkeypatch):
    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    p = repo.create_project(db, "x", "y")
    llm = LLMClient(mode="record", scenario_dir=tmp_path)
    agent = Echo(llm)
    agent.run(db, p.id, {"phase": "backlog"})
    agent.run(db, p.id, {"phase": "backlog"})
    first = json.loads((tmp_path / "calls" / "product_owner.Echo.backlog.s0.1.json").read_text())
    assert first["key"] == "product_owner.Echo.backlog.s0" and first["n"] == 1
    assert first["schema"] == "Answer" and first["output"] == {"summary": "from mock"}
    assert first["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert first["source"] == "recorded" and first["model"] == config.MODEL
    assert len(first["prompt_sha256"]) == 64 and first["recorded_at"].endswith("+00:00")
    assert (tmp_path / "calls" / "product_owner.Echo.backlog.s0.2.json").is_file()
    finished = _events(db, p.id, "agent_finished")[0]
    assert finished.payload["llm_mode"] == "record" and finished.payload["calls"] == 1
    assert "replayed" not in finished.payload and "replay_n" not in finished.payload


def test_record_needs_key_and_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    with pytest.raises(LLMError, match="needs a call key"):
        LLMClient(mode="record", scenario_dir=tmp_path).complete_json(
            "s", "u", Answer, mock=lambda: {})
    with pytest.raises(LLMError, match="LLM_SCENARIO_DIR"):
        LLMClient(mode="record").complete_json("s", "u", Answer, mock=lambda: {}, key="k")


# --- replay ----------------------------------------------------------------------------------


def _record_two(db, tmp_path, monkeypatch):
    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    p = repo.create_project(db, "x", "y")

    counter = iter(range(1, 10))
    original = Echo.mock_output
    monkeypatch.setattr(Echo, "mock_output",
                        lambda self, db, project_id, task: {"summary": f"answer {next(counter)}"})
    agent = Echo(LLMClient(mode="record", scenario_dir=tmp_path))
    agent.run(db, p.id, {"phase": "x"})
    agent.run(db, p.id, {"phase": "x"})
    monkeypatch.setattr(Echo, "mock_output", original)
    return p


def test_replay_serves_in_order_with_recorded_usage(db: Session, tmp_path, monkeypatch):
    _record_two(db, tmp_path, monkeypatch)
    monkeypatch.setattr(LLMClient, "_live", _no_model)
    p = repo.create_project(db, "a", "b")
    llm = LLMClient(mode="replay", scenario_dir=tmp_path)
    agent = Echo(llm)
    assert agent.run(db, p.id, {"phase": "x"}).summary == "answer 1"
    assert agent.run(db, p.id, {"phase": "x"}).summary == "answer 2"
    finished = _events(db, p.id, "agent_finished")
    assert finished[0].payload["llm_mode"] == "replay"
    assert finished[0].payload["calls"] == 1 and finished[0].payload["input_tokens"] == 10
    assert finished[0].payload["output_tokens"] == 5
    assert "replayed" not in finished[0].payload and "replay_drift" not in finished[0].payload
    assert llm.usage["calls"] == 2 and llm.usage["input_tokens"] == 20
    assert "replayed" not in llm.usage
    assert _events(db, p.id, "llm_replay_drift") == []

    llm.reset_replay()
    assert agent.run(db, p.id, {"phase": "x"}).summary == "answer 1"


def test_replay_flags_in_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    LLMClient(mode="record", scenario_dir=tmp_path).complete_json(
        "s", "u", Answer, mock=lambda: {"summary": "r"}, key="k")
    usage: dict = {}
    out = LLMClient(mode="replay", scenario_dir=tmp_path).complete_json(
        "s", "u", Answer, usage=usage, key="k")
    assert out.summary == "r"
    assert usage["replayed"] == 1 and usage["replay_n"] == 1 and "replay_drift" not in usage


def test_replay_miss_names_key_and_number(db: Session, tmp_path):
    p = repo.create_project(db, "a", "b")
    agent = Echo(LLMClient(mode="replay", scenario_dir=tmp_path))
    with pytest.raises(LLMError) as err:
        agent.run(db, p.id, {"phase": "x"})
    text = str(err.value)
    assert "product_owner.Echo.x.s0" in text and "#1" in text
    assert "LLM_MODE=record" in text
    # the failed call is not logged as finished
    assert _events(db, p.id, "agent_finished") == []


def test_replay_fallback_to_mock_is_logged(db: Session, tmp_path):
    p = repo.create_project(db, "a", "b")
    agent = Echo(LLMClient(mode="replay", scenario_dir=tmp_path, fallback="mock"))
    assert agent.run(db, p.id, {"phase": "x"}).summary == "from mock"
    events = _events(db, p.id, "llm_replay_fallback")
    assert len(events) == 1
    assert events[0].payload == {"key": "product_owner.Echo.x.s0", "n": 1}
    assert _events(db, p.id, "agent_finished")[0].payload["calls"] == 0


def test_replay_fallback_error_without_mock_callable(tmp_path):
    llm = LLMClient(mode="replay", scenario_dir=tmp_path, fallback="mock")
    with pytest.raises(LLMError, match="No recorded response"):
        llm.complete_json("s", "u", Answer, key="k")


def test_replay_drift_is_served_and_reported(db: Session, tmp_path, monkeypatch):
    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    p = repo.create_project(db, "a", "b")
    Echo(LLMClient(mode="record", scenario_dir=tmp_path)).run(db, p.id, {"phase": "x"})

    monkeypatch.setattr(Echo, "prompt", "prompt v2")
    out = Echo(LLMClient(mode="replay", scenario_dir=tmp_path)).run(db, p.id, {"phase": "x"})
    assert out.summary == "from mock"  # the recorded answer is served despite the new prompt
    drift = _events(db, p.id, "llm_replay_drift")
    assert len(drift) == 1 and drift[0].payload["n"] == 1


def test_replay_validates_against_the_schema(tmp_path):
    path = tmp_path / "calls" / "k.1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"key": "k", "n": 1, "output": {"summary": 5}}))
    with pytest.raises(Exception, match="summary"):
        LLMClient(mode="replay", scenario_dir=tmp_path).complete_json(
            "s", "u", Answer, key="k")


# --- round trip ------------------------------------------------------------------------------


def _outcome(db: Session, project_id: int) -> dict:
    events = repo.events_since(db, project_id)
    return {
        "stories": [(s.title, s.status) for s in repo.backlog(db, project_id)],
        "artifacts": dict(sorted(Counter(
            a.kind for a in repo.list_for_project(db, project_id, m.Artifact)).items())),
        "tests": [(e.payload["passed"], e.payload["failed"], e.payload["ok"])
                  for e in events if e.kind == "test_run"],
        "sprints": len(repo.sprints(db, project_id)),
        "releases": [e.payload["version"] for e in events if e.kind == "release_created"],
        "phase": repo.get(db, m.Project, project_id).phase,
    }


def test_record_then_replay_gives_identical_outcomes(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from workbench.db.session import init_db, make_engine

    def run(mode: str, workspaces: Path):
        monkeypatch.setattr(config, "WORKSPACES_DIR", str(workspaces))
        engine = make_engine("sqlite://")
        init_db(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as db:
            project = repo.create_project(db, "Todo application", "A small to-do app")
            Orchestrator(db, agents_for(mode, tmp_path / "scenario")).run_to_end(project.id)
            tagged = [v for v in _outcome(db, project.id)["releases"]
                      if Workspace(project.id)._tag_sha(v)]
            return _outcome(db, project.id), tagged, {
                e.payload["llm_mode"] for e in repo.events_since(db, project.id)
                if e.kind == "agent_finished"}

    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    recorded, tags_a, modes_a = run("record", tmp_path / "ws-a")
    assert modes_a == {"record", "none"}
    assert list((tmp_path / "scenario" / "calls").glob("*.json"))

    monkeypatch.setattr(LLMClient, "_live", _no_model)
    replayed, tags_b, modes_b = run("replay", tmp_path / "ws-b")
    assert modes_b == {"replay", "none"}
    assert replayed == recorded
    assert tags_a == tags_b and tags_a
    assert recorded["stories"] and recorded["tests"] and recorded["releases"]


# --- scenario_keys.py ------------------------------------------------------------------------


def test_scenario_keys_lists_recorded_and_fallback_keys(db: Session, tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import scenario_keys
    finally:
        sys.path.remove(str(ROOT / "scripts"))

    monkeypatch.setattr(LLMClient, "_live", _fake_model)
    p = repo.create_project(db, "a", "b")
    Echo(LLMClient(mode="record", scenario_dir=tmp_path / "sc")).run(db, p.id, {"phase": "x"})
    assert scenario_keys.recorded_keys(tmp_path / "sc") == [
        ("product_owner.Echo.x.s0", 1, "recorded")]

    # a replay run with fallback = mock logs the keys that are not authored yet
    db_file = tmp_path / "run.db"
    from sqlalchemy.orm import sessionmaker

    from workbench.db.session import init_db, make_engine

    engine = make_engine(f"sqlite:///{db_file}")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as run_db:
        q = repo.create_project(run_db, "a", "b")
        agent = Echo(LLMClient(mode="replay", scenario_dir=tmp_path / "sc", fallback="mock"))
        agent.run(run_db, q.id, {"phase": "x"})  # served
        agent.run(run_db, q.id, {"phase": "x"})  # missing -> fallback
        agent.run(run_db, q.id, {"phase": "y"})  # missing -> fallback
    engine.dispose()
    assert scenario_keys.fallback_keys(db_file) == [
        ("product_owner.Echo.x.s0", 2), ("product_owner.Echo.y.s0", 1)]


def test_scenario_keys_cli(tmp_path):
    calls = tmp_path / "sc" / "calls"
    calls.mkdir(parents=True)
    (calls / "a.b.1.json").write_text(json.dumps({"key": "a.b", "n": 1, "source": "scripted"}))
    (calls / "broken.1.json").write_text("{")
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scenario_keys.py"), "--scenario",
         str(tmp_path / "sc"), "--db", str(tmp_path / "missing.db")],
        capture_output=True, text=True, check=False)
    assert done.returncode == 0
    assert "a.b #1  [scripted]" in done.stdout and "unreadable" in done.stdout
    assert "No such database" in done.stderr
