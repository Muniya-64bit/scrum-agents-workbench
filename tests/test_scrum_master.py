import json

import pytest
from sqlalchemy.orm import Session

from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.registry import AGENTS
from workbench.agents.scrum_master import (
    ScrumMasterAgent,
    SprintPlanner,
    _blocked_ids,
    plan_stories,
)
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator, Phase

PLANNING = {"name": "sprint_planning", "phase": "sprint_planning"}
REVIEW = {"name": "review", "phase": "review"}
RETRO = {"name": "retro", "phase": "retro"}


@pytest.fixture
def project(db: Session) -> m.Project:
    """A project with the Product Owner's mock backlog: stories of 3 and 2 points."""
    p = repo.create_project(db, "Todo", "A simple to-do app")
    ProductOwnerAgent().run(db, p.id)
    return p


def test_planning_creates_sprint_stories_and_tasks(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    assert sprint.number == 1 and sprint.status == "active"
    assert len(sprint.stories) == 2 and all(s.status == "sprint" for s in sprint.stories)
    tasks = [t for s in sprint.stories for t in s.tasks]
    assert len(tasks) == 4
    assert {t.assignee for t in tasks} == {"developer", "qa"}
    assert repo.unplanned_stories(db, project.id) == []


def test_planning_logs_sprint_planned(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    event = [e for e in repo.events_since(db, project.id) if e.kind == "sprint_planned"][0]
    assert event.agent == "scrum_master"
    assert event.payload == {"sprint_id": sprint.id, "number": 1, "capacity": 10,
                             "story_ids": [s.id for s in sprint.stories],
                             "committed_points": sum(s.points for s in sprint.stories),
                             "process": {"capacity": 10, "max_fix_retries": 3,
                                         "test_first": False, "guidelines": []},
                             "process_changes": {}, "process_reason": ""}


def test_planning_respects_capacity(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, {**PLANNING, "capacity": 3})
    sprint = repo.current_sprint(db, project.id)
    assert sum(s.points for s in sprint.stories) <= 3
    assert len(repo.unplanned_stories(db, project.id)) == 1  # left in the backlog


def test_planning_ignores_bad_llm_choices(db: Session, project: m.Project, monkeypatch):
    """Unknown ids, duplicates and over-capacity picks from the model are dropped."""
    first, second = repo.backlog(db, project.id)
    reply = json.dumps({"goal": "G", "story_ids": [999, first.id, first.id, second.id],
                        "tasks": [{"story_id": first.id, "title": "T", "assignee": "wizard"}]})
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: reply)
    ScrumMasterAgent(llm).run(db, project.id, {**PLANNING, "capacity": 3})
    sprint = repo.current_sprint(db, project.id)
    assert [s.id for s in sprint.stories] == [first.id]
    # an unknown assignee falls back to developer, and the story gets the QA task it lacks
    assert [(t.title, t.assignee) for t in sprint.stories[0].tasks] == [
        ("T", "developer"), (f"Test: {first.title}", "qa")]


CLOSERS = {"developer", "qa"}  # the only agents that ever mark a task done


def _plan_with_tasks(db: Session, project: m.Project, monkeypatch,
                     tasks: list[dict]) -> list[m.Task]:
    first = repo.backlog(db, project.id)[0]
    reply = json.dumps({"goal": "G", "story_ids": [first.id],
                        "tasks": [{"story_id": first.id, **t} for t in tasks]})
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: reply)
    ScrumMasterAgent(llm).run(db, project.id, {**PLANNING, "capacity": 3})
    return repo.current_sprint(db, project.id).stories[0].tasks


