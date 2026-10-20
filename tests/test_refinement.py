"""Backlog refinement: before a sprint is planned the Product Owner fixes flagged stories."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from workbench.agents.product_owner import BacklogRefiner, ProductOwnerAgent, story_problems
from workbench.agents.registry import AGENTS
from workbench.agents.scrum_master import ScrumMasterAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.orchestrator.engine import Orchestrator, Phase
from workbench.schemas import RefinementOutput, StoryRefinement

PLANNING = {"name": "sprint_planning", "phase": "sprint_planning"}
GOOD = ["Given the app When I add a book Then it is listed",
        "Given the app When I add nothing Then I see an error"]


def _kinds(db: Session, project_id: int) -> list[str]:
    return [e.kind for e in repo.events_since(db, project_id)]


def _story(t: Tools, epic_id: int, title: str, criteria=GOOD, points: int = 3, priority: int = 1):
    return t.create_story(epic_id, title=title, as_a="librarian", i_want=f"to {title.lower()}",
                          so_that="the shelves stay in order", acceptance_criteria=list(criteria),
                          points=points, priority=priority)


@pytest.fixture
def clean(db: Session) -> m.Project:
    p = repo.create_project(db, "Library", "A library")
    t = Tools(db, p.id, "product_owner")
    _story(t, t.create_epic("Core").id, "Add a book")
    return p


@pytest.fixture
def flawed(db: Session) -> tuple[m.Project, m.UserStory, m.UserStory]:
    """One good story, one with a vague criterion and 13 points, one already in a sprint."""
    p = repo.create_project(db, "Library", "A library")
    t = Tools(db, p.id, "product_owner")
    epic = t.create_epic("Core")
    good = _story(t, epic.id, "Add a book")
    bad = _story(t, epic.id, "Borrow a book", criteria=["The book is borrowed quickly"],
                 points=13, priority=2)
    planned = _story(t, epic.id, "Return a book", criteria=["It works"], points=13)
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    repo.update(db, planned, sprint_id=sprint.id, status="sprint")
    return p, bad, good


def test_a_clean_backlog_is_not_refined_and_costs_no_model_call(db: Session, clean: m.Project):
    llm = LLMClient(mock=False, use_cache=False)
    llm._call = lambda *a: (_ for _ in ()).throw(AssertionError("no model call expected"))
    out = BacklogRefiner(llm).run(db, clean.id, PLANNING)
    assert out.summary == "Nothing to refine"
    assert "refinement_skipped" in _kinds(db, clean.id)
    assert "backlog_refined" not in _kinds(db, clean.id)


def test_flagged_stories_are_found_and_planned_ones_are_not(db: Session, flawed):
    p, bad, good = flawed
    problems = story_problems(db, p.id)
    assert set(problems) == {bad.id}  # the good story is clean; the planned one is out of scope
    assert {w["rule"] for w in problems[bad.id]} >= {"criterion_not_gwt", "story_too_big",
                                                     "vague_wording"}


def test_the_mock_refinement_fixes_the_flagged_story(db: Session, flawed):
    p, bad, good = flawed
    BacklogRefiner().run(db, p.id, PLANNING)
    db.refresh(bad)
    assert bad.points == 8  # 13 is too big and off the scale
    assert len(bad.acceptance_criteria) == 2
    assert all("Given" in c and "When" in c and "Then" in c for c in bad.acceptance_criteria)
    assert story_problems(db, p.id) == {}
    events = repo.events_since(db, p.id)
    (refined,) = [e for e in events if e.kind == "story_refined"]
    assert refined.payload["story_id"] == bad.id
    assert set(refined.payload["changes"]) == {"acceptance_criteria", "points"}
    assert refined.payload["changes"]["points"] == [13, 8]
    (summary,) = [e for e in events if e.kind == "backlog_refined"]
    assert summary.payload["refined"] == 1 and summary.payload["before"] > 0
    assert summary.payload["after"] == 0
    assert "backlog_validated" in [e.kind for e in events]  # the Backlog page shows the new check


def test_the_untouched_stories_stay_as_they_were(db: Session, flawed):
    p, bad, good = flawed
    BacklogRefiner().run(db, p.id, PLANNING)
    db.refresh(good)
    assert good.acceptance_criteria == GOOD and good.points == 3
    planned = [s for s in repo.backlog(db, p.id) if s.sprint_id is not None][0]
    assert planned.points == 13  # a story already in a sprint is not refined


def test_a_live_answer_is_applied_to_flagged_stories_only(db: Session, flawed, monkeypatch):
    p, bad, good = flawed
    reply = json.dumps({"summary": "s", "stories": [
        {"story_id": bad.id, "acceptance_criteria": GOOD, "points": 5, "priority": 1},
        {"story_id": 999, "acceptance_criteria": GOOD, "points": 2, "priority": 1},
        {"story_id": good.id, "acceptance_criteria": GOOD, "points": 8, "priority": 5}]})
    llm = LLMClient(mock=False, use_cache=False)
    prompts = []
    monkeypatch.setattr(llm, "_call",
                        lambda system, prompt, stats: (prompts.append(prompt), reply)[1])
    BacklogRefiner(llm).run(db, p.id, PLANNING)
    db.refresh(bad)
    db.refresh(good)
    assert (bad.points, bad.priority, bad.acceptance_criteria) == (5, 1, GOOD)
    assert (good.points, good.priority) == (3, 1)  # the check did not flag it: left alone
    assert f"{bad.id} | 2 | 13 | Borrow a book" in prompts[0]
    assert "PROBLEM: Story is larger than 8 points; split it" in prompts[0]
    assert "Add a book" not in prompts[0]  # the clean story is not shown


def test_a_refinement_must_follow_the_scale_and_give_two_criteria():
    ok = {"story_id": 1, "acceptance_criteria": GOOD, "points": 5, "priority": 2}
    assert StoryRefinement(**ok).points == 5
    with pytest.raises(ValidationError):
        StoryRefinement(**{**ok, "points": 4})  # not on the 1, 2, 3, 5, 8 scale
    with pytest.raises(ValidationError):
        StoryRefinement(**{**ok, "points": 13})
    with pytest.raises(ValidationError):
        StoryRefinement(**{**ok, "acceptance_criteria": [GOOD[0]]})
    with pytest.raises(ValidationError):
        StoryRefinement(**{**ok, "priority": 6})
    assert RefinementOutput().stories == []


def test_refine_story_changes_only_what_differs(db: Session, clean: m.Project):
    t = Tools(db, clean.id, "product_owner")
    story = repo.backlog(db, clean.id)[0]
    assert t.refine_story(story.id, points=3, priority=1) is None  # nothing changed
    assert "story_refined" not in _kinds(db, clean.id)
    assert t.refine_story(story.id, points=5, priority=1) is story
    (e,) = [e for e in repo.events_since(db, clean.id) if e.kind == "story_refined"]
    assert e.payload["changes"] == {"points": [3, 5]}


def test_the_product_owner_writes_the_backlog_and_refines_in_sprint_planning(
        db: Session, flawed):
    p, bad, good = flawed
    po = ProductOwnerAgent()
    assert po.run(db, p.id, PLANNING).summary.startswith("Refined")  # delegated to the refiner
    assert "backlog_refined" in _kinds(db, p.id)


def test_sprint_planning_refines_before_it_plans(db: Session, flawed):
    p, bad, good = flawed
    repo.update(db, p, phase="backlog")
    for s in repo.backlog(db, p.id):  # nothing is planned yet
        repo.update(db, s, sprint_id=None, status="backlog")
    Orchestrator(db, AGENTS).step(p.id)
    assert p.phase == Phase.SPRINT_PLANNING
    kinds = _kinds(db, p.id)
    assert kinds.index("backlog_refined") < kinds.index("sprint_planned")
    refiner = [e.agent for e in repo.events_since(db, p.id) if e.kind == "backlog_refined"]
    assert refiner == ["product_owner"]


def test_the_planner_still_plans_when_there_is_nothing_to_refine(db: Session, clean: m.Project):
    Orchestrator(db, AGENTS).run_to_end(clean.id)
    kinds = _kinds(db, clean.id)
    assert "refinement_skipped" in kinds and "sprint_planned" in kinds
    assert ScrumMasterAgent is not None
