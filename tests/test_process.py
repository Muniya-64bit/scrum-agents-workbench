"""Process levers: bounds, the retro advisor, the next sprint's process and the carry-over."""

import pytest
from sqlalchemy.orm import Session

from workbench import config
from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.scrum_master import ScrumMasterAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.process import (
    ProcessConfig,
    current_process,
    effective_process,
    next_process,
    suggest_process_changes,
)
from workbench.schemas import ProcessChanges, RetroOutput

PLANNING = {"name": "sprint_planning", "phase": "sprint_planning"}
RETRO = {"name": "retro", "phase": "retro"}

CFG = ProcessConfig(capacity=10, max_fix_retries=3, test_first=False, guidelines=[])
TEST_FIRST_RULE = "Write the acceptance tests first and make them pass before committing"


def metrics_of(**kw) -> dict:
    base = {"committed_points": 10, "completed_points": 10, "bugs_reported": 0,
            "first_pass_yield": 1.0, "retry_limit_hits": 0}
    return {**base, **kw}


# --- the advisor --------------------------------------------------------------------------


@pytest.mark.parametrize("metrics, cfg, expected", [
    # rule 1: commit to the velocity that was delivered
    (metrics_of(completed_points=7), CFG, {"capacity": 7}),
    (metrics_of(completed_points=0), CFG, {}),
    (metrics_of(completed_points=2), CFG, {"capacity": 3}),
    (metrics_of(completed_points=10), CFG, {}),
    # rule 2: defects escaped
    (metrics_of(bugs_reported=2), CFG, {"test_first": True,
                                         "add_guidelines": [TEST_FIRST_RULE]}),
    (metrics_of(first_pass_yield=0.5), CFG, {"test_first": True,
                                              "add_guidelines": [TEST_FIRST_RULE]}),
    (metrics_of(first_pass_yield=None), CFG, {}),
    (metrics_of(bugs_reported=2), CFG.model_copy(update={"test_first": True}), {}),
    # rule 3: the retry limit was hit
    (metrics_of(retry_limit_hits=1), CFG, {"max_fix_retries": 4}),
    (metrics_of(retry_limit_hits=1), CFG.model_copy(update={"max_fix_retries": 5}),
     {"max_fix_retries": 5}),
])
def test_suggest_process_changes_rules(metrics, cfg, expected):
    got = suggest_process_changes(metrics, cfg).model_dump(exclude_defaults=True)
    got.pop("reason")
    assert got == expected


def test_suggest_process_changes_joins_reasons():
    ch = suggest_process_changes(
        metrics_of(completed_points=6, bugs_reported=1, retry_limit_hits=2), CFG)
    assert (ch.capacity, ch.test_first, ch.max_fix_retries) == (6, True, 4)
    assert ch.reason == ("Commit to last sprint's velocity (yesterday's weather); "
                         "Defects escaped into testing; prevent them instead (test-first); "
                         "A bug hit the fix-retry limit")


def test_suggest_process_changes_keeps_a_working_process():
    ch = suggest_process_changes(metrics_of(), CFG)
    assert ch.reason == "The process worked; keep it"
    assert ch.capacity is None and ch.test_first is None and ch.max_fix_retries is None


# --- applying changes ---------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [(99, 40), (12, 12), (8, 8)])
def test_apply_clamps_capacity(value, expected):
    new, diff = CFG.apply(ProcessChanges(capacity=value))
    assert new.capacity == expected
    assert diff == ({"capacity": [10, expected]} if expected != 10 else {})


@pytest.mark.parametrize("value", [1, 3, 5, 6])
def test_one_retrospective_cuts_capacity_by_at_most_30_percent(value):
    """A live retro halved the capacity after one weak sprint, which left most of the backlog
    unstarted. A cut now stops at 70 percent of the current capacity."""
    new, diff = CFG.apply(ProcessChanges(capacity=value))
    assert new.capacity == 7 and diff == {"capacity": [10, 7]}


def test_the_cut_never_goes_below_the_minimum_capacity():
    small = CFG.model_copy(update={"capacity": 4})
    assert small.apply(ProcessChanges(capacity=3))[0].capacity == 3  # 70% of 4 is 2.8, floor is 3
    assert small.apply(ProcessChanges(capacity=1))[0].capacity == 3


