"""The sprint loop: after a release the orchestrator plans another sprint while work is left."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import config
from workbench.agents.base import BaseAgent
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.api.main import app
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.orchestrator.engine import MAX_STEPS, Orchestrator, Phase
from workbench.schemas import BacklogOutput


def backlog_po(count: int, points: int = 2) -> BaseAgent:
    """A Product Owner double that writes `count` small stories."""

    class BigPO(BaseAgent):
        role = "product_owner"
        output_schema = BacklogOutput

        def run(self, db, project_id, task=None):
            """Writes the backlog once; in sprint planning (refinement) it does nothing."""
            if (task or {}).get("phase") == "sprint_planning":
                return BacklogOutput(summary="nothing to refine", vision="", epics=[])
            return super().run(db, project_id, task)

        def build_prompt(self, db, project_id, task):
            return "idea"

        def mock_output(self, db, project_id, task):
            stories = [{"title": f"Feature {i}", "as_a": "user", "i_want": f"feature {i}",
                        "so_that": "it works", "points": points, "priority": 1,
                        "acceptance_criteria": ["Given a When b Then c", "Given d When e Then f"]}
                       for i in range(1, count + 1)]
            return {"vision": "v", "epics": [{"title": "Core", "stories": stories}]}

        def apply(self, tools: Tools, out, task):
            for epic in out.epics:
                e = tools.create_epic(epic.title)
                for s in epic.stories:
                    tools.create_story(e.id, **s.model_dump())

    return BigPO()


def run_project(db: Session, count: int) -> m.Project:
    p = repo.create_project(db, "Todo", "A to-do app")
    Orchestrator(db, {**AGENTS, "product_owner": backlog_po(count)}).run_to_end(p.id)
    return p


def phases(db: Session, project: m.Project) -> list[str]:
    return [e.message for e in repo.events_since(db, project.id) if e.kind == "phase_started"]


@pytest.fixture(autouse=True)
def small_sprints(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_CAPACITY", 5)
    monkeypatch.setattr(config, "MAX_SPRINTS", 3)


def test_runs_sprint_after_sprint_until_the_backlog_is_empty(db: Session):
    p = run_project(db, 3)  # 2 points each, 5 per sprint: two sprints
    assert p.phase == Phase.DONE
    sprints = repo.sprints(db, p.id)
    assert [len(s.stories) for s in sprints] == [2, 1]
    assert repo.unplanned_stories(db, p.id) == []
    assert all(repo.story_is_done(s) for sp in sprints for s in sp.stories)
    one_sprint = ["sprint_planning", "execution", "review", "retro", "release"]
    assert phases(db, p) == ["backlog", *one_sprint, *one_sprint, "done"]
    versions = [a.name for a in repo.artifacts(db, p.id, "release") if a.name.startswith("Release")]
    assert versions == ["Release v0.1.0", "Release v0.2.0"]
    planned = [e for e in repo.events_since(db, p.id) if e.kind == "sprint_planned"]
    assert [e.payload["number"] for e in planned] == [1, 2]
    assert planned[1].payload["process"]["capacity"] == 5


def test_stops_after_max_sprints_with_work_left(db: Session, monkeypatch):
    monkeypatch.setattr(config, "MAX_SPRINTS", 1)
    p = run_project(db, 4)
    assert p.phase == Phase.DONE
    assert len(repo.sprints(db, p.id)) == 1
    assert len(repo.unplanned_stories(db, p.id)) == 2


def _release_project(db: Session, points: list[int]) -> m.Project:
    p = repo.create_project(db, "x", "y")
    po = Tools(db, p.id, "product_owner")
    epic = po.create_epic("Core")
    for i, pts in enumerate(points):
        po.create_story(epic.id, title=f"S{i}", points=pts)
    repo.update(db, p, phase="release")
    return p


def test_release_goes_to_done_without_stories_left(db: Session):
    p = _release_project(db, [])
    assert Orchestrator(db).next_phase(p) == Phase.DONE


def test_release_goes_back_to_planning_with_stories_left(db: Session):
    p = _release_project(db, [2])
    o = Orchestrator(db)
    assert o.more_sprints(p.id) and o.next_phase(p) == Phase.SPRINT_PLANNING


def test_other_phases_keep_their_order(db: Session):
    p = _release_project(db, [2])
    for phase, expected in [("idea", "backlog"), ("retro", "release"), ("done", None)]:
        repo.update(db, p, phase=phase)
        if expected:
            assert Orchestrator(db).next_phase(p) == Phase(expected)


def test_no_new_sprint_when_no_story_fits(db: Session):
    p = _release_project(db, [13])  # capacity is 5, so no sprint could ever take it
    assert Orchestrator(db).more_sprints(p.id) is False


def test_no_new_sprint_after_max_sprints(db: Session, monkeypatch):
    p = _release_project(db, [2])
    Tools(db, p.id, "scrum_master").create_sprint("S1")
    monkeypatch.setattr(config, "MAX_SPRINTS", 1)
    assert Orchestrator(db).more_sprints(p.id) is False


def test_run_to_end_gives_up_instead_of_looping_forever(db: Session, monkeypatch):
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)  # stub agents: every phase is instant
    monkeypatch.setattr(o, "more_sprints", lambda project_id: True)
    with pytest.raises(RuntimeError, match=str(MAX_STEPS)):
        o.run_to_end(p.id)


def test_the_project_view_says_whether_another_sprint_follows(db: Session):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    try:
        with factory() as session:
            more, last = _release_project(session, [2]), _release_project(session, [])
            execution = _release_project(session, [2])
            repo.update(session, execution, phase="execution")
        c = TestClient(app)
        assert c.get(f"/projects/{more.id}").json()["has_more_sprints"] is True
        assert c.get(f"/projects/{last.id}").json()["has_more_sprints"] is False
        assert c.get(f"/projects/{execution.id}").json()["has_more_sprints"] is False
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