@pytest.mark.parametrize("role", ["architect", "product_owner", "scrum_master", "devops", "wizard"])
def test_no_story_is_planned_with_a_task_nobody_closes(db: Session, project: m.Project,
                                                       monkeypatch, role: str):
    """Live runs had tasks for the architect or product owner that stayed `todo` forever, so
    their stories could never be completed."""
    tasks = _plan_with_tasks(db, project, monkeypatch, [
        {"title": "Design it", "assignee": role}, {"title": "Build it", "assignee": "developer"},
        {"title": "Check it", "assignee": "qa"}])
    assert {t.assignee for t in tasks} == CLOSERS
    assert [t.title for t in tasks if t.title == "Design it"] == ["Design it"]  # kept, reassigned


def test_a_story_always_has_a_developer_task_and_a_qa_task(db: Session, project: m.Project,
                                                           monkeypatch):
    only_qa = _plan_with_tasks(db, project, monkeypatch, [{"title": "Check", "assignee": "qa"}])
    assert sorted(t.assignee for t in only_qa) == ["developer", "qa"]


def test_a_developer_only_story_gets_a_qa_task_so_it_cannot_finish_untested(
        db: Session, project: m.Project, monkeypatch):
    tasks = _plan_with_tasks(db, project, monkeypatch,
                             [{"title": "Build", "assignee": "developer"}])
    assert sorted(t.assignee for t in tasks) == ["developer", "qa"]


def test_the_planner_prompt_names_only_the_roles_that_close_tasks():
    prompt = SprintPlanner.system_prompt
    assert "assignee must be developer or qa" in prompt
    assert "architect" not in prompt.split("assignee")[1].split("\n- ")[0]


def test_every_planned_story_can_be_completed(db: Session, project: m.Project):
    """With the mock planner every story gets a task for each of the two agents that close tasks."""
    ScrumMasterAgent().run(db, project.id, PLANNING)
    planned = repo.current_sprint(db, project.id).stories
    assert planned
    for story in planned:
        assert {t.assignee for t in story.tasks} == CLOSERS


def test_story_without_tasks_gets_default_tasks(db: Session, project: m.Project, monkeypatch):
    first = repo.backlog(db, project.id)[0]
    reply = json.dumps({"goal": "G", "story_ids": [first.id], "tasks": []})
    llm = LLMClient(mock=False, use_cache=False)
    monkeypatch.setattr(llm, "_call", lambda system, prompt, stats: reply)
    ScrumMasterAgent(llm).run(db, project.id, PLANNING)
    assert len(repo.current_sprint(db, project.id).stories[0].tasks) == 2


def test_planning_with_empty_backlog_creates_no_sprint(db: Session):
    p = repo.create_project(db, "x", "y")
    ScrumMasterAgent().run(db, p.id, PLANNING)
    assert repo.current_sprint(db, p.id) is None
    assert "sprint_skipped" in [e.kind for e in repo.events_since(db, p.id)]


def test_standup_summarises_task_states_and_snapshots_burndown(db: Session, project: m.Project):
    sm = ScrumMasterAgent()
    sm.run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    for t in sprint.stories[0].tasks:
        Tools(db, project.id, "developer").update_task(t.id, "done")
    out = sm.run(db, project.id, REVIEW)
    assert out.yesterday and out.today
    events = repo.events_since(db, project.id)
    assert "standup" in [e.kind for e in events]
    snap = [e for e in events if e.kind == "burndown_snapshot"][-1]
    assert snap.payload["remaining"] == 2  # the 3-point story is done, 2 points are left


def test_burndown_data_tracks_remaining_points(db: Session, project: m.Project):
    sm = ScrumMasterAgent()
    sm.run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    sm.run(db, project.id, REVIEW)  # nothing done yet
    for story in sprint.stories:
        for t in story.tasks:
            Tools(db, project.id, "developer").update_task(t.id, "done")
    sm.run(db, project.id, REVIEW)
    data = repo.burndown(db, sprint)
    assert data["total_points"] == 5 and data["remaining_points"] == 0
    assert data["actual"] == [5, 0]
    assert data["ideal"] == [5.0, 0.0]


