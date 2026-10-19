from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.schemas import BacklogOutput


def test_crud_and_backlog_order(db: Session):
    p = repo.create_project(db, "Todo", "a todo app")
    t = Tools(db, p.id, "product_owner")
    e = t.create_epic("Auth")
    t.create_story(e.id, title="low", priority=3)
    t.create_story(e.id, title="high", priority=1)
    assert [s.title for s in repo.backlog(db, p.id)] == ["high", "low"]
    assert len(repo.events_since(db, p.id)) == 3


def test_traceability(db: Session):
    p = repo.create_project(db, "x", "y")
    t = Tools(db, p.id, "qa")
    s = t.create_story(t.create_epic("E").id, title="S")
    t.write_artifact("test", "test_s.py", "assert True", story_id=s.id)
    assert db.query(m.TraceLink).count() == 1


class DemoPO(BaseAgent):
    role = "product_owner"
    output_schema = BacklogOutput

    def build_prompt(self, db, project_id, task):
        return "idea"

    def mock_output(self, db, project_id, task):
        return {"vision": "v", "epics": [{"title": "E", "stories": [
            {"title": "S", "as_a": "u", "i_want": "x", "so_that": "y",
             "acceptance_criteria": ["Given a When b Then c", "Given d When e Then f"]}]}]}

    def apply(self, tools: Tools, out: BaseModel, task):
        for ep in out.epics:
            e = tools.create_epic(ep.title)
            for s in ep.stories:
                tools.create_story(e.id, **s.model_dump())


def test_agent_validates_and_persists(db: Session):
    p = repo.create_project(db, "x", "y")
    DemoPO().run(db, p.id)
    assert [s.title for s in repo.backlog(db, p.id)] == ["S"]


def test_state_machine_gates(db: Session):
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)
    o.step(p.id)  # backlog
    o.step(p.id)  # sprint planning -> gate
    assert p.phase == Phase.SPRINT_PLANNING and p.awaiting_approval
    try:
        o.step(p.id)
        raise AssertionError("should block")
    except RuntimeError:
        pass
    o.approve(p.id)
    o.run_to_end(p.id)
    assert p.phase == Phase.DONE
