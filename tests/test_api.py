import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from workbench.agents.tools import Tools
from workbench.api.main import app
from workbench.api.sse import event_stream
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_run_flow():
    with TestClient(app) as c:
        pid = c.post("/projects", json={"name": "n", "idea": "i"}).json()["id"]
        assert c.post(f"/projects/{pid}/advance").json()["phase"] == "backlog"
        c.post(f"/projects/{pid}/advance")
        assert c.post(f"/projects/{pid}/advance").status_code == 409
        c.post(f"/projects/{pid}/approve")
        assert c.get(f"/projects/{pid}/events").json()


@pytest.fixture
def api():
    """TestClient on a private in-memory database, plus its session factory for seeding."""
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


def _seed(factory) -> dict:
    with factory() as db:
        p = repo.create_project(db, "Todo", "a todo app")
        repo.update(db, p, vision="Get things done")
        t = Tools(db, p.id, "product_owner")
        e = t.create_epic("Tasks", "manage todos")
        low = t.create_story(e.id, title="Delete todo", priority=3, points=2)
        high = t.create_story(e.id, title="Add todo", priority=1, points=3,
                              acceptance_criteria=["Given x When y Then z"])
        sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="MVP"))
        repo.update(db, high, sprint_id=sprint.id)
        task = t.create_task(high.id, "Build POST /todos", "developer")
        t.create_task(low.id, "Not in sprint", "developer")
        design = t.write_artifact("api_spec", "openapi.yaml", "paths: {}", story_id=high.id)
        code = t.write_artifact("code", "app.py", "print(1)", story_id=high.id, path="app.py")
        t.write_artifact("test", "test_app.py", "assert 1", story_id=high.id)
        t.write_artifact("release", "notes.md", "v1")
        t.report_bug(high.id, "500 on empty title")
        return {"project": p.id, "high": high.id, "low": low.id, "sprint": sprint.id,
                "task": task.id, "design": design.id, "code": code.id}


def test_list_projects(api):
    c, factory = api
    ids = _seed(factory)
    c.post("/projects", json={"name": "Second", "idea": "x"})
    body = c.get("/projects").json()
    assert [p["name"] for p in body] == ["Todo", "Second"]
    assert body[0]["id"] == ids["project"]


def test_backlog_nests_stories_in_priority_order(api):
    c, factory = api
    ids = _seed(factory)
    body = c.get(f"/projects/{ids['project']}/backlog").json()
    assert body["vision"] == "Get things done"
    stories = body["epics"][0]["stories"]
    assert [s["title"] for s in stories] == ["Add todo", "Delete todo"]
    assert stories[0]["acceptance_criteria"] == ["Given x When y Then z"]
    assert stories[0]["sprint_id"] == ids["sprint"]


def test_sprints_list_and_detail(api):
    c, factory = api
    ids = _seed(factory)
    [s] = c.get(f"/projects/{ids['project']}/sprints").json()
    assert s["goal"] == "MVP" and s["story_ids"] == [ids["high"]] and s["points"] == 3
    detail = c.get(f"/sprints/{ids['sprint']}").json()
    assert [st["title"] for st in detail["stories"]] == ["Add todo"]
    assert [t["title"] for t in detail["tasks"]] == ["Build POST /todos"]


def test_tasks_filter_and_patch(api):
    c, factory = api
    ids = _seed(factory)
    pid = ids["project"]
    assert len(c.get(f"/projects/{pid}/tasks").json()) == 2
    assert len(c.get(f"/projects/{pid}/tasks?sprint_id={ids['sprint']}").json()) == 1

    r = c.patch(f"/tasks/{ids['task']}", json={"status": "doing"})
    assert r.status_code == 200 and r.json()["status"] == "doing"
    assert [t["id"] for t in c.get(f"/projects/{pid}/tasks?status=doing").json()] == [ids["task"]]
    last = c.get(f"/projects/{pid}/events").json()[-1]
    assert last["agent"] == "human" and last["kind"] == "task_updated"

    assert c.patch(f"/tasks/{ids['task']}", json={"status": "bogus"}).status_code == 422
    assert c.patch("/tasks/9999", json={"status": "done"}).status_code == 404


def test_artifacts_list_and_detail(api):
    c, factory = api
    ids = _seed(factory)
    pid = ids["project"]
    listed = c.get(f"/projects/{pid}/artifacts").json()
    assert len(listed) == 4 and "content" not in listed[0]
    assert [a["name"] for a in c.get(f"/projects/{pid}/artifacts?kind=code").json()] == ["app.py"]
    detail = c.get(f"/artifacts/{ids['code']}").json()
    assert detail["content"] == "print(1)" and detail["story_ids"] == [ids["high"]]
    assert c.get("/artifacts/9999").status_code == 404


def test_bugs(api):
    c, factory = api
    ids = _seed(factory)
    [b] = c.get(f"/projects/{ids['project']}/bugs").json()
    assert b["story_id"] == ids["high"] and b["status"] == "open"
    assert c.get(f"/projects/{ids['project']}/bugs?status=fixed").json() == []


def test_traceability_groups_by_kind(api):
    c, factory = api
    ids = _seed(factory)
    rows = c.get(f"/projects/{ids['project']}/traceability").json()
    assert [r["story_id"] for r in rows] == [ids["high"], ids["low"]]
    high, low = rows
    assert [i["artifact_id"] for i in high["design"]] == [ids["design"]]
    assert [i["name"] for i in high["code"]] == ["app.py"]
    assert [i["name"] for i in high["test"]] == ["test_app.py"]
    assert low["design"] == low["code"] == low["test"] == []


def test_new_endpoints_404_for_unknown_project(api):
    c, _ = api
    for path in ["backlog", "sprints", "tasks", "artifacts", "bugs", "traceability", "stream"]:
        assert c.get(f"/projects/9999/{path}").status_code == 404, path
    assert c.get("/sprints/9999").status_code == 404


def test_event_stream_yields_events_after_cursor(api):
    _, factory = api
    ids = _seed(factory)
    with factory() as db:
        events = repo.events_since(db, ids["project"])
    cursor = events[1].id
    checks = iter([False, True])  # one poll, then the client disconnects

    async def is_disconnected():
        return next(checks)

    async def collect():
        gen = event_stream(factory, ids["project"], cursor, is_disconnected, poll_seconds=0)
        return [frame async for frame in gen]

    frames = asyncio.run(collect())
    assert len(frames) == len(events) - 2
    first = frames[0]
    assert first.startswith(f"id: {events[2].id}\ndata: ") and first.endswith("\n\n")
    assert '"kind":"story_created"' in first
