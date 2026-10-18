"""Gate rejection, non-functional requirements, the backlog quality check and the process model
(issue #41)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from workbench import process_model, requirements
from workbench.agents.architect import SystemDesigner
from workbench.agents.registry import AGENTS
from workbench.agents.scrum_master import RetroAgent, SprintPlanner
from workbench.agents.tools import Tools
from workbench.api import main as api_main
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import Base, get_session
from workbench.orchestrator.engine import GATES, PHASE_AGENTS, Orchestrator, Phase

HANDBOOK = Path(__file__).resolve().parents[1] / "docs" / "process-handbook.md"
START, END = "<!-- generated:start -->", "<!-- generated:end -->"
GWT = "Given a list When I add an item Then it is shown"


def kinds(db: Session, project_id: int) -> list[str]:
    return [e.kind for e in repo.events_since(db, project_id)]


def last_of(db: Session, project_id: int, kind: str) -> m.Event:
    return [e for e in repo.events_since(db, project_id) if e.kind == kind][-1]


def story(**fields) -> m.UserStory:
    base = {"id": 1, "title": "Add item", "as_a": "user", "i_want": "to add an item",
            "so_that": "I remember it", "acceptance_criteria": [GWT], "points": 3}
    return m.UserStory(**{**base, **fields})


# --- backlog quality check ----------------------------------------------------------------------


def rules(stories, nfrs=()) -> list[str]:
    return [w["rule"] for w in requirements.check_backlog(list(stories), list(nfrs))]


def test_a_clean_backlog_has_no_warnings():
    nfr = {"category": "product", "requirement": "x", "measure": "under 300 ms"}
    assert rules([story(), story(id=2, title="Remove item")], [nfr]) == []


@pytest.mark.parametrize("fields, rule", [
    ({"acceptance_criteria": []}, "no_acceptance_criteria"),
    ({"acceptance_criteria": ["The item is saved"]}, "criterion_not_gwt"),
    ({"so_that": ""}, "incomplete_story"),
    ({"points": 4}, "points_not_fibonacci"),
    ({"i_want": "a fast and easy list"}, "vague_wording"),
])
def test_each_rule_flags_its_problem(fields, rule):
    assert rules([story(**fields)]) == [rule]


def test_large_stories_and_duplicates_are_flagged():
    assert rules([story(points=13), story(id=2, title=" add ITEM ")]) == [
        "story_too_big", "duplicate_title"]
    vague = requirements.check_backlog([story(title="Quick and simple add")], [])[0]
    assert (vague["story_id"], vague["detail"]) == (1, "quick, simple")


def test_an_nfr_without_a_number_is_not_measurable():
    warning = requirements.check_backlog([], [{"requirement": "Be usable", "measure": "nice"}])
    assert warning == [{"rule": "nfr_not_measurable", "story_id": None,
                        "message": requirements.RULES["nfr_not_measurable"],
                        "detail": "Be usable"}]


# --- Product Owner: NFRs and the check ----------------------------------------------------------


def test_the_product_owner_writes_nfrs_and_validates_the_backlog(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    Orchestrator(db, AGENTS).step(p.id)  # idea -> backlog
    nfrs = requirements.nfrs(db, p.id)
    assert [n["category"] for n in nfrs] == ["product", "organizational"]
    doc = repo.artifacts(db, p.id, "requirements")[0]
    assert doc.path == requirements.NFR_PATH and "| NFR-2 | organizational |" in doc.content
    check = requirements.latest_check(db, p.id)
    assert check == {"stories": 2, "flagged_stories": 0, "warnings": []}
    assert last_of(db, p.id, "backlog_validated").agent == "product_owner"
    assert "Non-functional requirements" in SystemDesigner().build_prompt(db, p.id, {})


def test_a_backlog_without_nfrs_or_a_check_reads_as_empty(db: Session):
    p = repo.create_project(db, "x", "y")
    assert requirements.nfrs(db, p.id) == [] and requirements.latest_check(db, p.id) is None
    assert "Non-functional" not in SystemDesigner().build_prompt(db, p.id, {})


def test_nfr_markdown_escapes_pipes():
    md = requirements.nfr_markdown([{"category": "product", "requirement": "a|b", "measure": "1"}])
    assert "| NFR-1 | product | a\\|b | 1 |" in md


# --- process model ------------------------------------------------------------------------------


def test_the_orchestrator_takes_agents_and_gates_from_the_model():
    assert PHASE_AGENTS[Phase.EXECUTION] == ["architect", "developer", "qa"]
    assert GATES == {Phase.SPRINT_PLANNING, Phase.REVIEW}
    assert [a.phase for a in process_model.MODEL] == [p.value for p in Phase][1:-1]
    for a in process_model.MODEL:
        assert a.responsible in a.agents
        assert sum("A" in v for v in a.raci.values()) == 1, a.phase  # exactly one accountable


def test_criteria_are_checked_and_logged_at_every_phase(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    checks = [e for e in repo.events_since(db, p.id) if e.kind.endswith("_criteria_checked")]
    assert len(checks) == 2 * 6  # entry and exit of six phases, one sprint
    assert all(not e.payload["unmet"] for e in checks), [e.payload for e in checks]


def test_unmet_criteria_are_reported_not_enforced(db: Session):
    p = repo.create_project(db, "x", "y")
    o = Orchestrator(db)  # stub agents: no backlog, no sprint
    o.step(p.id)
    o.step(p.id)  # sprint planning runs although there is nothing to plan
    entry = last_of(db, p.id, "entry_criteria_checked")
    assert entry.payload["unmet"] == ["stories_to_plan"] and entry.message.startswith("0 of 1")
    assert p.awaiting_approval
    assert process_model.check(db, p.id, "done", "entry") == []
    assert process_model.log_check(db, p.id, "idea", "exit") == []


def test_the_handbook_tables_match_the_model():
    text = HANDBOOK.read_text(encoding="utf-8")
    generated = text.split(START, 1)[1].split(END, 1)[0].strip()
    assert generated == process_model.handbook_tables().strip(), (
        "docs/process-handbook.md is out of date: run python scripts/process_handbook.py")


# --- gate rejection -----------------------------------------------------------------------------


def test_rejecting_the_sprint_plan_plans_the_same_sprint_again(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    o = Orchestrator(db, AGENTS)
    o.step(p.id)
    o.step(p.id)  # sprint 1 planned with both stories
    sprint = repo.current_sprint(db, p.id)
    assert len(sprint.stories) == 2 and repo.tasks(db, p.id)
    o.approve(p.id, approved=False, comment="Too much for one sprint")
    assert sprint.status == "replanning" and not sprint.stories and not repo.tasks(db, p.id)
    assert o.replanning(p.id) and o.next_phase(p) == Phase.SPRINT_PLANNING
    prompt = SprintPlanner().build_prompt(db, p.id, {"phase": "sprint_planning"})
    assert "rejected your previous plan" in prompt and "Too much for one sprint" in prompt

    o.step(p.id)  # plans sprint 1 again, with less
    assert [s.number for s in repo.sprints(db, p.id)] == [1]
    assert sprint.status == "active" and len(sprint.stories) == 1
    assert "sprint_replanned" in kinds(db, p.id) and not o.replanning(p.id)
    o.approve(p.id)
    assert o.next_phase(p) == Phase.EXECUTION
    assert o.run_to_end(p.id).phase == Phase.DONE


def test_rejecting_without_a_reason_still_replans(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    o = Orchestrator(db, AGENTS)
    o.step(p.id)
    o.step(p.id)
    o.approve(p.id, approved=False)
    prompt = SprintPlanner().build_prompt(db, p.id, {"phase": "sprint_planning"})
    assert "No reason given" in prompt


def test_a_rejected_plan_keeps_the_tasks_of_carried_over_stories(db: Session):
    p = repo.create_project(db, "x", "y")
    po, sm = Tools(db, p.id, "product_owner"), Tools(db, p.id, "scrum_master")
    epic = po.create_epic("E")
    old, new = (po.create_story(epic.id, title=t, points=2) for t in ("Old", "New"))
    s1 = sm.create_sprint("one")
    sm.add_story_to_sprint(s1.id, old.id)
    sm.create_task(old.id, "Build old", "developer")
    sm.unplan_story(old.id, s1.id)  # carried over
    s2 = sm.create_sprint("two")
    for s in (old, new):
        sm.add_story_to_sprint(s2.id, s.id)
    sm.create_task(new.id, "Build new", "developer")
    Tools(db, p.id, "orchestrator").reset_sprint_plan(s2.id, "no")
    assert [t.title for t in repo.tasks(db, p.id)] == ["Build old"]
    e = last_of(db, p.id, "sprint_plan_rejected")
    assert e.payload["story_ids"] == [old.id, new.id] and e.payload["reason"] == "no"


def test_rejecting_the_review_reaches_the_retrospective(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    o = Orchestrator(db, AGENTS)
    for _ in range(4):  # backlog, planning (approve), execution, review
        o.step(p.id)
        if p.awaiting_approval and p.phase == Phase.SPRINT_PLANNING:
            o.approve(p.id)
    assert p.phase == Phase.REVIEW
    o.approve(p.id, approved=False, comment="The list is not sorted")
    assert o.next_phase(p) == Phase.RETRO  # a rejected review does not loop
    prompt = RetroAgent().build_prompt(db, p.id, {"phase": "retro"})
    assert "REJECTED" in prompt and "The list is not sorted" in prompt
    o.step(p.id)  # retro
    retro = repo.current_sprint(db, p.id).retro
    assert "The sprint review was rejected: The list is not sorted" in retro["went_wrong"]
    assert any("review feedback" in a for a in retro["actions"])


def test_an_approved_review_adds_nothing_to_the_retrospective(db: Session):
    p = repo.create_project(db, "Todo", "A to-do app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    retro = repo.sprints(db, p.id)[0].retro
    assert not any("review" in w for w in retro["went_wrong"])


# --- API ----------------------------------------------------------------------------------------


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as s:
            yield s

    api_main.app.dependency_overrides[get_session] = override
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


def test_the_api_serves_nfrs_the_check_and_the_process_model(client):
    pid = client.post("/projects", json={"name": "n", "idea": "i"}).json()["id"]
    assert client.get(f"/projects/{pid}/backlog").json()["quality"] is None
    client.post(f"/projects/{pid}/advance")
    body = client.get(f"/projects/{pid}/backlog").json()
    assert len(body["nfrs"]) == 2 and body["quality"]["warnings"] == []
    model = client.get("/process/model").json()
    assert [a["phase"] for a in model][:2] == ["backlog", "sprint_planning"]
    assert model[1]["gate"] is True and model[1]["entry"][0]["id"] == "stories_to_plan"
