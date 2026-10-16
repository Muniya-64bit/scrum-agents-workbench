import json

import pytest
from sqlalchemy.orm import Session

from workbench import runner
from workbench.agents.developer import MAX_FIX_RETRIES, DeveloperAgent
from workbench.agents.qa import QAAgent
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.workspace import Workspace

EXECUTION = {"name": "execution", "phase": "execution"}


@pytest.fixture
def project(db: Session) -> m.Project:
    """One sprint story with a developer task and a QA task."""
    p = repo.create_project(db, "Todo", "A simple to-do app")
    t = Tools(db, p.id, "product_owner")
    e = t.create_epic("Core")
    s = t.create_story(e.id, title="Create an item", as_a="user", i_want="to add items",
                       so_that="I track work", priority=1,
                       acceptance_criteria=["Given the app When I add a title Then it is listed",
                                            "Given the app When I add nothing Then I see an error"])
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    repo.update(db, s, sprint_id=sprint.id)
    t.create_task(s.id, "Implement: Create an item", "developer")
    t.create_task(s.id, "Test: Create an item", "qa")
    return p


@pytest.fixture
def coded(db: Session, project: m.Project) -> m.UserStory:
    """The sprint story after the Developer (mock mode) has written its code."""
    DeveloperAgent().run(db, project.id, EXECUTION)
    return repo.backlog(db, project.id)[0]


def _kinds(db: Session, project_id: int) -> list[str]:
    return [e.kind for e in repo.events_since(db, project_id)]


def _fake_llm(monkeypatch, *replies: dict) -> LLMClient:
    llm = LLMClient(mock=False, use_cache=False)
    it = iter(json.dumps(r) for r in replies)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: next(it))
    return llm


def _tests_reply(story: m.UserStory, expected: str) -> dict:
    """A QA reply with one test that passes only if story_N() returns `expected`."""
    body = (f"from app.features import story_{story.id}\n\n\n"
            f"def test_returns_value():\n"
            f"    assert story_{story.id}.story_{story.id}() == {expected!r}\n")
    return {"summary": "tests", "files": [{"path": f"tests/test_story_{story.id}.py",
                                           "content": body}]}


def _fix_reply(story: m.UserStory, returns: str) -> dict:
    return {"summary": "fix", "files": [{
        "path": f"app/features/story_{story.id}.py",
        "content": f"def story_{story.id}() -> str:\n    return {returns!r}\n"}]}


# --- the pytest runner ---------------------------------------------------------------------


def _workspace_with(tmp_path, source: str):
    (tmp_path / "tests").mkdir()
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (tmp_path / "tests" / "test_x.py").write_text(source)
    return tmp_path


def test_runner_reports_passes_and_failures(tmp_path):
    ws = _workspace_with(tmp_path, "def test_a():\n    assert True\n\n"
                                   "def test_b():\n    assert 1 == 2\n")
    result = runner.run_pytest(ws)
    assert result.passed == 1 and not result.ok
    assert [f.test for f in result.failures] == ["tests.test_x.test_b"]
    assert "assert 1 == 2" in result.failures[0].message


def test_runner_all_pass(tmp_path):
    result = runner.run_pytest(_workspace_with(tmp_path, "def test_a():\n    assert True\n"))
    assert result.ok and result.passed == 1


def test_runner_treats_import_errors_as_failures(tmp_path):
    result = runner.run_pytest(_workspace_with(tmp_path, "import not_a_real_module_xyz\n"))
    assert not result.ok and result.failures


def test_runner_treats_no_tests_as_failure(tmp_path):
    result = runner.run_pytest(_workspace_with(tmp_path, "x = 1\n"))
    assert not result.ok and result.failures[0].test == "collection"


def test_runner_enforces_timeout(tmp_path):
    ws = _workspace_with(tmp_path, "import time\n\ndef test_slow():\n    time.sleep(60)\n")
    result = runner.run_pytest(ws, timeout=2)
    assert not result.ok and result.failures[0].test == "timeout"


# --- writing and committing tests ----------------------------------------------------------


def test_writes_tests_from_criteria_and_traces_them(db: Session, project: m.Project,
                                                    coded: m.UserStory):
    QAAgent().run(db, project.id, EXECUTION)
    ws = Workspace(project.id)
    path = f"tests/test_story_{coded.id}.py"
    assert path in ws.files() and "pytest.ini" in ws.files()
    assert ws.read(path).count("def test_criterion_") == 2  # one per acceptance criterion
    assert "Given the app When I add a title Then it is listed" in ws.read(path)
    assert ws.history()[0] == f"Tests for story #{coded.id}: Create an item"
    links = [(link.relation, a.path) for link, a in repo.trace_links(db, project.id)
             if link.story_id == coded.id]
    assert ("test", path) in links and ("code", f"app/features/story_{coded.id}.py") in links


def test_test_runs_leave_no_bytecode_in_the_workspace(db: Session, project: m.Project,
                                                      coded: m.UserStory, monkeypatch):
    """Regression: .pyc files made the Developer crash reading the workspace (seen in CI)."""
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)  # CI does not set it
    QAAgent().run(db, project.id, EXECUTION)
    files = Workspace(project.id).files()
    assert not [f for f in files if "__pycache__" in f or f.endswith(".pyc")]
    assert ".gitignore" in files
    DeveloperAgent().run(db, project.id, {**EXECUTION, "story_id": coded.id})  # still readable


def test_passing_tests_finish_the_qa_task(db: Session, project: m.Project, coded: m.UserStory):
    QAAgent().run(db, project.id, EXECUTION)
    db.refresh(coded)
    qa_task = next(t for t in coded.tasks if t.assignee == "qa")
    assert qa_task.status == "done"
    assert repo.bugs(db, project.id) == []
    run = next(e for e in repo.events_since(db, project.id) if e.kind == "test_run")
    assert run.payload["ok"] is True and run.payload["failed"] == 0


