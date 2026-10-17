from sqlalchemy.orm import Session

from tests.factories import build_two_sprint_project
from workbench import metrics
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.db import repo
from workbench.orchestrator.engine import Orchestrator


def _sprints(db: Session, ids: dict):
    return repo.sprints(db, ids["project"])


def test_sprint_one_metrics(db: Session):
    ids = build_two_sprint_project(db)
    s1 = _sprints(db, ids)[0]
    got = metrics.sprint_metrics(db, s1)
    expected = {
        "committed_points": 8, "committed_stories": 3,
        "completed_points": 5, "completed_stories": 2,  # A (3) + B (2) are done, C is not
        "commitment_reliability": 0.625,  # 5 / 8
        "carried_over_stories": 1,  # C
        "test_runs": 4,  # A 1, B 2, C 1
        "first_pass_yield": 0.333,  # only A passed its first run: 1 of 3 stories
        "test_pass_rate": 0.8,  # last runs: A 2/0, B 2/0, C 0/1 -> 4 passed of 5
        "bugs_reported": 2,  # b1 and c1
        "bugs_fixed_in_sprint": 1,  # b1 verified
        "bugs_open_at_end": 1,  # c1
        "fix_attempts": 2,  # b1 fixed, c1 failed
        "retry_limit_hits": 1,  # c1 is open after 1 attempt and the sprint's limit is 1
        "llm_calls": 3, "input_tokens": 10000, "output_tokens": 2000,  # developer 2 + qa 1
        "cache_hits": 1, "llm_invalid_outputs": 1,
        "est_cost_usd": 0.04,  # 10000 * 2/1e6 + 2000 * 10/1e6
        "cost_per_completed_point": 0.008,  # 0.04 / 5
        "trace_completeness": 0.333,  # only A has design, code and test
        "ac_coverage": 0.4,  # A: min(2, 2) of 5 criteria
        "closed": True, "goal": "S1",
    }
    assert {k: got[k] for k in expected} == expected
    assert got["process"]["max_fix_retries"] == 1


def test_sprint_two_metrics(db: Session):
    ids = build_two_sprint_project(db)
    got = metrics.sprint_metrics(db, _sprints(db, ids)[1])
    expected = {
        "committed_points": 5, "completed_points": 5, "commitment_reliability": 1.0,
        "carried_over_stories": 0,
        "test_runs": 2,  # C and D
        "first_pass_yield": 1.0, "test_pass_rate": 1.0,
        "bugs_reported": 0,  # c1 was reported in sprint 1
        "bugs_fixed_in_sprint": 1,  # c1 verified now
        "bugs_open_at_end": 0, "fix_attempts": 1, "retry_limit_hits": 0,
        "est_cost_usd": 0.02,  # 5000 * 2/1e6 + 1000 * 10/1e6
        "cost_per_completed_point": 0.004,  # 0.02 / 5
    }
    assert {k: got[k] for k in expected} == expected


def test_burndown_series(db: Session):
    ids = build_two_sprint_project(db)
    s1, s2 = _sprints(db, ids)
    b1 = metrics.burndown(db, s1)
    assert [p["remaining"] for p in b1["series"]] == [8, 5, 3, 3]
    labels = [p["label"] for p in b1["series"]]
    assert labels[0] == "Sprint start" and labels[3] == "Sprint end"
    assert labels[1].startswith("Done: A") and labels[2].startswith("Done: B")
    assert b1["committed_points"] == 8 and b1["remaining_points"] == 3 and b1["closed"]
    assert b1["ideal"][0]["remaining"] == 8 and b1["ideal"][-1]["remaining"] == 0
    assert [p["step"] for p in b1["series"]] == [0, 1, 2, 3]
    b2 = metrics.burndown(db, s2)
    assert [p["remaining"] for p in b2["series"]] == [5, 2, 0, 0]
    assert b2["ideal"][0]["remaining"] == 5 and b2["ideal"][-1]["remaining"] == 0


