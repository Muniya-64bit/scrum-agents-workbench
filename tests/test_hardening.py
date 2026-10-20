"""Behaviour that must not regress: Tools events, process-engine branches, gate errors,
workspace and runner safety, SSE resume, the live LLM call, metrics edge cases."""

import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import config, metrics, process, runner
from workbench.agents.registry import AGENTS
from workbench.agents.release import ReleaseAgent
from workbench.agents.tools import Tools
from workbench.api import main as api_main
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.llm.client import LLMClient, LLMError
from workbench.orchestrator.engine import MAX_STEPS, Orchestrator, Phase
from workbench.schemas import CodeOutput
from workbench.workspace import UnsafePath, Workspace


def kinds(db: Session, project_id: int) -> list[str]:
    return [e.kind for e in repo.events_since(db, project_id)]


def last(db: Session, project_id: int) -> m.Event:
    return repo.events_since(db, project_id)[-1]


# --- Tools: one event per call, with the documented payload keys -----------------------------


def test_every_tool_logs_its_event_with_documented_keys(db: Session):
    p = repo.create_project(db, "x", "y")
    t = Tools(db, p.id, "scrum_master")

    def check(kind: str, keys: set[str], agent: str = "scrum_master", back: int = 1) -> m.Event:
        e = repo.events_since(db, p.id)[-back]
        assert (e.kind, set(e.payload), e.agent) == (kind, keys, agent), e.payload
        return e

    def check_message(to: str, subject: str, back: int = 1) -> None:
        """A bug report or a fix attempt also tells the other agent."""
        e = repo.events_since(db, p.id)[-back]
        assert (e.kind, e.payload["to"], e.message) == ("agent_message", to, subject)
        assert {"to", "body", "story_id", "bug_id"} <= set(e.payload)

    t.set_vision("Be useful")
    assert check("vision_set", set()).message == "Be useful"
    epic = t.create_epic("Epic", "d")
    check("epic_created", {"epic_id"})
    story = t.create_story(epic.id, title="Story", points=3)
    check("story_created", {"story_id"})
    sprint = t.create_sprint("goal", 8)
    e = check("sprint_created", {"sprint_id"})
    assert e.message == "Sprint 1: goal" and sprint.status == "active" and sprint.capacity == 8
    t.add_story_to_sprint(sprint.id, story.id)
    check("story_planned", {"story_id", "sprint_id"})
    assert story.status == "sprint" and story.sprint_id == sprint.id
    task = t.create_task(story.id, "Build", "developer")
    check("task_created", {"task_id", "story_id", "assignee"})
    t.update_task(task.id, "doing")
    e = check("task_updated", {"task_id", "status", "story_id"})
    assert e.message == "Build -> doing"
    snap = t.snapshot_burndown(sprint.id)
    check("burndown_snapshot", {"sprint_id", "remaining"})
    assert snap == {"sprint_id": sprint.id, "remaining": 3}
    art = t.write_artifact("code", "main.py", "x = 1", story_id=story.id, path="main.py")
    check("artifact_created", {"artifact_id", "artifact_kind"})
    assert [(link.story_id, link.relation) for link in
            db.query(m.TraceLink).filter_by(artifact_id=art.id)] == [(story.id, "code")]
    t.link_artifact(art.id, [story.id], "design")
    check("artifact_linked", {"artifact_id", "story_ids"})
    bug = t.report_bug(story.id, "boom")
    check("bug_reported", {"bug_id", "story_id"}, back=2)
    check_message("developer", f"Please fix bug #{bug.id}")
    t.record_fix_attempt(bug.id, fixed=False)
    check("bug_fix_failed", {"bug_id", "story_id", "retries"}, back=2)
    check_message("qa", f"Bug #{bug.id}: I could not fix it")
    t.record_fix_attempt(bug.id, fixed=True)
    e = check("bug_fixed", {"bug_id", "story_id", "retries"}, back=2)
    check_message("qa", f"Bug #{bug.id}: a fix is committed, please test again")
    assert e.payload["retries"] == 2 and bug.status == "fixed"
    t.reopen_bug(bug.id)
    check("bug_reopened", {"bug_id", "story_id"})
    assert bug.status == "open"
    t.verify_bug(bug.id)
    check("bug_verified", {"bug_id", "story_id"})
    t.unplan_story(story.id, sprint.id)
    check("story_carried_over", {"story_id", "from_sprint_id"})
    assert story.sprint_id is None and story.status == "backlog"
    t.save_retro(sprint.id, {"went_well": ["a"]})
    e = check("retro_saved", {"sprint_id", "went_well"})
    assert sprint.status == "done" and sprint.retro == {"went_well": ["a"]}
    t.log("custom", "msg", a=1)
    check("custom", {"a"})


