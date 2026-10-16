"""The release step: version, notes, tag, trace links, events and the API on top of them."""

import re
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.factories import build_two_sprint_project
from workbench.agents.registry import AGENTS
from workbench.agents.release import ReleaseAgent
from workbench.agents.tools import Tools
from workbench.api.main import app
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.workspace import Workspace

RELEASE = {"name": "release", "phase": "release"}
SECTIONS = ["## Completed stories", "## Fixed bugs", "## Known issues", "## Carried over",
            "## Process used", "## Metrics", "## Commits"]


@pytest.fixture
def released(db: Session) -> m.Project:
    """A project that ran the whole mock flow, so sprint 1 is released as v0.1.0."""
    p = repo.create_project(db, "Todo", "A simple to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    assert p.phase == Phase.DONE
    return p


def events(db: Session, project: m.Project, kind: str) -> list[m.Event]:
    return [e for e in repo.events_since(db, project.id) if e.kind == kind]


def git(ws: Workspace, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=ws.path, capture_output=True, text=True,
                          check=True).stdout.strip()


def test_release_after_a_sprint(db: Session, released: m.Project):
    ws = Workspace(released.id)
    (art,) = [a for a in repo.artifacts(db, released.id, "release")
              if a.name == "Release v0.1.0"]
    assert art.path == "releases/v0.1.0.md"
    files = ws.files()
    assert {"releases/v0.1.0.md", "Dockerfile", "RELEASE_NOTES.md"} <= set(files)
    assert ws.read("releases/v0.1.0.md") == art.content
    assert "v0.1.0" in git(ws, "tag", "--list").split()

    notes = art.content
    positions = [notes.index(heading) for heading in SECTIONS]
    assert positions == sorted(positions)
    assert notes.startswith("# Release v0.1.0 — Todo")
    stories = repo.backlog(db, released.id)
    for story in stories:
        assert story.title in notes.split("## Fixed bugs")[0]
    assert "Sprint 1 goal:" in notes and "- Test-first: off" in notes

    linked = {link.story_id for link, a in repo.trace_links(db, released.id)
              if a.id == art.id and link.relation == "release"}
    assert linked == {s.id for s in stories}

    (event,) = events(db, released, "release_created")
    sprint = repo.current_sprint(db, released.id)
    assert event.payload["version"] == "v0.1.0"
    assert re.fullmatch(r"[0-9a-f]{40}", event.payload["sha"])
    assert event.payload["sha"] == git(ws, "rev-parse", "v0.1.0^{commit}")
    assert event.payload["story_ids"] == sorted(s.id for s in stories)
    assert event.payload["artifact_id"] == art.id and event.payload["sprint_id"] == sprint.id


def test_builder_files_come_from_the_devops_agent(db: Session, released: m.Project):
    names = {a.name for a in repo.artifacts(db, released.id, "release")}
    assert {"Dockerfile", ".github/workflows/ci.yml", "RELEASE_NOTES.md",
            "Release v0.1.0"} <= names


def test_running_the_release_again_creates_nothing(db: Session, released: m.Project):
    before = (len(repo.artifacts(db, released.id)), len(Workspace(released.id).history()))
    AGENTS["devops"].run(db, released.id, RELEASE)
    assert events(db, released, "release_exists")[0].payload == {"version": "v0.1.0"}
    assert len(events(db, released, "release_created")) == 1
    assert (len(repo.artifacts(db, released.id)),
            len(Workspace(released.id).history())) == before


def test_release_agent_logs_its_run_without_usage(db: Session, released: m.Project):
    finished = [e for e in events(db, released, "agent_finished") if e.agent == "devops"]
    mine = [e for e in finished if e.payload["llm_mode"] == "none"]
    assert len(mine) == 1 and mine[0].message == "Released v0.1.0 with 2 stories"
    assert mine[0].payload["calls"] == 0 and mine[0].payload["input_tokens"] == 0


def test_no_sprint_means_no_release(db: Session):
    p = repo.create_project(db, "x", "y")
    ReleaseAgent().run(db, p.id, RELEASE)
    (skipped,) = [e for e in repo.events_since(db, p.id) if e.kind == "release_skipped"]
    assert skipped.payload == {"reason": "no sprint"}
    assert repo.artifacts(db, p.id, "release") == []


def test_second_sprint_is_v0_2_0_with_only_its_own_commits(db: Session, released: m.Project):
    ws = Workspace(released.id)
    po, sm = Tools(db, released.id, "product_owner"), Tools(db, released.id, "scrum_master")
    story = po.create_story(repo.epics(db, released.id)[0].id, title="Extra feature", points=2)
    sprint = sm.create_sprint("S2", 5)
    sm.add_story_to_sprint(sprint.id, story.id)
    for task in (sm.create_task(story.id, "Implement", "developer"),
                 sm.create_task(story.id, "Test", "qa")):
        sm.update_task(task.id, "done")
    sm.log("sprint_planned", "Sprint 2", sprint_id=sprint.id, number=2, story_ids=[story.id],
           committed_points=2, capacity=5, process={"capacity": 5, "test_first": True,
                                                    "guidelines": ["Keep functions small"]})
    ws.write("app/extra.py", "x = 1\n")
    ws.commit("Story #99: Extra feature")

    AGENTS["devops"].run(db, released.id, RELEASE)

    (art,) = [a for a in repo.artifacts(db, released.id, "release") if a.name == "Release v0.2.0"]
    commits = art.content.split("## Commits")[1]
    assert "- Story #99: Extra feature" in commits
    assert "Tests for story" not in commits and "Release v0.1.0" not in commits
    assert "- Test-first: on" in art.content and "Keep functions small" in art.content
    assert {"v0.1.0", "v0.2.0"} <= set(git(ws, "tag", "--list").split())
    created = events(db, released, "release_created")
    assert [e.payload["version"] for e in created] == ["v0.1.0", "v0.2.0"]
    assert created[1].payload["story_ids"] == [story.id]


# --- the API ----------------------------------------------------------------------------------


@pytest.fixture
def api():
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


def test_releases_endpoint(api):
    c, factory = api
    with factory() as db:
        p = repo.create_project(db, "Todo", "A simple to-do app")
        Orchestrator(db, AGENTS).run_to_end(p.id)
        art = [a for a in repo.artifacts(db, p.id, "release") if a.name == "Release v0.1.0"][0]
        sprint = repo.current_sprint(db, p.id)
    body = c.get(f"/projects/{p.id}/releases").json()
    assert len(body) == 1
    assert body[0] | {"created_at": None, "sha": None, "story_ids": None} == {
        "artifact_id": art.id, "version": "v0.1.0", "sprint_id": sprint.id, "sprint_number": 1,
        "created_at": None, "story_ids": None, "sha": None}
    assert len(body[0]["story_ids"]) == 2 and len(body[0]["sha"]) == 40
    assert body[0]["created_at"]


def test_traceability_rows_carry_release_items(api):
    c, factory = api
    with factory() as db:
        p = repo.create_project(db, "Todo", "A simple to-do app")
        Orchestrator(db, AGENTS).run_to_end(p.id)
    rows = c.get(f"/projects/{p.id}/traceability").json()
    assert rows and all(r["release"] for r in rows)
    item = rows[0]["release"][0]
    assert item["kind"] == "release" and item["name"] == "Release v0.1.0"
    assert all(i["name"] != "Release v0.1.0" for i in rows[0]["other"])


def test_process_endpoint_shows_current_and_next(api):
    c, factory = api
    with factory() as db:
        ids = build_two_sprint_project(db)
        s2 = repo.get(db, m.Sprint, ids["sprints"][1])
        repo.update(db, s2, retro={**s2.retro, "process_changes": {
            "capacity": 4, "test_first": True, "reason": "Fewer, better"}})
    body = c.get(f"/projects/{ids['project']}/process").json()
    assert body["current"] == {"capacity": 5, "max_fix_retries": 2, "test_first": False,
                               "guidelines": []}
    assert body["current_sprint_number"] == 2
    assert body["next"]["capacity"] == 4 and body["next"]["test_first"] is True
    assert body["next_changes"] == {"capacity": [5, 4], "test_first": [False, True]}
    assert body["next_reason"] == "Fewer, better"


def test_process_endpoint_without_sprints_is_the_default(api):
    c, factory = api
    with factory() as db:
        p = repo.create_project(db, "x", "y")
    body = c.get(f"/projects/{p.id}/process").json()
    assert body["current_sprint_number"] is None and body["next_changes"] == {}
    assert body["current"] == body["next"]


@pytest.mark.parametrize("path", ["releases", "process"])
def test_unknown_project_is_404(api, path):
    c, _ = api
    assert c.get(f"/projects/999/{path}").status_code == 404
