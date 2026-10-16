import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.registry import AGENTS
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator
from workbench.schemas import BacklogOutput


def test_mock_run_creates_vision_epics_and_stories(db: Session):
    p = repo.create_project(db, "Todo", "A simple to-do app")
    ProductOwnerAgent().run(db, p.id)
    db.refresh(p)
    assert "to-do app" in p.vision
    assert len(repo.list_for_project(db, p.id, m.Epic)) == 1
    stories = repo.backlog(db, p.id)
    assert [s.title for s in stories] == ["Create an item", "Complete an item"]
    assert stories[0].priority == 1 and stories[0].points == 3


def test_acceptance_criteria_are_given_when_then(db: Session):
    p = repo.create_project(db, "x", "y")
    ProductOwnerAgent().run(db, p.id)
    for story in repo.backlog(db, p.id):
        assert story.acceptance_criteria
        for c in story.acceptance_criteria:
            assert c.startswith("Given") and " When " in c and " Then " in c


def test_events_are_logged(db: Session):
    p = repo.create_project(db, "x", "y")
    ProductOwnerAgent().run(db, p.id)
    kinds = [e.kind for e in repo.events_since(db, p.id)]
    assert kinds[0] == "agent_started" and kinds[-1] == "agent_finished"
    assert "vision_set" in kinds and "epic_created" in kinds and "story_created" in kinds


def test_invalid_priority_is_rejected():
    bad = {"vision": "v", "epics": [{"title": "E", "stories": [
        {"title": "S", "as_a": "u", "i_want": "x", "so_that": "y",
         "acceptance_criteria": [], "priority": 9}]}]}
    with pytest.raises(ValidationError):
        BacklogOutput.model_validate(bad)


def test_real_path_validates_and_retries_bad_json(db: Session, tmp_path, monkeypatch):
    """Non-mock path: first reply is garbage, second is valid JSON; the wrapper retries."""
    monkeypatch.setattr("workbench.llm.client.CACHE_DIR", tmp_path)
    replies = iter([
        "not json at all",
        '```json\n{"vision": "V", "epics": [{"title": "E", "stories": []}]}\n```',
    ])
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt: next(replies))
    p = repo.create_project(db, "x", "y")
    ProductOwnerAgent(llm).run(db, p.id)
    db.refresh(p)
    assert p.vision == "V"
    assert [e.title for e in repo.list_for_project(db, p.id, m.Epic)] == ["E"]


def test_registered_and_runs_in_backlog_phase(db: Session):
    assert isinstance(AGENTS["product_owner"], ProductOwnerAgent)
    p = repo.create_project(db, "Todo", "A simple to-do app")
    Orchestrator(db, AGENTS).step(p.id)  # idea -> backlog
    assert len(repo.backlog(db, p.id)) == 2
