"""The process levers change what the agents do: fix-retry limit, test-first, working agreements."""

import pytest
from sqlalchemy.orm import Session

from workbench import runner
from workbench.agents.developer import DeveloperAgent
from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.qa import QAAgent
from workbench.agents.scrum_master import ScrumMasterAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.workspace import Workspace

EXECUTION = {"name": "execution", "phase": "execution"}
AGREEMENTS = "Team working agreements (from the last retrospective):"


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


def story_of(db: Session, project: m.Project) -> m.UserStory:
    return repo.backlog(db, project.id)[0]


def set_process(db: Session, project: m.Project, **levers) -> None:
    """Record the sprint's process the way sprint planning does."""
    sprint = repo.current_sprint(db, project.id)
    process = {"capacity": 10, "max_fix_retries": 3, "test_first": False, "guidelines": [],
               **levers}
    Tools(db, project.id, "scrum_master").log(
        "sprint_planned", "Sprint 1", sprint_id=sprint.id, number=1,
        story_ids=[s.id for s in repo.backlog(db, project.id) if s.sprint_id == sprint.id],
        committed_points=3, capacity=process["capacity"], process=process)


def kinds(db: Session, project: m.Project) -> list[str]:
    return [e.kind for e in repo.events_since(db, project.id)]


def spy(agent, monkeypatch) -> list[str]:
    """Collect the user prompts an agent sends to its LLM client."""
    prompts: list[str] = []
    original = agent.llm.complete_json

    def wrapper(system, user, *args, **kwargs):
        prompts.append(user)
        return original(system, user, *args, **kwargs)

    monkeypatch.setattr(agent.llm, "complete_json", wrapper)
    return prompts


def always_failing(monkeypatch) -> None:
    failing = runner.TestResult(passed=0, failures=[runner.Failure("tests.test_x", "boom")])
    monkeypatch.setattr(runner, "run_pytest", lambda *args, **kwargs: failing)


# --- max_fix_retries ------------------------------------------------------------------------


@pytest.mark.parametrize("limit, runs", [(1, 2), (2, 3), (None, 4)])
def test_fix_retry_limit_comes_from_the_sprint_process(db: Session, project: m.Project,
                                                       monkeypatch, limit, runs):
    if limit is not None:  # no process recorded: the default of 3 applies
        set_process(db, project, max_fix_retries=limit)
    always_failing(monkeypatch)
    developer = DeveloperAgent()
    developer.run(db, project.id, EXECUTION)
    QAAgent(developer=developer).run(db, project.id, EXECUTION)

    (bug,) = repo.bugs(db, project.id)
    assert bug.status == "open" and bug.retries == runs - 1
    found = kinds(db, project)
    assert found.count("test_run") == runs and "bugs_left_open" in found


def test_bug_past_the_process_limit_is_not_retried(db: Session, project: m.Project):
    set_process(db, project, max_fix_retries=1)
    developer = DeveloperAgent()
    developer.run(db, project.id, EXECUTION)
    bug = Tools(db, project.id, "qa").report_bug(story_of(db, project).id, "Broken")
    repo.update(db, bug, retries=1)
    developer.run(db, project.id, EXECUTION)
    assert "bug_retry_limit" in kinds(db, project)
    assert len(Workspace(project.id).history()) == 1  # no fix commit


def test_a_task_value_beats_the_process(db: Session, project: m.Project, monkeypatch):
    set_process(db, project, max_fix_retries=1)
    always_failing(monkeypatch)
    developer = DeveloperAgent()
    developer.run(db, project.id, EXECUTION)
    qa = QAAgent(developer=developer)
    qa.run(db, project.id, {**EXECUTION, "max_fix_retries": 2})
    assert repo.bugs(db, project.id)[0].retries == 2


def test_developer_prompt_shows_the_attempt_limit(db: Session, project: m.Project, monkeypatch):
    set_process(db, project, max_fix_retries=2)
    developer = DeveloperAgent()
    developer.run(db, project.id, EXECUTION)
    Tools(db, project.id, "qa").report_bug(story_of(db, project).id, "Broken")
    prompts = spy(developer, monkeypatch)
    developer.run(db, project.id, EXECUTION)
    assert "(attempt 1 of 2)" in prompts[-1]


# --- test-first -----------------------------------------------------------------------------


def test_test_first_writes_the_tests_before_the_code(db: Session, project: m.Project,
                                                     monkeypatch):
    set_process(db, project, test_first=True)
    developer = DeveloperAgent()
    qa = QAAgent(developer=developer)
    assert developer.test_writer == qa.write_tests
    dev_prompts, qa_prompts = spy(developer, monkeypatch), spy(qa, monkeypatch)

    developer.run(db, project.id, EXECUTION)
    story = story_of(db, project)
    history = list(reversed(Workspace(project.id).history()))  # oldest first
    assert history == [f"Tests for story #{story.id}: Create an item",
                       f"Story #{story.id}: Create an item"]
    assert "tests_written_first" in kinds(db, project)
    assert "There is no implementation yet" in qa_prompts[0]
    assert "Code to test:" not in qa_prompts[0]
    assert "Tests you must make pass (do not edit them):" in dev_prompts[0]
    assert f"tests/test_story_{story.id}.py" in dev_prompts[0]

    qa.run(db, project.id, EXECUTION)  # the tests exist but have never run
    runs = [e.payload for e in repo.events_since(db, project.id) if e.kind == "test_run"]
    assert len(runs) == 1 and runs[0]["ok"] is True
    assert len(qa_prompts) == 1  # QA did not write the tests a second time
    db.refresh(story)
    assert {t.status for t in story.tasks} == {"done"}


