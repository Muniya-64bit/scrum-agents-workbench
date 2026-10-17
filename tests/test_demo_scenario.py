"""The scripted todo-app demo scenario replays offline and tells the whole story of #17-#19."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from tests.factories import agents_for
from workbench import config, metrics, runner, schemas
from workbench.db import models as m
from workbench.db import repo
from workbench.orchestrator.engine import Orchestrator
from workbench.workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "demo" / "scenarios" / "todo-app"
SPEC = json.loads((SCENARIO / "scenario.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def story(tmp_path_factory):
    """One replay of the scenario; the tests below look at different parts of the result."""
    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("workspaces")
    mp.setattr(config, "WORKSPACES_DIR", str(root))
    for name, value in SPEC["env"].items():
        mp.setattr(config, name, int(value))
    from sqlalchemy.orm import sessionmaker

    from workbench.db.session import init_db, make_engine

    engine = make_engine("sqlite://")
    init_db(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        project = repo.create_project(db, SPEC["project_name"], SPEC["idea"])
        # fallback "error": the scenario must answer every call itself
        Orchestrator(db, agents_for("replay", SCENARIO)).run_to_end(project.id)
        project.workspaces_root = root  # the per-test fixture changes config.WORKSPACES_DIR
        yield db, project
    finally:
        db.close()
        mp.undo()


def events(db: Session, project: m.Project, kind: str) -> list[m.Event]:
    return [e for e in repo.events_since(db, project.id) if e.kind == kind]


def test_project_runs_from_idea_to_done_in_three_sprints(story):
    db, project = story
    assert project.phase == "done"
    assert [s.number for s in repo.sprints(db, project.id)] == [1, 2, 3]
    assert [e.message for e in events(db, project, "phase_started")].count("sprint_planning") == 3


def test_every_call_is_scripted_without_fallbacks_or_drift(story):
    db, project = story
    assert events(db, project, "llm_replay_fallback") == []
    assert events(db, project, "llm_replay_drift") == []
    modes = {e.payload["llm_mode"] for e in events(db, project, "agent_finished")}
    assert modes == {"replay", "none"}
    for kind in ("file_rejected", "code_unchanged", "tests_missing", "design_missing",
                 "docker_build_failed", "tests_skipped", "retro_exists", "sprint_skipped"):
        assert events(db, project, kind) == [], kind


def test_sprint_numbers_tell_the_improvement_story(story):
    db, project = story
    got = metrics.project_metrics(db, project.id)["sprints"]
    assert [(s["committed_points"], s["completed_points"]) for s in got] == [
        (10, 7), (6, 6), (3, 3)]
    assert [s["commitment_reliability"] for s in got] == [0.7, 1.0, 1.0]
    assert [s["first_pass_yield"] for s in got] == [0.5, 1.0, 1.0]
    assert [s["bugs_reported"] for s in got] == [2, 0, 0]
    assert [s["carried_over_stories"] for s in got] == [1, 0, 0]
    assert [s["process"]["capacity"] for s in got] == [10, 7, 7]
    assert [s["process"]["max_fix_retries"] for s in got] == [1, 2, 2]
    assert [s["process"]["test_first"] for s in got] == [False, True, True]
    assert got[1]["process"]["guidelines"]  # the retrospective added a working agreement


def test_pdca_rows_show_the_change_and_its_effect(story):
    db, project = story
    rows = metrics.improvement_rows(db, project.id)
    assert rows[0]["act"]["proposed_changes"]["capacity"] == 7
    assert rows[1]["plan"]["changes_applied"]["test_first"] == [False, True]
    assert rows[1]["deltas"]["commitment_reliability"] == pytest.approx(0.3)
    assert rows[1]["deltas"]["first_pass_yield"] == pytest.approx(0.5)
    assert rows[1]["deltas"]["bugs_reported"] == -2


def test_defects_are_found_fixed_and_carried_over(story):
    db, project = story
    titles = {s.id: s.title for s in repo.backlog(db, project.id)}
    assert [titles[s] for s in sorted(titles)] == [
        "Create item", "List items", "Complete item", "Delete item", "Edit title",
        "Filter by status"]
    bugs = db.query(m.Bug).order_by(m.Bug.id).all()
    assert [(b.story_id, b.status, b.retries) for b in bugs] == [(1, "fixed", 1), (4, "fixed", 2)]
    assert "201" in bugs[0].description and "200" in bugs[1].description
    carried = events(db, project, "story_carried_over")
    assert [e.payload["story_id"] for e in carried] == [4]
    assert len(events(db, project, "bugs_left_open")) == 1
    assert len(events(db, project, "tests_written_first")) == 2  # stories 5 and 6
    assert all(repo.story_is_done(s) for s in repo.backlog(db, project.id))


def test_releases_are_tagged_and_the_generated_app_passes_its_tests(story):
    db, project = story
    versions = [e.payload["version"] for e in events(db, project, "release_created")]
    assert versions == ["v0.1.0", "v0.2.0", "v0.3.0"]
    ws = Workspace(project.id, project.workspaces_root)
    assert all(ws._tag_sha(v) for v in versions)
    result = runner.run_pytest(ws.path)
    assert result.ok, result.output
    assert result.passed == 14 and result.failures == []
    assert {"app/main.py", "Dockerfile", "releases/v0.3.0.md"} <= set(ws.files())


def test_call_files_match_their_schema_and_keys():
    files = sorted((SCENARIO / "calls").glob("*.json"))
    assert len(files) == 32
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert path.name == f"{data['key']}.{data['n']}.json"
        assert data["source"] == "scripted" and data["usage"] == {
            "input_tokens": 0, "output_tokens": 0}
        getattr(schemas, data["schema"]).model_validate(data["output"])


def test_demo_script_reports_an_unknown_scenario():
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo.py"), "run",
                           "--scenario", "nope"], capture_output=True, text=True, check=False)
    assert done.returncode != 0 and "No scenario 'nope'" in done.stderr
    assert "todo-app" in done.stderr
