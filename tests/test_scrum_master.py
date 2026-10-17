import json

import pytest
from sqlalchemy.orm import Session

from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.registry import AGENTS
from workbench.agents.scrum_master import ScrumMasterAgent, SprintPlanner
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
    # unknown assignee falls back to developer; the story still gets its task
    assert [(t.title, t.assignee) for t in sprint.stories[0].tasks] == [("T", "developer")]


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
