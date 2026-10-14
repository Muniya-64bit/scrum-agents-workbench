from fastapi.testclient import TestClient

from workbench.api.main import app

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