def test_raising_the_capacity_is_not_limited():
    assert CFG.apply(ProcessChanges(capacity=40))[0].capacity == 40


@pytest.mark.parametrize("value, expected", [(0, 1), (9, 5), (2, 2)])
def test_apply_clamps_retries(value, expected):
    new, diff = CFG.apply(ProcessChanges(max_fix_retries=value))
    assert new.max_fix_retries == expected
    assert diff == {"max_fix_retries": [3, expected]}


def test_apply_diff_lists_only_changed_levers():
    new, diff = CFG.apply(ProcessChanges(capacity=7, test_first=True))
    assert diff == {"capacity": [10, 7], "test_first": [False, True]}
    assert new.max_fix_retries == 3 and new.guidelines == []
    assert CFG.apply(ProcessChanges(capacity=10, test_first=False))[1] == {}


def test_apply_normalises_guidelines():
    start = ProcessConfig(guidelines=["Keep functions small"])
    new, diff = start.apply(ProcessChanges(add_guidelines=[
        "  keep   FUNCTIONS small ", "", "   ", "x" * 300, "Review   every\ndiff"]))
    assert new.guidelines == ["Keep functions small", "x" * 200, "Review every diff"]
    assert diff == {"guidelines": [["Keep functions small"], new.guidelines]}


def test_apply_keeps_the_last_five_guidelines():
    start = ProcessConfig(guidelines=["a", "b", "c", "d"])
    new, _ = start.apply(ProcessChanges(add_guidelines=["e", "f", "g"]))
    assert new.guidelines == ["c", "d", "e", "f", "g"]