# --- orchestrator branches ---------------------------------------------------------------------


def test_step_on_a_finished_project_changes_nothing(db: Session):
    p = repo.create_project(db, "x", "y")
    Orchestrator(db).run_to_end(p.id)
    before = len(kinds(db, p.id))
    assert Orchestrator(db).step(p.id).phase == Phase.DONE
    assert len(kinds(db, p.id)) == before


def test_gates_block_until_approved(db: Session):
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)
    o.step(p.id)  # backlog
    o.step(p.id)  # sprint planning: gate
    assert p.awaiting_approval and last(db, p.id).kind == "approval_requested"
    with pytest.raises(RuntimeError, match="Awaiting human approval"):
        o.step(p.id)
    o.approve(p.id, approved=False, comment="not yet")
    e = last(db, p.id)
    assert (e.kind, e.message, e.payload) == ("rejected", "not yet", {"phase": "sprint_planning"})
    assert not p.awaiting_approval and p.phase == Phase.SPRINT_PLANNING


def test_approve_with_nothing_pending_is_an_error(db: Session):
    p = repo.create_project(db, "x", "y")
    with pytest.raises(RuntimeError, match="Nothing to approve"):
        Orchestrator(db).approve(p.id)


def test_run_to_end_gives_up_after_the_step_cap(db: Session, monkeypatch):
    p = repo.create_project(db, "x", "y")
    monkeypatch.setattr("workbench.orchestrator.engine.MAX_STEPS", 3)
    with pytest.raises(RuntimeError, match="did not finish within 3 steps"):
        Orchestrator(db).run_to_end(p.id)
    assert p.phase != Phase.DONE and MAX_STEPS == 200


def test_run_to_end_may_finish_on_its_last_allowed_step(db: Session, monkeypatch):
    p = repo.create_project(db, "x", "y")
    monkeypatch.setattr("workbench.orchestrator.engine.MAX_STEPS", 7)  # a one-sprint flow
    assert Orchestrator(db).run_to_end(p.id).phase == Phase.DONE


def test_run_to_end_returns_a_finished_project(db: Session):
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)
    assert o.run_to_end(p.id).phase == Phase.DONE
    assert o.run_to_end(p.id).phase == Phase.DONE  # nothing left to do


def test_phase_order_without_a_loop(db: Session):
    """The loop edge only exists after a release and only while another sprint is possible."""
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)
    expected = {Phase.IDEA: Phase.BACKLOG, Phase.BACKLOG: Phase.SPRINT_PLANNING,
                Phase.SPRINT_PLANNING: Phase.EXECUTION, Phase.EXECUTION: Phase.REVIEW,
                Phase.REVIEW: Phase.RETRO, Phase.RETRO: Phase.RELEASE,
                Phase.RELEASE: Phase.DONE}
    for current, nxt in expected.items():
        p.phase = current.value
        assert o.next_phase(p) == nxt, current


def test_loop_edge_needs_a_story_that_fits_and_sprints_left(db: Session, monkeypatch):
    p = repo.create_project(db, "x", "y")
    po = Tools(db, p.id, "product_owner")
    po.create_story(po.create_epic("E").id, title="Big", points=13)
    o = Orchestrator(db)
    assert not o.more_sprints(p.id)  # does not fit the default capacity
    po.create_story(po.create_epic("E2").id, title="Small", points=2)
    assert o.more_sprints(p.id)
    p.phase = Phase.RELEASE.value
    assert o.next_phase(p) == Phase.SPRINT_PLANNING
    monkeypatch.setattr(config, "MAX_SPRINTS", 0)
    assert not o.more_sprints(p.id) and o.next_phase(p) == Phase.DONE


