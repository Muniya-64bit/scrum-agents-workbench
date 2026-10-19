import json

import pytest
from sqlalchemy.orm import Session

from workbench.agents.developer import MAX_FIX_RETRIES, DeveloperAgent
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator
from workbench.workspace import UnsafePath, Workspace

EXECUTION = {"name": "execution", "phase": "execution"}


@pytest.fixture
def project(db: Session) -> m.Project:
    """Two stories; only the first is in a sprint, with one developer and one QA task."""
    p = repo.create_project(db, "Todo", "A simple to-do app")
    t = Tools(db, p.id, "product_owner")
    e = t.create_epic("Core")
    s1 = t.create_story(e.id, title="Create an item", as_a="user", i_want="to add items",
                        so_that="I track work", priority=1,
                        acceptance_criteria=["Given the app When I add a title Then it is listed"])
    t.create_story(e.id, title="Delete an item", priority=2)
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    repo.update(db, s1, sprint_id=sprint.id)
    t.create_task(s1.id, "Implement: Create an item", "developer")
    t.create_task(s1.id, "Test: Create an item", "qa")
    return p


def _story(db: Session, project: m.Project, title: str = "Create an item") -> m.UserStory:
    return next(s for s in repo.backlog(db, project.id) if s.title == title)


def _kinds(db: Session, project_id: int) -> list[str]:
    return [e.kind for e in repo.events_since(db, project_id)]


def _fake_llm(monkeypatch, *replies: dict) -> LLMClient:
    """Real (non-mock) client whose API call returns the given JSON replies in order."""
    llm = LLMClient(mock=False, use_cache=False)
    it = iter(json.dumps(r) for r in replies)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: next(it))
    return llm


def test_implements_sprint_story_with_one_commit(db: Session, project: m.Project):
    story = _story(db, project)
    DeveloperAgent().run(db, project.id, EXECUTION)
    ws = Workspace(project.id)
    assert ws.history() == [f"Story #{story.id}: Create an item"]
    assert {"app/main.py", "requirements.txt", f"app/features/story_{story.id}.py"} <= set(
        ws.files())
    assert "Given the app When I add a title" in ws.read(f"app/features/story_{story.id}.py")
    assert "code_committed" in _kinds(db, project.id)


def test_only_sprint_stories_are_built(db: Session, project: m.Project):
    DeveloperAgent().run(db, project.id, EXECUTION)
    other = _story(db, project, "Delete an item")
    assert not db.query(m.TraceLink).filter_by(story_id=other.id).count()


def test_code_artifacts_are_traced_to_the_story(db: Session, project: m.Project):
    story = _story(db, project)
    DeveloperAgent().run(db, project.id, EXECUTION)
    code = repo.artifacts(db, project.id, "code")
    assert code and all(a.created_by == "developer" and a.version == 1 for a in code)
    assert {a.path for a in code} == set(Workspace(project.id).files())
    links = db.query(m.TraceLink).filter_by(story_id=story.id, relation="code").count()
    assert links == len(code)


def test_developer_tasks_done_and_qa_tasks_untouched(db: Session, project: m.Project):
    DeveloperAgent().run(db, project.id, EXECUTION)
    status = {t.assignee: t.status for t in _story(db, project).tasks}
    assert status == {"developer": "done", "qa": "todo"}


def test_second_run_without_bugs_does_nothing(db: Session, project: m.Project):
    agent = DeveloperAgent()
    agent.run(db, project.id, EXECUTION)
    count = len(repo.artifacts(db, project.id, "code"))
    out = agent.run(db, project.id, EXECUTION)
    assert out.summary == "No sprint stories need code"
    assert len(repo.artifacts(db, project.id, "code")) == count
    assert len(Workspace(project.id).history()) == 1
    assert "code_skipped" in _kinds(db, project.id)


def test_qa_bug_triggers_fix_commit(db: Session, project: m.Project):
    story = _story(db, project)
    agent = DeveloperAgent()
    agent.run(db, project.id, EXECUTION)
    bug = Tools(db, project.id, "qa").report_bug(story.id, "Empty title is accepted")
    agent.run(db, project.id, EXECUTION)

    assert Workspace(project.id).history()[0] == (
        f"Fix bug #{bug.id} in story #{story.id}: Create an item")
    db.refresh(bug)
    assert bug.status == "fixed" and bug.retries == 1
    feature = [a for a in repo.artifacts(db, project.id, "code")
               if a.path == f"app/features/story_{story.id}.py"]
    assert [a.version for a in feature] == [1, 2]
    assert "Empty title is accepted" in feature[-1].content
    assert "bug_fixed" in _kinds(db, project.id)


