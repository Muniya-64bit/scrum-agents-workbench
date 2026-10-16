import json

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from workbench.agents.architect import ArchitectAgent, DesignDelta, SystemDesigner
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator
from workbench.schemas import ArchitectureOutput, StoryDesignOut

BACKLOG = {"name": "backlog", "phase": "backlog"}
EXECUTION = {"name": "execution", "phase": "execution"}


@pytest.fixture
def project(db: Session) -> m.Project:
    """A project with two stories; only the first is planned into a sprint."""
    p = repo.create_project(db, "Todo", "A simple to-do app")
    t = Tools(db, p.id, "product_owner")
    e = t.create_epic("Core")
    s1 = t.create_story(e.id, title="Create an item", as_a="user", i_want="to add items",
                        so_that="I track work", priority=1,
                        acceptance_criteria=["Given the app When I add Then it shows"])
    t.create_story(e.id, title="Delete an item", priority=2)
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    repo.update(db, s1, sprint_id=sprint.id)
    return p


def _kinds(db: Session, project_id: int, kind: str) -> list[m.Artifact]:
    return repo.artifacts(db, project_id, kind)


def test_sprint0_writes_overview_diagrams_and_api_spec(db: Session, project: m.Project):
    ArchitectAgent().run(db, project.id, BACKLOG)
    assert len(_kinds(db, project.id, "architecture")) == 1
    diagrams = _kinds(db, project.id, "diagram")
    assert [d.name for d in diagrams] == ["components.mmd", "data-model.mmd", "main-flow.mmd"]
    assert diagrams[1].content.startswith("erDiagram")
    spec = _kinds(db, project.id, "api_spec")[0]
    assert spec.content.startswith("openapi: 3") and spec.path == "docs/design/openapi.yaml"
    assert all(a.created_by == "architect" for a in repo.artifacts(db, project.id))


def test_sprint0_artifacts_are_traced_to_every_story(db: Session, project: m.Project):
    ArchitectAgent().run(db, project.id, BACKLOG)
    links = db.query(m.TraceLink).filter_by(relation="architecture").all()
    assert len(links) == 5 * 2  # 5 artifacts x 2 stories
    assert "artifact_linked" in [e.kind for e in repo.events_since(db, project.id)]


def test_sprint0_prompt_includes_stories_and_criteria(db: Session, project: m.Project):
    prompt = SystemDesigner().build_prompt(db, project.id, BACKLOG)
    assert "Create an item" in prompt and "Given the app When I add Then it shows" in prompt


def test_design_delta_only_for_sprint_stories(db: Session, project: m.Project):
    agent = ArchitectAgent()
    agent.run(db, project.id, BACKLOG)
    agent.run(db, project.id, EXECUTION)
    first = repo.backlog(db, project.id)[0]
    rels = {link.relation for link in db.query(m.TraceLink).filter_by(story_id=first.id)}
    assert {"design", "diagram", "api_spec"} <= rels
    second = repo.backlog(db, project.id)[1]
    assert not db.query(m.TraceLink).filter_by(story_id=second.id, relation="design").count()


def test_design_delta_is_not_repeated(db: Session, project: m.Project):
    agent = ArchitectAgent()
    agent.run(db, project.id, EXECUTION)
    agent.run(db, project.id, EXECUTION)  # second sprint run: nothing new to design
    assert len(_kinds(db, project.id, "design")) == 1
    assert "design_skipped" in [e.kind for e in repo.events_since(db, project.id)]


def test_design_delta_prompt_uses_existing_architecture(db: Session, project: m.Project):
    ArchitectAgent().run(db, project.id, BACKLOG)
    prompt = DesignDelta().build_prompt(db, project.id, EXECUTION)
    assert "Key decisions" in prompt and "Create an item" in prompt
    assert "Delete an item" not in prompt


def test_design_delta_drops_unknown_story_ids(db: Session, project: m.Project, monkeypatch):
    first = repo.backlog(db, project.id)[0]
    reply = json.dumps({"designs": [{"story_id": 999, "notes": "x"},
                                    {"story_id": first.id, "notes": "real"},
                                    {"story_id": first.id, "notes": "duplicate"}]})
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt: reply)
    ArchitectAgent(llm).run(db, project.id, EXECUTION)
    assert [a.content for a in _kinds(db, project.id, "design")] == ["real"]


def test_story_skipped_by_llm_is_logged(db: Session, project: m.Project, monkeypatch):
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt: '{"designs": []}')
    ArchitectAgent(llm).run(db, project.id, EXECUTION)
    assert "design_missing" in [e.kind for e in repo.events_since(db, project.id)]


def test_invalid_mermaid_is_retried(db: Session, project: m.Project, tmp_path, monkeypatch):
    good = SystemDesigner().mock_output(db, project.id, BACKLOG)
    bad = {**good, "diagrams": [{"name": "x", "mermaid": "not a diagram"}]}
    replies = iter([json.dumps(bad), json.dumps(good)])
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt: next(replies))
    ArchitectAgent(llm).run(db, project.id, BACKLOG)
    assert len(_kinds(db, project.id, "diagram")) == 3


def test_mermaid_validation():
    with pytest.raises(ValidationError):
        ArchitectureOutput(overview="o", api_spec="a", diagrams=[{"name": "x", "mermaid": "box"}])
    with pytest.raises(ValidationError):
        ArchitectureOutput(overview="o", api_spec="a", diagrams=[])
    assert StoryDesignOut(story_id=1, notes="n", diagram="  ").diagram == ""


def test_unknown_phase_is_rejected(db: Session, project: m.Project):
    with pytest.raises(ValueError):
        ArchitectAgent().run(db, project.id, {"phase": "release"})


def test_registered_and_runs_in_orchestrator(db: Session):
    assert isinstance(AGENTS["architect"], ArchitectAgent)
    p = repo.create_project(db, "Todo", "A simple to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    assert _kinds(db, p.id, "architecture") and _kinds(db, p.id, "api_spec")