def test_project_metrics(db: Session):
    ids = build_two_sprint_project(db)
    got = metrics.project_metrics(db, ids["project"])
    assert got["project"] == {
        "stories_total": 4, "stories_done": 4, "points_total": 10, "points_done": 10,
        "sprint_count": 2, "avg_velocity": 5.0,  # (5 + 5) / 2
        "total_llm_calls": 6, "total_input_tokens": 16000, "total_output_tokens": 3500,
        "total_cost_usd": 0.067,  # 16000 * 2/1e6 + 3500 * 10/1e6
        "llm_modes": ["live"], "loc": 2,
        "trace_completeness": 0.25,  # A of A, B, C, D
    }
    assert got["unattributed"] == {"llm_calls": 1, "input_tokens": 1000,
                                   "output_tokens": 500, "est_cost_usd": 0.007}
    assert len(got["sprints"]) == 2 and got["pricing"]["input_per_mtok"] == 2.0


def test_gqm_matches_metrics(db: Session):
    ids = build_two_sprint_project(db)
    sprint = metrics.sprint_metrics(db, _sprints(db, ids)[0])
    assert len(metrics.GQM) == 4
    assert sum(len(g["questions"]) for g in metrics.GQM) == 6
    keys = [mt["key"] for g in metrics.GQM for q in g["questions"] for mt in q["metrics"]]
    assert all(k == "burndown" or k in sprint for k in keys)


def test_empty_project_does_not_raise(db: Session):
    p = repo.create_project(db, "empty", "nothing")
    got = metrics.project_metrics(db, p.id)
    assert got["sprints"] == [] and got["project"]["sprint_count"] == 0
    assert got["project"]["avg_velocity"] is None
    assert got["project"]["trace_completeness"] is None
    assert got["project"]["llm_modes"] == [] and got["project"]["loc"] == 0
    assert got["unattributed"]["est_cost_usd"] == 0


def test_sprint_without_data_has_none_ratios(db: Session):
    p = repo.create_project(db, "x", "y")
    s = Tools(db, p.id, "scrum_master").create_sprint("empty sprint", 5)
    got = metrics.sprint_metrics(db, s)
    assert got["commitment_reliability"] is None and got["first_pass_yield"] is None
    assert got["test_pass_rate"] is None and got["cost_per_completed_point"] is None
    assert got["trace_completeness"] is None and got["ac_coverage"] is None
    assert metrics.burndown(db, s)["committed_points"] == 0


def test_old_format_task_event_is_parsed_from_message(db: Session):
    p = repo.create_project(db, "x", "y")
    po, sm = Tools(db, p.id, "product_owner"), Tools(db, p.id, "scrum_master")
    story = po.create_story(po.create_epic("E").id, title="S", points=2)
    sprint = sm.create_sprint("g", 5)
    sm.add_story_to_sprint(sprint.id, story.id)
    task = sm.create_task(story.id, "Do it", "developer")
    sm.log("sprint_planned", "x", sprint_id=sprint.id, number=1, story_ids=[story.id],
           committed_points=2, capacity=5)
    repo.update(db, task, status="done")
    sm.log("task_updated", "Do it -> done", task_id=task.id)  # no status key (older event)
    assert metrics.burndown(db, sprint)["series"][1]["remaining"] == 0
    assert metrics.sprint_metrics(db, sprint)["completed_points"] == 2


def test_cost_and_pricing():
    assert metrics.cost(1_000_000, 1_000_000) == 12.0
    assert metrics.cost(0, 0) == 0.0
    assert metrics.pricing()["output_per_mtok"] == 10.0


def test_test_function_counting(db: Session):
    ids = build_two_sprint_project(db)
    a, b = ids["stories"]["A"], ids["stories"]["B"]
    assert metrics.test_function_count(db, ids["project"], a) == 2
    assert metrics.test_function_count(db, ids["project"], b) == 0
    # a newer version of the same path replaces the old one
    Tools(db, ids["project"], "qa").write_artifact(
        "test", "tests/test_a.py", "def test_only():\n    pass\n", story_id=a,
        path="tests/test_a.py", version=2)
    assert metrics.test_function_count(db, ids["project"], a) == 1


def test_mock_flow_metrics(db: Session):
    p = repo.create_project(db, "Mock", "a todo app")
    Orchestrator(db, AGENTS).run_to_end(p.id)
    got = metrics.project_metrics(db, p.id)
    assert got["sprints"][0]["commitment_reliability"] == 1.0
    assert got["project"]["llm_modes"] == ["mock"]
    assert got["project"]["total_cost_usd"] == 0
