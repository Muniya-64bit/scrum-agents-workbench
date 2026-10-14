"""Scrum state machine.

Idea -> Backlog -> SprintPlanning -> Execution -> Review -> Retro -> Release.

Gates (SprintPlanning, Review) pause for human approval. Agents are looked up by role in a
registry so teammates can swap StubAgents for real ones without touching this file."""

from enum import StrEnum

from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent, StubAgent
from workbench.db import models as m
from workbench.db import repo
from workbench.schemas import ROLES


class Phase(StrEnum):
    IDEA = "idea"
    BACKLOG = "backlog"
    SPRINT_PLANNING = "sprint_planning"
    EXECUTION = "execution"
    REVIEW = "review"
    RETRO = "retro"
    RELEASE = "release"
    DONE = "done"


ORDER = list(Phase)
PHASE_AGENTS: dict[Phase, list[str]] = {
    Phase.BACKLOG: ["product_owner", "architect"],
    Phase.SPRINT_PLANNING: ["scrum_master"],
    Phase.EXECUTION: ["architect", "developer", "qa"],
    Phase.REVIEW: ["scrum_master"],
    Phase.RETRO: ["scrum_master"],
    Phase.RELEASE: ["devops"],
}
GATES = {Phase.SPRINT_PLANNING, Phase.REVIEW}  # human approval needed after the phase runs


class Orchestrator:
    def __init__(self, db: Session, agents: dict[str, BaseAgent] | None = None):
        self.db = db
        self.agents = {r: StubAgent(r) for r in ROLES}
        self.agents.update(agents or {})

    def _project(self, project_id: int) -> m.Project:
        return repo.get(self.db, m.Project, project_id)

    def step(self, project_id: int) -> m.Project:
        """Move to the next phase and run its agents. Blocked while awaiting approval."""
        p = self._project(project_id)
        if p.awaiting_approval:
            raise RuntimeError("Awaiting human approval; call approve() first")
        if p.phase == Phase.DONE:
            return p
        nxt = ORDER[ORDER.index(Phase(p.phase)) + 1]
        repo.update(self.db, p, phase=nxt.value)
        repo.log_event(self.db, project_id, "orchestrator", "phase_started", nxt.value)
        for role in PHASE_AGENTS.get(nxt, []):
            self.agents[role].run(self.db, project_id, {"name": nxt.value, "phase": nxt.value})
        if nxt in GATES:
            repo.update(self.db, p, awaiting_approval=True)
            repo.log_event(self.db, project_id, "orchestrator", "approval_requested", nxt.value)
        return p

    def approve(self, project_id: int, approved: bool = True, comment: str = "") -> m.Project:
        p = self._project(project_id)
        if not p.awaiting_approval:
            raise RuntimeError("Nothing to approve")
        repo.update(self.db, p, awaiting_approval=False)
        repo.log_event(self.db, project_id, "human",
                       "approved" if approved else "rejected", comment, phase=p.phase)
        return p

    def run_to_end(self, project_id: int) -> m.Project:
        """Auto-approve all gates (demo/testing)."""
        p = self._project(project_id)
        while p.phase != Phase.DONE:
            self.step(project_id)
            if p.awaiting_approval:
                self.approve(project_id)
        return p