def test_unlisted_roles_run_as_stubs(db: Session):
    o = Orchestrator(db, {"qa": AGENTS["qa"]})
    assert o.agents["qa"] is AGENTS["qa"] and o.agents["developer"].role == "developer"


# --- API: gate errors, trace skipping, resume --------------------------------------------------


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as s:
            yield s

    api_main.app.dependency_overrides[get_session] = override
    yield TestClient(api_main.app), factory
    api_main.app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_gate_errors_are_409_over_the_api(api):
    c, _ = api
    pid = c.post("/projects", json={"name": "n", "idea": "i"}).json()["id"]
    r = c.post(f"/projects/{pid}/approve")
    assert r.status_code == 409 and "Nothing to approve" in r.json()["detail"]
    c.post(f"/projects/{pid}/advance")
    c.post(f"/projects/{pid}/advance")  # sprint planning: waiting for a human
    r = c.post(f"/projects/{pid}/advance")
    assert r.status_code == 409 and "Awaiting human approval" in r.json()["detail"]
    assert c.post(f"/projects/{pid}/approve").json()["awaiting_approval"] is False
    assert c.post("/projects/999/advance").status_code == 404
    assert c.post("/projects/999/approve").status_code == 404


def test_stream_resumes_after_last_event_id(api, monkeypatch):
    c, factory = api
    pid = c.post("/projects", json={"name": "n", "idea": "i"}).json()["id"]
    c.post(f"/projects/{pid}/advance")
    with factory() as db:
        all_ids = [e.id for e in repo.events_since(db, pid)]
    assert len(all_ids) >= 3
    monkeypatch.setattr(api_main, "SessionLocal", factory)

    class Request:
        calls = 0

        async def is_disconnected(self):
            Request.calls += 1
            return Request.calls > 1  # one poll, then the client goes away

    async def frames(**kwargs):
        with factory() as db:
            response = api_main.stream(pid, Request(), db=db, **kwargs)
        Request.calls = 0
        return [f async for f in response.body_iterator]

    got = asyncio.run(frames(after=0, last_event_id=all_ids[0]))  # header wins over ?after=
    ids = [int(f.split("\n", 1)[0][4:]) for f in got if f.startswith("id: ")]
    assert ids == all_ids[1:]
    assert asyncio.run(frames(after=all_ids[-1], last_event_id=None))[1:] == []


def test_stream_sends_a_keep_alive_when_idle(api, monkeypatch):
    _, factory = api
    from workbench.api import sse

    monkeypatch.setattr(sse, "KEEPALIVE_SECONDS", 0.015)
    polls = iter([False] * 5 + [True])

    async def disconnected():
        return next(polls)

    async def collect():
        gen = sse.event_stream(factory, 1, 0, disconnected, poll_seconds=0.01)
        return [f async for f in gen]

    frames = asyncio.run(collect())
    assert frames.count(": keep-alive\n\n") == 2  # after every second empty poll


def test_startup_creates_the_tables():
    """The app's own engine points at a scratch file in tests (see conftest), never the real DB."""
    with TestClient(api_main.app) as c:
        assert c.get("/projects").status_code == 200


def test_traceability_ignores_links_to_unknown_stories(api):
    c, factory = api
    with factory() as db:
        p = repo.create_project(db, "x", "y")
        Tools(db, p.id, "developer").write_artifact("code", "a.py", "x", path="a.py")
        art = db.query(m.Artifact).one()
        db.add(m.TraceLink(story_id=999, artifact_id=art.id, relation="code"))
        db.commit()
        pid = p.id
    assert c.get(f"/projects/{pid}/traceability").json() == []


# --- workspace and runner ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "  ", "..", "../x", "a/../../x", "/etc/passwd", "C:\\x",
                                 "C:/x", "\\\\server\\share", "..\\x", ".git/config",
                                 "src/.git/config", "a\\..\\..\\b"])
