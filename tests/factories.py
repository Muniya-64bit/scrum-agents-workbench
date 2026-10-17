"""Builders for test data. `build_two_sprint_project` writes a known two-sprint history through
`Tools`, so metrics tests can assert exact numbers (see tests/test_metrics.py)."""

from pathlib import Path

from sqlalchemy.orm import Session

from workbench.agents.architect import ArchitectAgent
from workbench.agents.base import BaseAgent
from workbench.agents.developer import DeveloperAgent
from workbench.agents.devops import DevOpsAgent
from workbench.agents.product_owner import ProductOwnerAgent
from workbench.agents.qa import QAAgent
from workbench.agents.release import ReleaseAgent
from workbench.agents.scrum_master import ScrumMasterAgent
from workbench.agents.tools import Tools
from workbench.db import repo
from workbench.llm.client import LLMClient

LIVE = {"llm_mode": "live", "model": "test-model", "duration_ms": 10}


def agents_for(mode: str, scenario: Path, fallback: str = "error") -> dict[str, BaseAgent]:
    """The registry's agents, each with its own LLM client in `mode` (record or replay)."""
    def client() -> LLMClient:
        return LLMClient(mode=mode, scenario_dir=scenario, fallback=fallback)

    developer = DeveloperAgent(client())
    return {
        "product_owner": ProductOwnerAgent(client()),
        "scrum_master": ScrumMasterAgent(client()),
        "architect": ArchitectAgent(client()),
        "developer": developer,
        "qa": QAAgent(client(), developer=developer),
        "devops": ReleaseAgent(builder=DevOpsAgent(client())),
    }


def _tasks(sm: Tools, story_id: int, title: str, with_qa: bool = True) -> dict:
    ids = {"dev": sm.create_task(story_id, f"Implement {title}", "developer").id}
    if with_qa:
        ids["qa"] = sm.create_task(story_id, f"Test {title}", "qa").id
    return ids


def build_two_sprint_project(db: Session) -> dict:
    """Sprint 1 commits A, B, C (8 points) and finishes A and B; C is carried into sprint 2
    together with D (5 points). Returns the ids of everything that was created."""
    project = repo.create_project(db, "Metrics demo", "A project with a known history")
    pid = project.id
    po, sm = Tools(db, pid, "product_owner"), Tools(db, pid, "scrum_master")
    arch, dev, qa = (Tools(db, pid, r) for r in ("architect", "developer", "qa"))

    epic = po.create_epic("Core")
    ac = "Given a state When an action Then a result"
    a = po.create_story(epic.id, title="A: sign in", points=3, priority=1,
                        acceptance_criteria=[ac, ac])
    b = po.create_story(epic.id, title="B: sign out", points=2, priority=1,
                        acceptance_criteria=[ac])
    c = po.create_story(epic.id, title="C: reset password", points=3, priority=2,
                        acceptance_criteria=[ac, ac])
    d = po.create_story(epic.id, title="D: profile", points=2, priority=3,
                        acceptance_criteria=[ac])

    arch.log("agent_finished", "architecture ready", calls=1, input_tokens=1000,
             output_tokens=500, cache_hits=0, invalid_outputs=0, **LIVE)

    # --- sprint 1 -----------------------------------------------------------------------------
    s1 = sm.create_sprint("S1", 8)
    for story in (a, b, c):
        sm.add_story_to_sprint(s1.id, story.id)
    t_a, t_b, t_c = (_tasks(sm, s.id, s.title) for s in (a, b, c))
    sm.log("sprint_planned", "Sprint 1: 8 points committed", sprint_id=s1.id, number=1,
           story_ids=[a.id, b.id, c.id], committed_points=8, capacity=8,
           process={"capacity": 8, "max_fix_retries": 1, "test_first": False, "guidelines": []})

    arch.write_artifact("design", "A design", "Sign in design", story_id=a.id)
    dev.write_artifact("code", "app/a.py", "x = 1\ny = 2\n", story_id=a.id, path="app/a.py")
    qa.write_artifact("test", "tests/test_a.py",
                      "def test_one():\n    pass\n\ndef test_two():\n    pass\n",
                      story_id=a.id, path="tests/test_a.py")

    dev.update_task(t_a["dev"], "done")
    qa.log("test_run", "2 passed, 0 failed", story_id=a.id, passed=2, failed=0, ok=True)
    qa.update_task(t_a["qa"], "done")

    dev.update_task(t_b["dev"], "done")
    qa.log("test_run", "1 passed, 1 failed", story_id=b.id, passed=1, failed=1, ok=False)
    b1 = qa.report_bug(b.id, "test_x: boom")
    dev.record_fix_attempt(b1.id, fixed=True)
    qa.log("test_run", "2 passed, 0 failed", story_id=b.id, passed=2, failed=0, ok=True)
    qa.verify_bug(b1.id)
    qa.update_task(t_b["qa"], "done")

    dev.update_task(t_c["dev"], "done")
    qa.log("test_run", "0 passed, 1 failed", story_id=c.id, passed=0, failed=1, ok=False)
    c1 = qa.report_bug(c.id, "test_c: fail")
    dev.record_fix_attempt(c1.id, fixed=False)
    qa.update_task(t_c["qa"], "testing")

    dev.log("agent_finished", "code written", calls=2, input_tokens=8000, output_tokens=1500,
            cache_hits=1, invalid_outputs=1, **LIVE)
    qa.log("agent_finished", "tests run", calls=1, input_tokens=2000, output_tokens=500,
           cache_hits=0, invalid_outputs=0, **LIVE)
    sm.save_retro(s1.id, {"went_well": ["a"], "went_wrong": ["b"], "actions": ["c"]})
    repo.update(db, c, sprint_id=None, status="backlog")  # carried over

    # --- sprint 2 -----------------------------------------------------------------------------
    s2 = sm.create_sprint("S2", 5)
    for story in (c, d):
        sm.add_story_to_sprint(s2.id, story.id)
    t_d = _tasks(sm, d.id, d.title)
    sm.log("sprint_planned", "Sprint 2: 5 points committed", sprint_id=s2.id, number=2,
           story_ids=[c.id, d.id], committed_points=5, capacity=5,
           process={"capacity": 5, "max_fix_retries": 2, "test_first": False, "guidelines": []})

    dev.record_fix_attempt(c1.id, fixed=True)
    qa.log("test_run", "1 passed, 0 failed", story_id=c.id, passed=1, failed=0, ok=True)
    qa.verify_bug(c1.id)
    qa.update_task(t_c["qa"], "done")
    dev.update_task(t_d["dev"], "done")
    qa.log("test_run", "1 passed, 0 failed", story_id=d.id, passed=1, failed=0, ok=True)
    qa.update_task(t_d["qa"], "done")

    dev.log("agent_finished", "work done", calls=2, input_tokens=5000, output_tokens=1000,
            cache_hits=0, invalid_outputs=0, **LIVE)
    sm.save_retro(s2.id, {"went_well": ["d"], "went_wrong": ["e"], "actions": ["f"]})

    return {"project": pid, "stories": {"A": a.id, "B": b.id, "C": c.id, "D": d.id},
            "sprints": [s1.id, s2.id], "bugs": {"b1": b1.id, "c1": c1.id}}