def test_retro_is_saved_and_closes_sprint(db: Session, project: m.Project):
    sm = ScrumMasterAgent()
    sm.run(db, project.id, PLANNING)
    sm.run(db, project.id, RETRO)
    sprint = repo.current_sprint(db, project.id)
    assert sprint.status == "done"
    assert sprint.retro["actions"] and sprint.retro["went_well"] and sprint.retro["went_wrong"]


def test_retro_actions_are_injected_into_next_sprint_prompt(db: Session, project: m.Project):
    sm = ScrumMasterAgent()
    first, _ = repo.backlog(db, project.id)
    sm.run(db, project.id, {**PLANNING, "capacity": 3})  # sprint 1 takes one story
    sm.run(db, project.id, RETRO)
    action = repo.current_sprint(db, project.id).retro["actions"][0]
    prompt = SprintPlanner().build_prompt(db, project.id, PLANNING)
    assert action in prompt
    # nothing was finished, so the retro returned the story to the backlog, marked as carried over
    assert f"{first.title} (carried over)" in prompt


def test_first_sprint_prompt_has_no_retro_section(db: Session, project: m.Project):
    assert "Retro actions" not in SprintPlanner().build_prompt(db, project.id, PLANNING)


def test_unknown_phase_is_rejected(db: Session, project: m.Project):
    with pytest.raises(ValueError):
        ScrumMasterAgent().run(db, project.id, {"phase": "release"})


def test_full_flow_through_orchestrator(db: Session):
    p = repo.create_project(db, "Todo", "A simple to-do app")
    assert isinstance(AGENTS["scrum_master"], ScrumMasterAgent)
    Orchestrator(db, AGENTS).run_to_end(p.id)
    assert p.phase == Phase.DONE
    sprint = repo.current_sprint(db, p.id)
    assert sprint.status == "done" and sprint.stories and sprint.retro["actions"]
    kinds = [e.kind for e in repo.events_since(db, p.id)]
    for k in ("sprint_created", "standup", "burndown_snapshot", "retro_saved"):
        assert k in kinds


# --- parking stuck stories, filling capacity, fresh attempts ---------------------------------


def _story(t: Tools, epic_id: int, title: str, points: int, priority: int = 1) -> m.UserStory:
    return t.create_story(epic_id, title=title, points=points, priority=priority)


def _carry_over(db: Session, story: m.UserStory, times: int, retries: int = 3) -> m.Bug:
    """A story that was carried over `times` times with a bug that used its attempts."""
    t = Tools(db, story.epic.project_id, "scrum_master")
    t.create_task(story.id, "Implement", "developer")
    t.create_task(story.id, "Test", "qa")
    for _ in range(times):
        t.log("story_carried_over", story.title, story_id=story.id)
    bug = Tools(db, story.epic.project_id, "qa").report_bug(story.id, "tests.x: broken")
    return repo.update(db, bug, retries=retries)


@pytest.fixture
def backlog5(db: Session):
    """A stuck 3-point story (P1) and three more stories: 3, 3 and 2 points."""
    p = repo.create_project(db, "Library", "A library")
    t = Tools(db, p.id, "product_owner")
    epic = t.create_epic("Core")
    stuck = _story(t, epic.id, "Add a Book", 3, 1)
    rest = [_story(t, epic.id, "Borrow", 3, 2), _story(t, epic.id, "Return", 3, 2),
            _story(t, epic.id, "Overdue", 2, 3)]
    return p, stuck, rest


def _titles(stories) -> list[str]:
    return [s.title for s in stories]


def test_spare_capacity_is_filled_from_the_backlog(db: Session, backlog5):
    """A live sprint committed 3 of 5 points and left the rest empty."""
    p, stuck, _ = backlog5
    chosen = plan_stories(repo.unplanned_stories(db, p.id), [stuck.id], 8, set())
    assert _titles(chosen) == ["Add a Book", "Borrow", "Overdue"]  # 3 + 3 + 2; Return would be 9
    assert sum(s.points for s in chosen) <= 8