def test_story_without_code_is_skipped_with_no_llm_call(db: Session, project: m.Project,
                                                        monkeypatch):
    llm = _fake_llm(monkeypatch)  # any LLM call would raise StopIteration
    QAAgent(llm).run(db, project.id, EXECUTION)
    assert "tests_skipped" in _kinds(db, project.id)
    assert Workspace(project.id).files() == []


def test_tested_stories_are_not_rewritten(db: Session, project: m.Project, coded: m.UserStory,
                                          monkeypatch):
    QAAgent().run(db, project.id, EXECUTION)
    llm = _fake_llm(monkeypatch)  # a second LLM call would raise StopIteration
    QAAgent(llm).run(db, project.id, EXECUTION)
    assert _kinds(db, project.id).count("tests_committed") == 1


def test_rejects_files_outside_tests_dir(db: Session, project: m.Project, coded: m.UserStory,
                                         monkeypatch):
    bad = {"summary": "s", "files": [
        {"path": "app/main.py", "content": "evil = True\n"},
        {"path": "../escape.py", "content": "x = 1\n"},
        {"path": "tests/notes.txt", "content": "not python\n"}]}
    QAAgent(_fake_llm(monkeypatch, bad)).run(db, project.id, EXECUTION)
    kinds = _kinds(db, project.id)
    assert kinds.count("file_rejected") == 3 and "tests_missing" in kinds
    assert "evil" not in Workspace(project.id).read("app/main.py")


# --- bugs and the Developer retry loop -----------------------------------------------------


def test_failing_tests_file_one_bug_each_without_duplicates(db: Session, project: m.Project,
                                                            coded: m.UserStory, monkeypatch):
    qa = QAAgent(_fake_llm(monkeypatch, _tests_reply(coded, "WRONG")))  # no developer attached
    qa.run(db, project.id, EXECUTION)
    qa.run(db, project.id, EXECUTION)  # second pass reuses the tests and must not duplicate
    bugs = repo.bugs(db, project.id)
    assert len(bugs) == 1 and bugs[0].status == "open" and bugs[0].story_id == coded.id
    assert bugs[0].description.startswith("tests.test_story_")
    assert "WRONG" in bugs[0].description
    db.refresh(coded)
    assert next(t for t in coded.tasks if t.assignee == "qa").status == "testing"


def test_developer_fixes_bug_and_qa_confirms(db: Session, project: m.Project, coded: m.UserStory,
                                             monkeypatch):
    developer = DeveloperAgent(_fake_llm(monkeypatch, _fix_reply(coded, "WRONG")))
    qa_llm = _fake_llm(monkeypatch, _tests_reply(coded, "WRONG"))
    QAAgent(qa_llm, developer=developer).run(db, project.id, EXECUTION)

    (bug,) = repo.bugs(db, project.id)
    assert bug.status == "fixed" and bug.retries == 1
    runs = [e.payload["ok"] for e in repo.events_since(db, project.id) if e.kind == "test_run"]
    assert runs == [False, True]  # failed, the Developer fixed it, passed
    assert "bug_verified" in _kinds(db, project.id)
    assert Workspace(project.id).history()[0].startswith(f"Fix bug #{bug.id}")
    db.refresh(coded)
    assert next(t for t in coded.tasks if t.assignee == "qa").status == "done"


def test_gives_up_after_max_retries(db: Session, project: m.Project, coded: m.UserStory,
                                    monkeypatch):
    """The mock Developer never changes the behaviour, so the bug cannot be fixed."""
    qa_llm = _fake_llm(monkeypatch, _tests_reply(coded, "WRONG"))
    QAAgent(qa_llm, developer=DeveloperAgent()).run(db, project.id, EXECUTION)

    (bug,) = repo.bugs(db, project.id)
    assert bug.status == "open" and bug.retries == MAX_FIX_RETRIES
    kinds = _kinds(db, project.id)
    assert kinds.count("test_run") == MAX_FIX_RETRIES + 1
    assert "bugs_left_open" in kinds and "bug_reopened" in kinds  # claimed fixed, still failing
    db.refresh(coded)
    assert next(t for t in coded.tasks if t.assignee == "qa").status == "testing"


def test_exhausted_bug_is_not_retried_on_a_later_run(db: Session, project: m.Project,
                                                     coded: m.UserStory, monkeypatch):
    qa = QAAgent(_fake_llm(monkeypatch, _tests_reply(coded, "WRONG")),
                 developer=DeveloperAgent())
    qa.run(db, project.id, EXECUTION)
    before = len(Workspace(project.id).history())
    qa.run(db, project.id, EXECUTION)
    assert "tests_skipped" in _kinds(db, project.id)
    assert len(Workspace(project.id).history()) == before


# --- wiring ----------------------------------------------------------------------------------


def test_registered_with_developer_attached():
    qa = AGENTS["qa"]
    assert isinstance(qa, QAAgent) and qa.developer is AGENTS["developer"]


def test_execution_phase_end_to_end(db: Session, project: m.Project):
    Orchestrator(db, AGENTS).run_to_end(project.id)
    assert project.phase == Phase.DONE
    story = repo.backlog(db, project.id)[0]
    assert {t.status for t in story.tasks} == {"done"}
    assert repo.bugs(db, project.id) == []
    ws = Workspace(project.id)
    assert f"tests/test_story_{story.id}.py" in ws.files()
    history = ws.history()
    assert history[0] == "Prepare release"
    assert any(message.startswith("Story #") for message in history)
    assert any(message.startswith("Tests for story #") for message in history)
