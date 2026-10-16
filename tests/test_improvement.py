"""The PDCA rows: plan (process used), do, check (with deltas) and act, per sprint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.factories import build_two_sprint_project
from workbench import metrics
from workbench.api.main import app
from workbench.db import repo
from workbench.db.session import Base, get_session


@pytest.fixture
def seeded(db):
    return build_two_sprint_project(db)


def test_rows_show_both_sprints_with_their_process(db, seeded):
    s1, s2 = metrics.improvement_rows(db, seeded["project"])
    assert (s1["sprint_number"], s2["sprint_number"]) == (1, 2)
    assert s1["plan"]["process"]["max_fix_retries"] == 1
    assert s2["plan"]["process"]["max_fix_retries"] == 2
    assert s1["do"] == {"committed_points": 8, "completed_points": 5}
    assert s2["do"] == {"committed_points": 5, "completed_points": 5}
    assert s1["act"] == {"went_well": ["a"], "went_wrong": ["b"], "actions": ["c"],
                         "proposed_changes": {}}


def test_check_values_and_deltas(db, seeded):
    s1, s2 = metrics.improvement_rows(db, seeded["project"])
    assert s1["check"] == {"commitment_reliability": 0.625, "first_pass_yield": 0.333,
                           "test_pass_rate": 0.8, "bugs_reported": 2, "fix_attempts": 2,
                           "est_cost_usd": 0.04}
    assert set(s1["deltas"].values()) == {None}  # nothing to compare sprint 1 with
    assert s2["deltas"] == {"commitment_reliability": 0.375, "first_pass_yield": 0.667,
                            "test_pass_rate": 0.2, "bugs_reported": -2, "fix_attempts": -1,
                            "est_cost_usd": -0.02}


def test_a_retro_without_notes_gives_an_empty_act(db, seeded):
    s2 = repo.sprints(db, seeded["project"])[1]
    repo.update(db, s2, retro={"actions": []})
    row = metrics.improvement_rows(db, seeded["project"])[1]
    assert row["act"]["proposed_changes"] == {} and row["act"]["went_well"] == []


def test_the_process_that_was_changed_is_reported(db, seeded):
    s1, s2 = repo.sprints(db, seeded["project"])
    repo.update(db, s1, retro={**s1.retro, "process_changes": {"capacity": 5, "reason": "r"}})
    row = metrics.improvement_rows(db, seeded["project"])[0]
    assert row["act"]["proposed_changes"] == {"capacity": 5, "reason": "r"}


def test_no_sprints_no_rows(db):
    p = repo.create_project(db, "x", "y")
    assert metrics.improvement_rows(db, p.id) == []


def test_improvement_endpoint(db, seeded):
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
            ids = build_two_sprint_project(session)
        c = TestClient(app)
        rows = c.get(f"/projects/{ids['project']}/improvement").json()
        assert [r["sprint_number"] for r in rows] == [1, 2]
        assert rows[1]["deltas"]["commitment_reliability"] == 0.375
        assert rows[0]["deltas"]["bugs_reported"] is None
        assert set(rows[1]) == {"sprint_number", "plan", "do", "check", "deltas", "act"}
        assert c.get("/projects/999/improvement").status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