def test_workspace_rejects_unsafe_paths(tmp_path, bad):
    ws = Workspace(1, tmp_path).init()
    with pytest.raises(UnsafePath):
        ws.resolve(bad)
    with pytest.raises(UnsafePath):
        ws.write(bad, "x")


def test_workspace_never_writes_a_nul_character(tmp_path):
    ws = Workspace(1, tmp_path).init()
    assert ws.write("app/main.py", "a = 1\x00\nb = 2\x00\n") is True
    assert ws.read("app/main.py") == "a = 1\nb = 2\n"
    assert ws.write("app/main.py", "a = 1\nb = 2\x00\n") is False  # the cleaned text is the same


def test_workspace_accepts_nested_and_backslash_paths(tmp_path):
    ws = Workspace(1, tmp_path).init()
    ws.write("app\\routes\\items.py", "x = 1")
    assert ws.read("app/routes/items.py") == "x = 1"
    assert ws.files() == ["app/routes/items.py"]
    assert ws.resolve("app/routes/items.py").is_relative_to(ws.path)


def test_history_of_a_repository_without_commits_is_empty(tmp_path):
    assert Workspace(1, tmp_path).init().history() == []
    assert Workspace(2, tmp_path).files() == []  # directory does not exist yet


def test_runner_reports_when_no_tests_are_collected(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "helper.py").write_text("x = 1\n")
    result = runner.run_pytest(tmp_path)
    assert not result.ok
    assert [f.test for f in result.failures] == ["collection"]


def test_runner_reports_a_crash_before_the_report(tmp_path):
    result = runner.run_pytest(tmp_path, ["--no-such-flag"])
    assert not result.ok and result.failures[0].test in ("pytest", "collection")
    assert result.output


def test_runner_counts_passes_failures_and_skips(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "import pytest\n"
        "def test_ok():\n    assert True\n"
        "def test_bad():\n    assert 1 == 2\n"
        "@pytest.mark.skip\ndef test_skipped():\n    pass\n")
    result = runner.run_pytest(tmp_path)
    assert result.passed == 1 and [f.test for f in result.failures] == ["tests.test_a.test_bad"]
    assert not result.ok


# --- LLMClient: the live call -----------------------------------------------------------------


def test_live_call_reads_text_blocks_and_counts_tokens(monkeypatch):
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            block = types.SimpleNamespace(type="text", text='```json\n{"summary": "hi"}\n```')
            other = types.SimpleNamespace(type="thinking", text="ignored")
            usage = types.SimpleNamespace(input_tokens=11, output_tokens=7)
            return types.SimpleNamespace(content=[other, block], usage=usage)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    llm = LLMClient(mock=False, use_cache=False)
    usage: dict = {}
    out = llm.complete_json("system text", "user text", CodeOutput, usage=usage)
    assert out.summary == "hi"
    assert usage == {"calls": 1, "input_tokens": 11, "output_tokens": 7, "cache_hits": 0,
                     "invalid_outputs": 0}
    assert calls[0]["model"] == config.MODEL and calls[0]["system"] == "system text"
    assert "JSON schema" in calls[0]["messages"][0]["content"]
    llm.complete_json("system text", "user text", CodeOutput)
    assert llm._client is not None and len(calls) == 2  # the client is created once


def test_live_call_gives_up_after_the_retries(monkeypatch):
    llm = LLMClient(mock=False, use_cache=False, max_retries=1)
    attempts = []

    def call(system, prompt, stats):
        attempts.append(prompt)
        stats["calls"] += 1
        return "no json here"

    monkeypatch.setattr(llm, "_call", call)
    usage: dict = {}
    with pytest.raises(LLMError, match="No valid output after 2 attempts"):
        llm.complete_json("s", "u", CodeOutput, usage=usage)
    assert usage["calls"] == 2 and usage["invalid_outputs"] == 2
    assert "Previous attempt invalid" in attempts[1] and llm.usage["calls"] == 2