def test_a_story_carried_over_twice_with_an_open_bug_is_blocked(db: Session, backlog5):
    p, stuck, _ = backlog5
    _carry_over(db, stuck, times=2)
    assert _blocked_ids(db, p.id) == {stuck.id}


@pytest.mark.parametrize("times", [0, 1])
def test_a_story_is_not_blocked_before_its_second_carry_over(db: Session, backlog5, times: int):
    p, stuck, _ = backlog5
    _carry_over(db, stuck, times=times)
    assert _blocked_ids(db, p.id) == set()


def test_a_fixed_bug_does_not_block_a_story(db: Session, backlog5):
    p, stuck, _ = backlog5
    bug = _carry_over(db, stuck, times=3)
    repo.update(db, bug, status="fixed")
    assert _blocked_ids(db, p.id) == set()


def test_a_blocked_story_is_planned_after_other_work(db: Session, backlog5):
    """The stuck story used both of its sprints; the rest of the backlog moves first."""
    p, stuck, _ = backlog5
    _carry_over(db, stuck, times=2)
    pool = repo.unplanned_stories(db, p.id)
    blocked = _blocked_ids(db, p.id)
    assert _titles(plan_stories(pool, [stuck.id], 5, blocked)) == ["Borrow", "Overdue"]
    assert _titles(plan_stories(pool, [stuck.id], 8, blocked)) == ["Borrow", "Return", "Overdue"]
    everything = _titles(plan_stories(pool, [stuck.id], 11, blocked))
    assert everything[-1] == "Add a Book"  # last, not first


def test_a_blocked_story_is_still_planned_when_nothing_else_is_left(db: Session):
    p = repo.create_project(db, "Library", "A library")
    t = Tools(db, p.id, "product_owner")
    only = _story(t, t.create_epic("Core").id, "Add a Book", 3)
    _carry_over(db, only, times=2)
    assert _titles(plan_stories(repo.unplanned_stories(db, p.id), [only.id], 5,
                                _blocked_ids(db, p.id))) == ["Add a Book"]


def test_a_rejected_plan_is_not_topped_up(db: Session, backlog5):
    p, stuck, _ = backlog5
    chosen = plan_stories(repo.unplanned_stories(db, p.id), [stuck.id], 11, set(), fill=False)
    assert _titles(chosen) == ["Add a Book"]  # the human asked for less


def test_the_planner_prompt_marks_blocked_stories(db: Session, backlog5):
    p, stuck, _ = backlog5
    _carry_over(db, stuck, times=2)
    prompt = SprintPlanner().build_prompt(db, p.id, PLANNING)
    assert f"{stuck.id} | 1 | 3 | Add a Book (carried over) (blocked)" in prompt
    assert "marked (blocked)" in SprintPlanner.system_prompt


def test_a_carried_over_story_gets_fresh_fix_attempts(db: Session, backlog5):
    p, stuck, _ = backlog5
    bug = _carry_over(db, stuck, times=1, retries=3)
    ScrumMasterAgent().run(db, p.id, {**PLANNING, "capacity": 5})
    db.refresh(bug)
    assert bug.retries == 0 and bug.status == "open"
    reset = [e for e in repo.events_since(db, p.id) if e.kind == "bug_attempts_reset"]
    assert len(reset) == 1 and reset[0].payload["bug_ids"] == [bug.id]


def test_a_story_that_was_not_carried_over_keeps_its_attempts(db: Session, backlog5):
    p, stuck, _ = backlog5
    t = Tools(db, p.id, "qa")
    bug = repo.update(db, t.report_bug(stuck.id, "tests.x: broken"), retries=2)
    ScrumMasterAgent().run(db, p.id, {**PLANNING, "capacity": 5})
    db.refresh(bug)
    assert bug.retries == 2  # no tasks yet: planned for the first time, nothing to reset
