import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.factories import build_two_sprint_project
from workbench.agents.tools import Tools
from workbench.api.main import app
from workbench.db import repo
from workbench.db.session import Base, get_session


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


@pytest.fixture
def seeded(api):
    c, factory = api
    with factory() as db:
        ids = build_two_sprint_project(db)
    return c, factory, ids


def test_project_metrics(seeded):
    c, _, ids = seeded
    r = c.get(f"/projects/{ids['project']}/metrics")
    assert r.status_code == 200
    body = r.json()
    s1, s2 = body["sprints"]
    assert (s1["committed_points"], s1["completed_points"], s1["commitment_reliability"]) == (
        8, 5, 0.625)
    assert (s1["first_pass_yield"], s1["test_pass_rate"], s1["est_cost_usd"]) == (0.333, 0.8, 0.04)
    assert (s2["commitment_reliability"], s2["est_cost_usd"]) == (1.0, 0.02)
    assert body["project"]["total_cost_usd"] == 0.067 and body["project"]["avg_velocity"] == 5.0
    assert body["unattributed"]["est_cost_usd"] == 0.007
    assert len(body["gqm"]) == 4 and body["pricing"]["input_per_mtok"] == 2.0


def test_burndown(seeded):
    c, _, ids = seeded
    body = c.get(f"/sprints/{ids['sprints'][0]}/burndown").json()
    assert [p["remaining"] for p in body["series"]] == [8, 5, 3, 3]
    assert body["committed_points"] == 8 and body["closed"] is True
    assert body["ideal"][0] == {"t": 0.0, "remaining": 8.0}
    assert [p["remaining"] for p in c.get(f"/sprints/{ids['sprints'][1]}/burndown")
            .json()["series"]] == [5, 2, 0, 0]


def test_unknown_ids_return_404(seeded):
    c, _, _ = seeded
    r = c.get("/sprints/999/burndown")
    assert r.status_code == 404 and r.json()["detail"] == "sprint not found"
    assert c.get("/projects/999/metrics").status_code == 404
    assert c.get("/projects/999/traceability").status_code == 404


def test_traceability_details(seeded):
    c, factory, ids = seeded
    with factory() as db:  # a story that was never planned and has no artifacts
        tools = Tools(db, ids["project"], "product_owner")
        epic = repo.epics(db, ids["project"])[0]
        extra = tools.create_story(epic.id, title="E: extra", points=1).id
    rows = {r["story_id"]: r for r in c.get(f"/projects/{ids['project']}/traceability").json()}
    a, cc = rows[ids["stories"]["A"]], rows[ids["stories"]["C"]]
    assert a["complete"] is True and a["test_count"] == 2 and a["ac_count"] == 2
    assert a["last_test_ok"] is True and a["sprint_number"] == 1
    assert a["design"][0]["name"] == "A design" and a["design"][0]["version"] == 1
    assert cc["open_bugs"] == 0 and cc["tests_passed"] == 1 and cc["sprint_number"] == 2
    assert rows[ids["stories"]["B"]]["tests_failed"] == 0  # B's last run passed
    e = rows[extra]
    assert e["complete"] is False and e["last_test_ok"] is None and e["sprint_number"] is None


def test_empty_project_metrics(api):
    c, _ = api
    pid = c.post("/projects", json={"name": "n", "idea": "i"}).json()["id"]
    r = c.get(f"/projects/{pid}/metrics")
    assert r.status_code == 200 and r.json()["sprints"] == []
    assert c.get(f"/projects/{pid}/traceability").json() == []
