from types import SimpleNamespace

from sqlalchemy.orm import Session

from workbench.agents.devops import ALLOWED_FILES, DevOpsAgent
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.workspace import Workspace

RELEASE = {"name": "release", "phase": "release"}


def _project_with_stories(db: Session) -> tuple[m.Project, m.UserStory, m.UserStory]:
    project = repo.create_project(db, "Todo App", "A simple to-do app")
    tools = Tools(db, project.id, "product_owner")
    epic = tools.create_epic("Core")
    complete = tools.create_story(epic.id, title="Create an item")
    incomplete = tools.create_story(epic.id, title="Delete an item")
    for story in (complete, incomplete):
        tools.create_task(story.id, f"Implement {story.title}", "developer")
        tools.create_task(story.id, f"Test {story.title}", "qa")
    for task in complete.tasks:
        tools.update_task(task.id, "done")
    tools.update_task(incomplete.tasks[0].id, "done")
    return project, complete, incomplete


def _event_kinds(db: Session, project_id: int) -> list[str]:
    return [event.kind for event in repo.events_since(db, project_id)]


def test_generates_release_files_artifacts_and_completed_story_notes(
    db: Session, tmp_path, monkeypatch
):
    project, complete, incomplete = _project_with_stories(db)
    monkeypatch.setattr("workbench.agents.devops.shutil.which", lambda _: None)

    DevOpsAgent(LLMClient(mock=True), workspaces_dir=tmp_path).run(db, project.id, RELEASE)

    workspace = Workspace(project.id, tmp_path)
    assert set(workspace.files()) == ALLOWED_FILES
    assert workspace.history() == ["Prepare release"]
    notes = workspace.read("RELEASE_NOTES.md")
    assert complete.title in notes and incomplete.title not in notes
    artifacts = repo.list_for_project(db, project.id, m.Artifact)
    assert {artifact.path for artifact in artifacts} == ALLOWED_FILES
    assert all(artifact.kind == "release" and artifact.created_by == "devops"
               for artifact in artifacts)
    assert "docker_build_skipped" in _event_kinds(db, project.id)


def test_rejects_unexpected_files_and_records_successful_docker_build(
    db: Session, tmp_path, monkeypatch
):
    project = repo.create_project(db, "Todo App", "A simple to-do app")
    agent = DevOpsAgent(workspaces_dir=tmp_path)
    output = agent.output_schema.model_validate({
        "files": [
            {"path": "Dockerfile", "content": "FROM scratch\n"},
            {"path": "../outside.txt", "content": "unsafe"},
        ]
    })
    calls = []
    monkeypatch.setattr("workbench.agents.devops.config.MOCK_LLM", False)
    monkeypatch.setattr("workbench.agents.devops.shutil.which", lambda _: "docker")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="built", stderr="")

    monkeypatch.setattr("workbench.agents.devops.subprocess.run", fake_run)
    agent.apply(Tools(db, project.id, "devops"), output, RELEASE)

    assert not (tmp_path / "outside.txt").exists()
    docker_calls = [call for call in calls if call[0][0] == "docker"]
    assert docker_calls[0][0] == ["docker", "build", "-t", "todo-app:latest", "."]
    assert docker_calls[0][1]["cwd"] == Workspace(project.id, tmp_path).path
    kinds = _event_kinds(db, project.id)
    assert "release_file_rejected" in kinds and "docker_build_succeeded" in kinds


def test_docker_failure_is_logged_without_failing_release(db: Session, tmp_path, monkeypatch):
    project = repo.create_project(db, "Todo", "A simple to-do app")
    monkeypatch.setattr("workbench.agents.devops.config.MOCK_LLM", False)
    monkeypatch.setattr("workbench.agents.devops.shutil.which", lambda _: "docker")
    monkeypatch.setattr(
        "workbench.agents.devops.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad build"),
    )

    DevOpsAgent(LLMClient(mock=True), workspaces_dir=tmp_path).run(db, project.id, RELEASE)

    failures = [event for event in repo.events_since(db, project.id)
                if event.kind == "docker_build_failed"]
    assert failures and "bad build" in failures[-1].message
    assert Workspace(project.id, tmp_path).resolve("RELEASE_NOTES.md").is_file()


def test_registered_and_runs_in_release_phase(db: Session, tmp_path, monkeypatch):
    assert isinstance(AGENTS["devops"], DevOpsAgent)
    monkeypatch.setattr("workbench.config.WORKSPACES_DIR", str(tmp_path))
    monkeypatch.setattr("workbench.agents.devops.shutil.which", lambda _: None)
    project = repo.create_project(db, "Todo", "A simple to-do app")

    Orchestrator(db, AGENTS).run_to_end(project.id)

    assert project.phase == Phase.DONE
    assert (tmp_path / f"project-{project.id}" / "Dockerfile").is_file()
    assert "agent_finished" in _event_kinds(db, project.id)