def test_defaults_come_from_config(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_CAPACITY", 8)
    monkeypatch.setattr(config, "DEFAULT_MAX_FIX_RETRIES", 2)
    assert ProcessConfig.defaults() == ProcessConfig(capacity=8, max_fix_retries=2)


# --- next_process -------------------------------------------------------------------------


@pytest.fixture
def project(db: Session) -> m.Project:
    p = repo.create_project(db, "Todo", "A simple to-do app")
    ProductOwnerAgent().run(db, p.id)
    return p


def test_next_process_without_sprints_is_the_default(db: Session, project: m.Project):
    assert next_process(db, project.id) == (ProcessConfig.defaults(), {}, "")
    assert current_process(db, project.id) == ProcessConfig.defaults()


def test_next_process_applies_the_retro_changes(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    Tools(db, project.id, "scrum_master").save_retro(sprint.id, {
        "process_changes": {"capacity": 7, "test_first": True, "reason": "Fewer, better"}})
    cfg, diff, reason = next_process(db, project.id)
    assert (cfg.capacity, cfg.test_first) == (7, True)
    assert diff == {"capacity": [10, 7], "test_first": [False, True]}
    assert reason == "Fewer, better"
    assert current_process(db, project.id).capacity == 10  # the sprint that ran
    assert effective_process(db, project.id, "sprint_planning").capacity == 7
    assert effective_process(db, project.id, "execution").capacity == 10


def test_next_process_without_changes_keeps_the_config(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    Tools(db, project.id, "scrum_master").save_retro(sprint.id, {"went_well": ["x"]})
    cfg, diff, reason = next_process(db, project.id)
    assert cfg == current_process(db, project.id) and diff == {} and reason == ""


# --- the retro and the next planning, end to end ------------------------------------------


def plan_and_work(db: Session, project: m.Project) -> tuple[m.UserStory, m.UserStory]:
    """Sprint 1 with both mock stories (3 + 2 points). The first is finished, the second has
    code but its QA task is not done and its first test run failed."""
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    done_story, open_story = sprint.stories
    qa, dev = Tools(db, project.id, "qa"), Tools(db, project.id, "developer")
    for t in done_story.tasks:
        dev.update_task(t.id, "done")
    qa.log("test_run", "2 passed", story_id=done_story.id, passed=2, failed=0, ok=True)
    for t in open_story.tasks:
        dev.update_task(t.id, "done" if t.assignee == "developer" else "testing")
    qa.log("test_run", "0 passed, 1 failed", story_id=open_story.id, passed=0, failed=1, ok=False)
    return done_story, open_story


def test_retro_carries_over_and_proposes_process_changes(db: Session, project: m.Project):
    done_story, open_story = plan_and_work(db, project)
    sprint = repo.current_sprint(db, project.id)
    ScrumMasterAgent().run(db, project.id, RETRO)

    db.refresh(open_story)
    db.refresh(done_story)
    assert open_story.sprint_id is None and open_story.status == "backlog"
    assert done_story.sprint_id == sprint.id
    kinds = [(e.kind, e.payload) for e in repo.events_since(db, project.id)]
    assert ("story_carried_over", {"story_id": open_story.id, "from_sprint_id": sprint.id}) \
        in kinds

    retro = repo.current_sprint(db, project.id).retro
    changes = retro["process_changes"]
    assert changes["capacity"] == done_story.points == 3
    assert changes["test_first"] is True and changes["add_guidelines"] == [TEST_FIRST_RULE]
    assert retro["metrics"]["completed_points"] == 3
    assert retro["metrics"]["committed_points"] == 5
    assert retro["actions"] and retro["went_well"]


def test_retro_runs_once(db: Session, project: m.Project):
    plan_and_work(db, project)
    ScrumMasterAgent().run(db, project.id, RETRO)
    before = repo.current_sprint(db, project.id).retro
    n_events = len(repo.events_since(db, project.id))
    out = ScrumMasterAgent().run(db, project.id, RETRO)
    after = repo.events_since(db, project.id)[n_events:]
    assert [e.kind for e in after] == ["retro_exists"]
    assert repo.current_sprint(db, project.id).retro == before
    assert isinstance(out, RetroOutput) and out.actions == before["actions"]
    assert out.process_changes.capacity == 3


def test_next_sprint_is_planned_with_the_retro_levers(db: Session, project: m.Project,
                                                      monkeypatch):
    done_story, open_story = plan_and_work(db, project)
    sm = ScrumMasterAgent()
    sm.run(db, project.id, RETRO)

    prompts = []
    original = sm.llm.complete_json

    def spy(system, user, *args, **kwargs):
        prompts.append(user)
        return original(system, user, *args, **kwargs)

    monkeypatch.setattr(sm.llm, "complete_json", spy)
    sm.run(db, project.id, PLANNING)

    sprint = repo.current_sprint(db, project.id)
    assert sprint.number == 2 and sprint.capacity == 7  # the proposed 3 is cut gently
    assert [s.id for s in sprint.stories] == [open_story.id]
    assert len(sprint.stories[0].tasks) == 2  # the carried story kept its tasks
    planned = [e for e in repo.events_since(db, project.id) if e.kind == "sprint_planned"][-1]
    expected = {"capacity": 7, "max_fix_retries": 3, "test_first": True,
                "guidelines": [TEST_FIRST_RULE]}
    assert planned.payload["process"] == expected
    diff = planned.payload["process_changes"]
    assert diff == {"capacity": [10, 7], "test_first": [False, True],
                    "guidelines": [[], [TEST_FIRST_RULE]]}
    assert planned.payload["process_reason"]
    changed = [e for e in repo.events_since(db, project.id) if e.kind == "process_changed"]
    assert len(changed) == 1 and changed[0].payload["diff"] == diff
    assert "Changed after the last retrospective" in prompts[-1]
    assert "(carried over)" in prompts[-1]
    assert current_process(db, project.id) == ProcessConfig(**expected)


def test_explicit_capacity_beats_the_retro(db: Session, project: m.Project):
    plan_and_work(db, project)
    sm = ScrumMasterAgent()
    sm.run(db, project.id, RETRO)
    sm.run(db, project.id, {**PLANNING, "capacity": 6})
    sprint = repo.current_sprint(db, project.id)
    assert sprint.capacity == 6
    planned = [e for e in repo.events_since(db, project.id) if e.kind == "sprint_planned"][-1]
    assert planned.payload["process"]["capacity"] == 6


def test_unplan_story_returns_it_to_the_backlog(db: Session, project: m.Project):
    ScrumMasterAgent().run(db, project.id, PLANNING)
    sprint = repo.current_sprint(db, project.id)
    story = sprint.stories[0]
    Tools(db, project.id, "scrum_master").unplan_story(story.id, sprint.id)
    assert story in repo.unplanned_stories(db, project.id)
