"""End-to-end proof that the registered agents can complete one mock sprint."""

from sqlalchemy.orm import Session

from workbench import runner
from workbench.agents.registry import AGENTS
from workbench.db import models as m
from workbench.db import repo
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.workspace import Workspace


def test_idea_to_release_with_passing_generated_tests(db: Session):
    project = repo.create_project(
        db,
        "Todo application",
        "A simple application for creating and completing tasks",
    )

    Orchestrator(db, AGENTS).run_to_end(project.id)

    assert project.phase == Phase.DONE
    assert project.awaiting_approval is False

    sprint = repo.current_sprint(db, project.id)
    assert sprint is not None
    assert sprint.stories
    assert all(repo.story_is_done(story) for story in sprint.stories)

    workspace = Workspace(project.id)
    files = set(workspace.files())
    assert {"app/main.py", "Dockerfile", ".github/workflows/ci.yml", "RELEASE_NOTES.md"} <= files
    assert any(path.startswith("tests/test_story_") for path in files)

    generated_tests = runner.run_pytest(workspace.path)
    assert generated_tests.ok, generated_tests.output

    open_bugs = db.query(m.Bug).filter_by(status="open").all()
    assert open_bugs == []

    artifacts = repo.list_for_project(db, project.id, m.Artifact)
    assert {"architecture", "code", "test", "release"} <= {a.kind for a in artifacts}

    phases = [
        event.message
        for event in repo.events_since(db, project.id)
        if event.kind == "phase_started"
    ]
    assert phases == [
        "backlog",
        "sprint_planning",
        "execution",
        "review",
        "retro",
        "release",
        "done",
    ]