def test_test_first_off_keeps_the_order(db: Session, project: m.Project, monkeypatch):
    set_process(db, project, test_first=False)
    developer = DeveloperAgent()
    qa = QAAgent(developer=developer)
    dev_prompts = spy(developer, monkeypatch)
    developer.run(db, project.id, EXECUTION)
    qa.run(db, project.id, EXECUTION)
    story = story_of(db, project)
    history = list(reversed(Workspace(project.id).history()))
    assert history == [f"Story #{story.id}: Create an item",
                       f"Tests for story #{story.id}: Create an item"]
    assert "tests_written_first" not in kinds(db, project)
    assert "Tests you must make pass" not in dev_prompts[0]


def test_test_first_needs_a_test_writer(db: Session, project: m.Project):
    set_process(db, project, test_first=True)
    DeveloperAgent().run(db, project.id, EXECUTION)  # no QA attached
    assert "tests_written_first" not in kinds(db, project)
    assert len(Workspace(project.id).history()) == 1


def test_qa_picks_stories_with_tests_that_never_ran(db: Session, project: m.Project):
    developer = DeveloperAgent()
    qa = QAAgent(developer=developer)
    developer.run(db, project.id, EXECUTION)
    story = story_of(db, project)
    qa.write_tests(db, project.id, {**EXECUTION, "story_id": story.id})
    assert [s.id for s in qa.stories_to_test(db, project.id, EXECUTION)] == [story.id]
    qa.run(db, project.id, EXECUTION)
    assert qa.stories_to_test(db, project.id, EXECUTION) == []


def test_qa_retests_a_story_whose_code_changed_after_its_last_run(db: Session,
                                                                  project: m.Project):
    """A carried-over bug is fixed in the Developer's turn, before QA runs (issue #39)."""
    developer = DeveloperAgent()
    qa = QAAgent(developer=developer)
    developer.run(db, project.id, EXECUTION)
    qa.run(db, project.id, EXECUTION)
    story = story_of(db, project)
    assert qa.stories_to_test(db, project.id, EXECUTION) == []
    bug = Tools(db, project.id, "qa").report_bug(story.id, "boom")  # open, tests ran before
    developer.run(db, project.id, EXECUTION)  # fixes the bug and commits
    assert db.get(m.Bug, bug.id).status == "fixed"
    assert [s.id for s in qa.stories_to_test(db, project.id, EXECUTION)] == [story.id]
    qa.run(db, project.id, EXECUTION)
    assert qa.stories_to_test(db, project.id, EXECUTION) == []  # the run came after the commit


# --- working agreements ---------------------------------------------------------------------


def test_agreements_end_every_agent_prompt(db: Session, project: m.Project, monkeypatch):
    set_process(db, project, guidelines=["Keep functions small", "Review every diff"])
    developer = DeveloperAgent()
    prompts = spy(developer, monkeypatch)
    developer.run(db, project.id, EXECUTION)
    assert prompts[0].endswith(f"\n\n{AGREEMENTS}\n- Keep functions small\n- Review every diff")


def test_no_agreements_block_without_guidelines(db: Session, project: m.Project, monkeypatch):
    developer = DeveloperAgent()
    prompts = spy(developer, monkeypatch)
    developer.run(db, project.id, EXECUTION)
    assert AGREEMENTS not in prompts[0]


def test_planning_uses_the_agreements_the_retro_adds(db: Session, project: m.Project,
                                                     monkeypatch):
    Tools(db, project.id, "product_owner").create_story(
        repo.epics(db, project.id)[0].id, title="Delete an item", points=2)
    sprint = repo.current_sprint(db, project.id)
    Tools(db, project.id, "scrum_master").save_retro(sprint.id, {
        "process_changes": {"add_guidelines": ["Keep functions small"]}})
    sm = ScrumMasterAgent()
    prompts = spy(sm, monkeypatch)
    sm.run(db, project.id, {"name": "sprint_planning", "phase": "sprint_planning"})
    assert prompts[0].endswith(f"{AGREEMENTS}\n- Keep functions small")


def test_product_owner_prompt_has_no_agreements(db: Session, monkeypatch):
    p = repo.create_project(db, "Todo", "A simple to-do app")
    sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, goal="G"))
    Tools(db, p.id, "scrum_master").log(
        "sprint_planned", "Sprint 1", sprint_id=sprint.id, number=1, story_ids=[],
        committed_points=0, capacity=10, process={"guidelines": ["Keep functions small"]})
    po = ProductOwnerAgent()
    prompts = spy(po, monkeypatch)
    po.run(db, p.id)
    assert AGREEMENTS not in prompts[0]
