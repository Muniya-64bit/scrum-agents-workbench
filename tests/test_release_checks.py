"""Release checks: the generated app is started, compared with its contract, timed and scanned."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from tests.test_release_contract import released  # noqa: F401  (a fixture)
from workbench import config, release_checks, staticcheck
from workbench.agents.release import ReleaseAgent, release_notes
from workbench.agents.tools import Tools
from workbench.contract import Endpoint
from workbench.db import models as m
from workbench.db import repo
from workbench.release_checks import Check
from workbench.workspace import Workspace

GOOD_APP = """from fastapi import FastAPI

app = FastAPI()


@app.get("/books")
def books():
    return []


@app.post("/books", status_code=201)
def add():
    return {}
"""


def _app(tmp_path: Path, source: str) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "main.py").write_text(source)
    return tmp_path


def test_a_working_app_starts_serves_its_contract_and_is_timed(tmp_path):
    checks, p95 = release_checks.smoke_test(
        _app(tmp_path, GOOD_APP), [Endpoint("POST", "/books", 201), Endpoint("GET", "/books", 200)])
    assert [(c.name, c.status) for c in checks] == [("starts", "passed"),
                                                    ("serves its contract", "passed")]
    assert p95 is not None and p95 < 1000


def test_an_endpoint_the_app_does_not_serve_is_reported(tmp_path):
    checks, _ = release_checks.smoke_test(
        _app(tmp_path, GOOD_APP), [Endpoint("GET", "/loans", 200), Endpoint("POST", "/books", 201)])
    contract_check = checks[1]
    assert contract_check.status == "failed"
    assert contract_check.detail == "not served: GET /loans"


def test_a_router_prefix_does_not_count_as_missing(tmp_path):
    source = ("from fastapi import APIRouter, FastAPI\nrouter = APIRouter(prefix='/books')\n"
              "@router.get('/')\ndef books(): return []\n"
              "app = FastAPI()\napp.include_router(router)\n")
    checks, _ = release_checks.smoke_test(_app(tmp_path, source), [Endpoint("GET", "/books", 200)])
    assert checks[1].status == "passed"


def test_an_app_that_cannot_start_fails_the_first_check(tmp_path):
    checks, p95 = release_checks.smoke_test(_app(tmp_path, "def f(a=1, b):\n    pass\n"), [])
    assert [(c.name, c.status) for c in checks] == [("starts", "failed")]
    assert p95 is None and "SyntaxError" in checks[0].detail


def test_no_completed_story_means_no_contract_to_check(tmp_path):
    checks, _ = release_checks.smoke_test(_app(tmp_path, GOOD_APP), [])
    assert checks[1] == Check("serves its contract", "skipped", "no completed story has a contract")


def test_an_app_without_list_endpoints_has_no_latency(tmp_path):
    source = ("from fastapi import FastAPI\napp = FastAPI()\n"
              "@app.get('/b/{x}')\ndef g(x: int): ...\n")
    assert release_checks.smoke_test(_app(tmp_path, source), [])[1] is None


# --- non-functional requirements ---------------------------------------------------------------

LATENCY = {"requirement": "The API shall respond quickly",
           "measure": "95% of requests under 300 ms"}
STYLE = {"requirement": "All code shall follow the standards",
         "measure": "100% of lines pass lint"}


def test_a_latency_requirement_is_checked_against_the_measured_p95():
    met, not_met = release_checks.check_nfrs([LATENCY], 120.0)[0], \
        release_checks.check_nfrs([LATENCY], 450.0)[0]
    assert (met.status, met.detail) == ("met", "p95 120 ms against 300 ms")
    assert (not_met.status, not_met.detail) == ("not met", "p95 450 ms against 300 ms")


@pytest.mark.parametrize("measure, limit", [
    ("answered in under 500 milliseconds", "500"),
    ("answered in under 500 ms.", "500"),
    ("every request finishes within 2 seconds", "2000"),
    ("98% of calls take less than 1.5 s", "1500"),
])
def test_a_time_limit_is_read_in_milliseconds_or_seconds(measure, limit):
    (result,) = release_checks.check_nfrs(
        [{"requirement": "The API shall respond fast", "measure": measure}], 100.0)
    assert result.status == "met" and result.detail == f"p95 100 ms against {limit} ms"


def test_a_missing_measurement_says_why_it_cannot_be_checked():
    (result,) = release_checks.check_nfrs([LATENCY], None)
    assert result.status == "unverified"
    assert "no list endpoint" in result.detail


def test_other_requirements_are_reported_as_not_verified():
    (result,) = release_checks.check_nfrs([STYLE], 120.0)
    assert result == Check("All code shall follow the standards", "unverified",
                           "no automatic check for this requirement")


def test_no_requirements_means_no_results():
    assert release_checks.check_nfrs([], 10.0) == []


# --- security ----------------------------------------------------------------------------------


def test_security_findings_name_the_line_and_the_rule():
    source = ("import sqlite3\n\ndef find(name):\n    conn = sqlite3.connect('x')\n"
              "    return conn.execute(f\"SELECT * FROM t WHERE n = '{name}'\")\n\n"
              "PASSWORD = 'hunter2'\nx = eval('1')\n")
    found = staticcheck.security_findings("app/main.py", source)
    codes = {f.split(": ")[1].split()[0] for f in found}
    assert {"S608", "S105", "S307"} <= codes
    assert all(f.startswith("app/main.py line ") for f in found)


def test_clean_code_has_no_security_findings(tmp_path):
    assert staticcheck.security_findings("app/main.py", "x = 1\n") == []
    assert release_checks.security_scan(_app(tmp_path, GOOD_APP)) == []


def test_the_scan_reads_every_app_file(tmp_path):
    ws = _app(tmp_path, GOOD_APP)
    (ws / "app" / "db.py").write_text("PASSWORD = 'hunter2'\n")
    (found,) = release_checks.security_scan(ws)
    assert found.startswith("app/db.py line 1: S105")


def test_a_missing_ruff_skips_the_security_scan(monkeypatch):
    class Gone:
        returncode, stdout, stderr = 1, "", "No module named ruff"

    monkeypatch.setattr(staticcheck.subprocess, "run", lambda *a, **k: Gone())
    assert staticcheck.security_findings("app/main.py", "eval('1')") == []


# --- the release step ----------------------------------------------------------------------------


def test_a_live_release_logs_its_checks_and_puts_them_in_the_notes(
        db: Session, released: m.Project, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "MOCK_LLM", False)  # the checks are for live runs
    sprint = repo.current_sprint(db, released.id)
    ws = Workspace(released.id)
    tools = Tools(db, released.id, "devops")

    checks = ReleaseAgent()._checks(db, released.id, tools, sprint, ws, "v0.1.0")

    names = [c.name for c in checks]
    assert names[0] == "starts" and names[-1] == "security scan"
    assert checks[0].status == "passed"  # the mock app really starts
    logged = [e for e in repo.events_since(db, released.id) if e.kind == "release_check"]
    assert [e.payload["name"] for e in logged] == names
    assert {e.payload["version"] for e in logged} == {"v0.1.0"}
    notes = release_notes(db, released.id, sprint, "v0.1.0", ws, checks)
    assert "## Release checks" in notes and "- starts: passed" in notes
    assert notes.index("## Release checks") < notes.index("## Commits")


def test_a_mock_release_runs_no_checks(db: Session, released: m.Project):  # noqa: F811
    sprint = repo.current_sprint(db, released.id)
    tools = Tools(db, released.id, "devops")
    assert ReleaseAgent()._checks(db, released.id, tools, sprint, Workspace(released.id),
                                  "v0.1.0") == []
    assert not [e for e in repo.events_since(db, released.id) if e.kind == "release_check"]
    notes = release_notes(db, released.id, sprint, "v0.1.0", Workspace(released.id), [])
    assert "## Release checks" not in notes


def test_a_project_without_an_app_skips_the_start_check(db: Session, monkeypatch):
    monkeypatch.setattr(config, "MOCK_LLM", False)
    p = repo.create_project(db, "Empty", "nothing built")
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    checks = ReleaseAgent()._checks(db, p.id, Tools(db, p.id, "devops"), sprint,
                                    Workspace(p.id).init(), "v0.1.0")
    assert (checks[0].name, checks[0].status) == ("starts", "skipped")
    assert checks[-1] == Check("security scan", "passed", "no common security mistakes found")


@pytest.mark.parametrize("status", ["passed", "failed", "skipped", "met", "not met", "unverified"])
def test_check_statuses_are_plain_strings(status):
    assert Check("x", status).status == status


# --- the API --------------------------------------------------------------------------------------


def test_the_api_lists_the_checks_of_every_release(db: Session):
    from fastapi.testclient import TestClient

    from workbench.api.main import app
    from workbench.db.session import get_session

    app.dependency_overrides[get_session] = lambda: db
    try:
        client = TestClient(app)
        p = repo.create_project(db, "Library", "A library")
        assert client.get(f"/projects/{p.id}/release-checks").json() == []
        tools = Tools(db, p.id, "devops")
        tools.log("release_check", "starts: passed", name="starts", status="passed",
                  detail="serves its OpenAPI document", version="v0.1.0", sprint_id=7)
        tools.log("release_check", "security scan: failed", name="security scan",
                  status="failed", detail="1 finding(s)", version="v0.1.0", sprint_id=7)
        rows = client.get(f"/projects/{p.id}/release-checks").json()
        assert [(r["version"], r["name"], r["status"]) for r in rows] == [
            ("v0.1.0", "starts", "passed"), ("v0.1.0", "security scan", "failed")]
        assert client.get("/projects/999/release-checks").status_code == 404
    finally:
        app.dependency_overrides.clear()