# --- metrics edge cases ------------------------------------------------------------------------


def test_sprints_that_never_closed(db: Session):
    p = repo.create_project(db, "x", "y")
    po, sm = Tools(db, p.id, "product_owner"), Tools(db, p.id, "scrum_master")
    stories = [po.create_story(po.create_epic("E").id, title=f"S{i}", points=2) for i in range(2)]
    first, second = sm.create_sprint("one", 4), sm.create_sprint("two", 4)
    for sprint, story in ((first, stories[0]), (second, stories[1])):
        sm.add_story_to_sprint(sprint.id, story.id)
        sm.log("sprint_planned", "x", sprint_id=sprint.id, number=sprint.number,
               story_ids=[story.id], committed_points=2, capacity=4)
    windows = metrics.sprint_windows(db, p.id)
    # no retro was saved: sprint 1 ends where sprint 2 starts, the last sprint stays open
    assert [w.closed for w in windows] == [True, False]
    assert windows[0].end_id == windows[1].start_id - 1
    got = metrics.project_metrics(db, p.id)
    assert [s["closed"] for s in got["sprints"]] == [True, False]
    assert [s["committed_points"] for s in got["sprints"]] == [2, 2]
    assert [s["completed_points"] for s in got["sprints"]] == [0, 0]
    rows = metrics.improvement_rows(db, p.id)
    assert len(rows) == 2


def test_event_filters_and_unknown_bug_lookup(db: Session):
    p = repo.create_project(db, "x", "y")
    t = Tools(db, p.id, "qa")
    for kind in ("a", "b", "c", "b"):
        t.log(kind)
    ids = [e.id for e in repo.events_since(db, p.id)]
    assert [e.kind for e in metrics._events(db, p.id, kinds=["b"])] == ["b", "b"]
    assert [e.id for e in metrics._events(db, p.id, start_id=ids[1], end_id=ids[2])] == ids[1:3]
    assert metrics._story_of_bug(db, None) is None and metrics._story_of_bug(db, 999) is None


def test_task_events_for_deleted_tasks_are_ignored(db: Session):
    p = repo.create_project(db, "x", "y")
    t = Tools(db, p.id, "developer")
    t.log("task_updated", "Ghost -> done", task_id=4242, status="done")
    assert metrics._replay_tasks(db, p.id, 10**9) == {}


# --- process and release ------------------------------------------------------------------------


def test_a_malformed_stored_process_falls_back_to_the_defaults():
    got = process._from_plan({"capacity": "lots"})
    assert got == process.ProcessConfig.defaults()
    assert process._from_plan({}) == process.ProcessConfig.defaults()
    assert process._from_plan({"capacity": 4}).capacity == 4


def test_release_agent_without_a_builder_writes_notes_and_a_tag_only(db: Session):
    p = repo.create_project(db, "x", "y")
    sm = Tools(db, p.id, "scrum_master")
    sm.create_sprint("goal", 5)
    ReleaseAgent().run(db, p.id, {"name": "release", "phase": "release"})
    ws = Workspace(p.id)
    assert ws.files() == ["releases/v0.1.0.md"]
    assert ws.history() == ["Release v0.1.0"]
    assert ws._tag_sha("v0.1.0")
    assert "release_created" in kinds(db, p.id)
    agent = ReleaseAgent()
    assert agent.build_prompt(db, p.id, {}) == "" and agent.apply(None, None, {}) is None
    assert agent.workspaces_dir is None


def test_release_agent_with_the_devops_builder_adds_the_release_files(db: Session):
    p = repo.create_project(db, "x", "y")
    Tools(db, p.id, "scrum_master").create_sprint("goal", 5)
    AGENTS["devops"].run(db, p.id, {"name": "release", "phase": "release"})
    files = set(Workspace(p.id).files())
    assert {"Dockerfile", ".github/workflows/ci.yml", "RELEASE_NOTES.md",
            "releases/v0.1.0.md"} <= files
    assert Workspace(p.id).history()[0] == "Release v0.1.0"
    assert Workspace(p.id).history()[1] == "Prepare release"
