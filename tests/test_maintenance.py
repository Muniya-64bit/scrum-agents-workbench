"""Maintenance: a problem found after the release becomes a fix story and a maintenance sprint."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import config
from workbench.agents.registry import AGENTS
from workbench.api.main import app
from workbench.api.views import MaintenanceIn
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.orchestrator.engine import MAINTENANCE_EPIC, Orchestrator, Phase


@pytest.fixture
def finished(db: Session, monkeypatch) -> m.Project:
    """A project that ran the whole mock flow in one sprint, so it is at `done`."""
    monkeypatch.setattr(config, "MAX_SPRINTS", 1)
    p = repo.create_project(db, "Todo", "A simple to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    assert p.phase == Phase.DONE and len(repo.sprints(db, p.id)) == 1
    return p


def _request(db: Session, p: m.Project, title: str = "Empty title is accepted",
             description: str = "Creating an item with an empty title returns 201.") -> m.Project:
    return Orchestrator(db, AGENTS).request_maintenance(p.id, title, description)


def test_a_project_that_is_not_finished_takes_no_maintenance_request(db: Session):
    p = repo.create_project(db, "Todo", "A simple to-do app")
    with pytest.raises(RuntimeError, match="finished project"):
        _request(db, p)


def test_a_reported_problem_becomes_a_top_priority_fix_story(db: Session, finished: m.Project):
    _request(db, finished)
    story = [s for s in repo.unplanned_stories(db, finished.id)][0]
    assert story.title == "Fix: Empty title is accepted"
    assert story.epic.title == MAINTENANCE_EPIC and story.priority == 1 and story.points == 2
    assert len(story.acceptance_criteria) == 2
    assert all("Given" in c and "When" in c and "Then" in c for c in story.acceptance_criteria)
    assert "returns 201" in story.i_want
    (event,) = [e for e in repo.events_since(db, finished.id) if e.kind == "maintenance_requested"]
    assert event.payload["story_id"] == story.id and event.agent == "human"
    assert finished.phase == Phase.RELEASE  # the next step plans a sprint


def test_a_maintenance_sprint_is_planned_past_the_sprint_limit(db: Session, finished: m.Project):
    orch = Orchestrator(db, AGENTS)
    assert not orch.more_sprints(finished.id)  # MAX_SPRINTS is 1 and one sprint ran
    _request(db, finished)
    assert orch.more_sprints(finished.id) and orch.maintenance_pending(finished.id)
    assert orch.next_phase(finished) == Phase.SPRINT_PLANNING


def test_the_fix_goes_through_a_whole_sprint_and_the_project_is_done_again(
        db: Session, finished: m.Project):
    _request(db, finished)
    Orchestrator(db, AGENTS).run_to_end(finished.id)
    assert finished.phase == Phase.DONE
    assert len(repo.sprints(db, finished.id)) == 2
    fix = next(s for s in repo.backlog(db, finished.id) if s.epic.title == MAINTENANCE_EPIC)
    assert repo.story_is_done(fix)
    assert [a.name for a in repo.artifacts(db, finished.id, "release")].count("Release v0.2.0") == 1


def test_a_second_request_reuses_the_maintenance_epic(db: Session, finished: m.Project):
    _request(db, finished, "First problem")
    Orchestrator(db, AGENTS).run_to_end(finished.id)
    _request(db, finished, "Second problem")
    epics = [e for e in repo.epics(db, finished.id) if e.title == MAINTENANCE_EPIC]
    assert len(epics) == 1 and len(epics[0].stories) == 2


def test_a_fix_that_never_passes_cannot_loop_forever(db: Session, finished: m.Project):
    """Each request adds one sprint to the limit; after that the project may finish."""
    _request(db, finished)
    orch = Orchestrator(db, AGENTS)
    for n in (2, 3):  # sprints 2 and 3 ran and the fix is still waiting
        repo.add(db, m.Sprint(project_id=finished.id, number=n, goal="G", status="done"))
    assert not orch.more_sprints(finished.id)


def test_the_request_is_validated():
    ok = {"title": "A bug", "description": "It breaks."}
    assert MaintenanceIn(**ok).points == 2
    for bad in ({"title": "ab"}, {"description": "x"}, {"title": "t" * 121}, {"points": 8}):
        with pytest.raises(ValidationError):
            MaintenanceIn(**{**ok, **bad})


# --- the API --------------------------------------------------------------------------------------


@pytest.fixture
def api():
    """A client on a database that its worker threads share."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield TestClient(app), factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_the_api_refuses_a_request_for_an_unfinished_project(api):
    client, factory = api
    with factory() as db:
        p = repo.create_project(db, "Todo", "A simple to-do app")
        pid = p.id
    body = {"title": "A bug", "description": "It breaks"}
    r = client.post(f"/projects/{pid}/maintenance", json=body)
    assert r.status_code == 409 and "finished project" in r.json()["detail"]
    assert client.post("/projects/999/maintenance", json=body).status_code == 404


def test_the_api_takes_a_request_and_offers_the_next_sprint(api, monkeypatch):
    client, factory = api
    monkeypatch.setattr(config, "MAX_SPRINTS", 1)
    with factory() as db:
        pid = repo.create_project(db, "Todo", "A simple to-do app").id
        Orchestrator(db, AGENTS).run_to_end(pid)
    r = client.post(f"/projects/{pid}/maintenance",
                    json={"title": "Empty title is accepted", "description": "It returns 201",
                          "points": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "release" and body["has_more_sprints"] is True
    story = client.get(f"/projects/{pid}/backlog").json()["epics"][-1]["stories"][0]
    assert story["title"] == "Fix: Empty title is accepted" and story["points"] == 3
    assert client.post(f"/projects/{pid}/maintenance", json={"title": "x"}).status_code == 422