def test_bug_retry_limit_stops_reruns(db: Session, project: m.Project):
    story = _story(db, project)
    agent = DeveloperAgent()
    agent.run(db, project.id, EXECUTION)
    bug = Tools(db, project.id, "qa").report_bug(story.id, "Still broken")
    repo.update(db, bug, retries=MAX_FIX_RETRIES)
    agent.run(db, project.id, EXECUTION)
    assert len(Workspace(project.id).history()) == 1
    kinds = _kinds(db, project.id)
    assert "bug_retry_limit" in kinds and kinds[-1] == "code_skipped"


def test_unchanged_output_is_a_failed_fix_attempt(db: Session, project: m.Project, monkeypatch):
    story = _story(db, project)
    DeveloperAgent().run(db, project.id, EXECUTION)
    bug = Tools(db, project.id, "qa").report_bug(story.id, "Bug")
    main = Workspace(project.id).read("app/main.py")
    llm = _fake_llm(monkeypatch, {"files": [{"path": "app/main.py", "content": main}]})
    DeveloperAgent(llm).run(db, project.id, EXECUTION)
    db.refresh(bug)
    assert bug.status == "open" and bug.retries == 1
    assert {"code_unchanged", "bug_fix_failed"} <= set(_kinds(db, project.id))
    assert len(Workspace(project.id).history()) == 1


def test_unsafe_paths_are_rejected(db: Session, project: m.Project, monkeypatch, tmp_path):
    bad = ["../escape.py", ".git/config", "C:/win.py", "a/../../b.py"]
    files = [{"path": p, "content": "x"} for p in bad] + [{"path": "app\\ok.py", "content": "ok"}]
    DeveloperAgent(_fake_llm(monkeypatch, {"files": files})).run(db, project.id, EXECUTION)
    ws = Workspace(project.id)
    assert ws.files() == ["app/ok.py"]
    assert not (ws.path.parent / "escape.py").exists()
    assert _kinds(db, project.id).count("file_rejected") == len(bad)


def test_leading_slash_path_is_read_as_repo_relative(db: Session, project: m.Project, monkeypatch):
    files = [{"path": "/app/main.py", "content": "ok"}]
    DeveloperAgent(_fake_llm(monkeypatch, {"files": files})).run(db, project.id, EXECUTION)
    assert Workspace(project.id).files() == ["app/main.py"]
    assert "file_rejected" not in _kinds(db, project.id)


def test_story_id_task_builds_that_story_only(db: Session, project: m.Project):
    other = _story(db, project, "Delete an item")  # not in a sprint, but asked for directly
    DeveloperAgent().run(db, project.id, {**EXECUTION, "story_id": other.id})
    assert Workspace(project.id).history() == [f"Story #{other.id}: Delete an item"]


def test_story_from_another_project_is_ignored(db: Session, project: m.Project):
    q = repo.create_project(db, "Other", "x")
    out = DeveloperAgent().run(db, q.id, {"story_id": _story(db, project).id})
    assert out.summary == "No sprint stories need code"
    assert Workspace(q.id).history() == []


def test_prompt_has_story_design_bugs_and_files(db: Session, project: m.Project):
    story = _story(db, project)
    agent = DeveloperAgent()
    Tools(db, project.id, "architect").write_artifact("architecture", "Overview", "Use FastAPI")
    Tools(db, project.id, "architect").write_artifact("design", "Design", "Add POST /items",
                                                      story_id=story.id)
    first = agent.build_prompt(db, project.id, {"story_id": story.id})
    assert "Given the app When I add a title Then it is listed" in first
    assert "Use FastAPI" in first and "Add POST /items" in first
    assert "(empty repository)" in first

    agent.run(db, project.id, EXECUTION)
    Tools(db, project.id, "qa").report_bug(story.id, "500 on empty title")
    second = agent.build_prompt(db, project.id, {"story_id": story.id})
    assert "500 on empty title (attempt 1 of 3)" in second
    assert "=== app/main.py ===" in second


def test_workspace_basics(tmp_path):
    ws = Workspace(1, tmp_path).init()
    assert ws.commit("nothing") is None
    assert ws.write("a.txt", "1") and not ws.write("a.txt", "1")
    sha = ws.commit("first")
    assert len(sha) == 40 and ws.history() == ["first"]
    for bad in ["", "../x", "/x", ".git/HEAD"]:
        with pytest.raises(UnsafePath):
            ws.resolve(bad)


def test_registered_and_runs_in_orchestrator(db: Session, project: m.Project):
    assert isinstance(AGENTS["developer"], DeveloperAgent)
    o = Orchestrator(db, AGENTS)
    o.step(project.id)  # backlog
    o.step(project.id)  # sprint planning (gate)
    o.approve(project.id)
    o.step(project.id)  # execution: developer runs, then QA adds its tests
    assert repo.artifacts(db, project.id, "code")
    history = Workspace(project.id).history()
    developer_commits = [message for message in history if message.startswith("Story #")]
    qa_commits = [message for message in history if message.startswith("Tests for story #")]
    assert developer_commits and len(developer_commits) == len(qa_commits)
