"""Export: a Markdown report and a zip of the generated project."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import export
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.api.main import app
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.orchestrator.engine import Orchestrator
from workbench.workspace import Workspace


@pytest.fixture
def done(db: Session) -> m.Project:
    p = repo.create_project(db, "Todo app", "A simple to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    return p


def test_the_report_has_every_section_in_order(db: Session, done: m.Project):
    text = export.report(db, done.id)
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings[:6] == ["Idea", "Vision", "Outcome", "Non-functional requirements", "Backlog",
                            "Sprints"]
    assert {"Releases", "Open bugs"} <= set(headings)
    assert text.startswith("# Todo app: project report")
    assert "A simple to-do app" in text


def test_the_report_lists_the_stories_with_their_criteria_and_status(db: Session, done: m.Project):
    text = export.report(db, done.id)
    for story in repo.backlog(db, done.id):
        assert f"**#{story.id} {story.title}**" in text
        for criterion in story.acceptance_criteria:
            assert f"  - {criterion}" in text
    assert ", done)" in text


def test_the_report_gives_the_numbers_of_the_results_page(db: Session, done: m.Project):
    text = export.report(db, done.id)
    stories = repo.backlog(db, done.id)
    points = sum(s.points for s in stories)
    assert f"- Stories done: {len(stories)} of {len(stories)}" in text
    assert f"- Points delivered: {points} of {points}" in text
    assert "| 1 | " in text and "Retrospective of sprint 1" in text
    assert "- v0.1.0: " in text


def test_a_cell_cannot_break_the_table(db: Session):
    p = repo.create_project(db, "Pipes", "x")
    t = Tools(db, p.id, "product_owner")
    t.set_nfrs([{"category": "product", "requirement": "A | B\nC", "measure": "1 ms"}])
    assert "| NFR-1 | product | A \\| B C | 1 ms |" in export.report(db, p.id)


def test_a_new_project_has_a_report_too(db: Session):
    p = repo.create_project(db, "Fresh", "nothing yet")
    text = export.report(db, p.id)
    assert "- Stories done: 0 of 0" in text and "## Sprints" not in text
    assert text.rstrip().endswith("- None")


def test_open_bugs_are_listed(db: Session, done: m.Project):
    story = repo.backlog(db, done.id)[0]
    bug = Tools(db, done.id, "qa").report_bug(story.id, "tests.x: broken | badly")
    text = export.report(db, done.id)
    assert f"- #{bug.id} (story #{story.id}): tests.x: broken \\| badly" in text


def test_the_archive_holds_the_report_and_the_generated_project(db: Session, done: m.Project):
    ws = Workspace(done.id)
    (ws.path / "library.db").write_bytes(b"data")
    (ws.path / "app" / "__pycache__").mkdir(exist_ok=True)
    (ws.path / "app" / "__pycache__" / "main.pyc").write_bytes(b"x")
    names = zipfile.ZipFile(io.BytesIO(export.archive(db, done.id))).namelist()
    assert names[0] == "PROJECT_REPORT.md"
    assert "project/app/main.py" in names and "project/Dockerfile" in names
    assert any(n.startswith("project/releases/") for n in names)
    assert not [n for n in names if ".git/" in n or n.endswith((".db", ".pyc"))]


def test_the_archive_report_is_the_report(db: Session, done: m.Project):
    z = zipfile.ZipFile(io.BytesIO(export.archive(db, done.id)))
    body = z.read("PROJECT_REPORT.md").decode()
    assert body.splitlines()[0] == "# Todo app: project report"


def test_a_project_without_code_still_exports(db: Session):
    p = repo.create_project(db, "Empty", "x")
    z = zipfile.ZipFile(io.BytesIO(export.archive(db, p.id)))
    assert z.namelist() == ["PROJECT_REPORT.md"]


@pytest.mark.parametrize("name, expected", [("Todo app", "todo-app"), ("  Library / Loans! ",
                                                                       "library-loans"),
                                            ("***", "project-7")])
def test_the_file_name_is_safe(name, expected):
    assert export.filename(m.Project(id=7, name=name, idea="x")) == expected


# --- the API --------------------------------------------------------------------------------------


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


def test_the_api_serves_the_report_and_the_archive(api):
    client, factory = api
    with factory() as db:
        pid = repo.create_project(db, "Todo app", "A simple to-do app").id
        Orchestrator(db, AGENTS).run_to_end(pid)

    report = client.get(f"/projects/{pid}/report")
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/markdown")
    assert report.text.startswith("# Todo app: project report")

    archive = client.get(f"/projects/{pid}/export")
    assert archive.status_code == 200 and archive.headers["content-type"] == "application/zip"
    assert archive.headers["content-disposition"] == 'attachment; filename="todo-app.zip"'
    assert "PROJECT_REPORT.md" in zipfile.ZipFile(io.BytesIO(archive.content)).namelist()


def test_the_api_returns_404_for_an_unknown_project(api):
    client, _ = api
    assert client.get("/projects/999/report").status_code == 404
    assert client.get("/projects/999/export").status_code == 404
