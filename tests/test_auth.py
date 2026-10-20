"""The optional API token: everything but /health needs it once WORKBENCH_API_TOKEN is set."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import config
from workbench.api.main import app
from workbench.db import repo
from workbench.db.session import Base, get_session

TOKEN = "s3cret-token"


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
    with factory() as db:
        pid = repo.create_project(db, "Todo", "A to-do app").id
    yield TestClient(app), pid
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_without_a_configured_token_nothing_is_checked(api):
    client, pid = api
    assert config.API_TOKEN == ""
    assert client.get("/projects").status_code == 200
    assert client.get(f"/projects/{pid}").status_code == 200


@pytest.fixture
def locked(api, monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", TOKEN)
    return api


def test_a_request_without_the_token_is_refused(locked):
    client, pid = locked
    for path in ("/projects", f"/projects/{pid}", f"/projects/{pid}/report", "/process/model"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json() == {"detail": "A valid API token is required"}
        assert r.headers["www-authenticate"] == "Bearer"


def test_a_wrong_token_is_refused(locked):
    client, _ = locked
    assert client.get("/projects", headers={"authorization": "Bearer nope"}).status_code == 401
    assert client.get("/projects", headers={"authorization": TOKEN[:-1]}).status_code == 401
    assert client.get("/projects?token=nope").status_code == 401


def test_the_bearer_token_is_accepted(locked):
    client, pid = locked
    headers = {"authorization": f"Bearer {TOKEN}"}
    assert client.get("/projects", headers=headers).status_code == 200
    assert client.get(f"/projects/{pid}/report", headers=headers).status_code == 200
    created = client.post("/projects", headers=headers, json={"name": "B", "idea": "x"})
    assert created.status_code == 200


def test_the_token_in_the_query_is_accepted_for_the_event_stream(locked):
    """A browser EventSource cannot send headers."""
    client, pid = locked
    assert client.get(f"/projects/{pid}?token={TOKEN}").status_code == 200


def test_the_health_check_stays_open(locked):
    client, _ = locked
    assert client.get("/health").json() == {"status": "ok"}


def test_a_refused_request_changes_nothing(locked):
    client, pid = locked
    assert client.post("/projects", json={"name": "B", "idea": "x"}).status_code == 401
    assert client.post(f"/projects/{pid}/advance").status_code == 401
    r = client.get("/projects", headers={"authorization": f"Bearer {TOKEN}"})
    assert [p["name"] for p in r.json()] == ["Todo"]
