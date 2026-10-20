"""Scrum state machine.

Idea -> Backlog -> SprintPlanning -> Execution -> Review -> Retro -> Release.
After a release the loop goes back to SprintPlanning while stories are left to plan (at most
MAX_SPRINTS sprints), otherwise the project is done.

Gates (SprintPlanning, Review) pause for human approval. Rejecting sprint planning returns the
planned stories to the backlog and plans the same sprint again with the human's reason;
rejecting the review lets the project go on to the retrospective, which must respond to the
reason. Which agents run in a phase, and which phases are gated, come from the process model
(`workbench.process_model`), whose entry and exit criteria are checked and logged at every phase.
Agents are looked up by role in a registry so teammates can swap StubAgents for real ones
without touching this file."""

from enum import StrEnum

from sqlalchemy.orm import Session

from workbench import config, process, process_model
from workbench.agents.base import BaseAgent, StubAgent
from workbench.agents.tools import Tools
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
MAINTENANCE_EPIC = "Maintenance"  # where problems reported after a release become stories
PHASE_AGENTS: dict[Phase, list[str]] = {Phase(a.phase): a.agents for a in process_model.MODEL}
# human approval needed after the phase runs
GATES = {Phase(a.phase) for a in process_model.MODEL if a.gate}
MAX_STEPS = 200  # run_to_end gives up after this many phase changes


def _pending_decision(db: Session, project_id: int) -> m.Event | None:
    """The latest `approved` or `rejected` event, unless a phase has started since then."""
    for e in reversed(repo.events_since(db, project_id)):
        if e.kind == "phase_started":
            return None
        if e.kind in ("approved", "rejected"):
            return e
    return None


class Orchestrator:
    def __init__(self, db: Session, agents: dict[str, BaseAgent] | None = None):
        self.db = db
        self.agents = {r: StubAgent(r) for r in ROLES}
        self.agents.update(agents or {})

    def _project(self, project_id: int) -> m.Project:
        return repo.get(self.db, m.Project, project_id)

    def next_phase(self, p: m.Project) -> Phase:
        """The phase after the current one. After a release, plan another sprint if there is one.
        After a rejected sprint plan, plan again."""
        cur = Phase(p.phase)
        if cur == Phase.SPRINT_PLANNING and self.replanning(p.id):
            return Phase.SPRINT_PLANNING
        if cur == Phase.RELEASE and self.more_sprints(p.id):
            return Phase.SPRINT_PLANNING
        return ORDER[ORDER.index(cur) + 1]

    def replanning(self, project_id: int) -> bool:
        """Was the sprint plan rejected, and not yet planned again (so the next step plans)?"""
        e = _pending_decision(self.db, project_id)
        return (e is not None and e.kind == "rejected"
                and (e.payload or {}).get("phase") == Phase.SPRINT_PLANNING)

    def more_sprints(self, project_id: int) -> bool:
        """Is another sprint possible: stories left that fit the next capacity, and fewer than
        MAX_SPRINTS sprints so far. Every maintenance request adds one sprint to that limit while
        its fix is still waiting."""
        sprints = len(repo.sprints(self.db, project_id))
        requests = sum(1 for e in repo.events_since(self.db, project_id)
                       if e.kind == "maintenance_requested")
        if requests and self.maintenance_pending(project_id) \
                and sprints < config.MAX_SPRINTS + requests:
            return True
        if sprints >= config.MAX_SPRINTS:
            return False
        capacity = process.next_process(self.db, project_id)[0].capacity
        return any(s.points <= capacity for s in repo.unplanned_stories(self.db, project_id))

    def maintenance_pending(self, project_id: int) -> bool:
        """Is a reported problem waiting for a sprint?"""
        return any(s.epic.title == MAINTENANCE_EPIC
                   for s in repo.unplanned_stories(self.db, project_id))

    def request_maintenance(self, project_id: int, title: str, description: str,
                            points: int = 2) -> m.Project:
        """A problem found after the release: it becomes a top-priority fix story, and the next
        step plans a maintenance sprint. Only a finished project takes one."""
        p = self._project(project_id)
        if p.phase != Phase.DONE:
            raise RuntimeError("Only a finished project takes a maintenance request")
        tools = Tools(self.db, project_id, "human")
        epic = next((e for e in repo.epics(self.db, project_id) if e.title == MAINTENANCE_EPIC),
                    None) or tools.create_epic(MAINTENANCE_EPIC,
                                               "Problems found after a release")
        problem = description.strip().rstrip(".")
        story = tools.create_story(
            epic.id, title=f"Fix: {title.strip()}", as_a="user of the released product",
            i_want=f"this problem fixed: {problem}", so_that="the product works as released",
            acceptance_criteria=[
                f"Given the released product When the problem is tried again ({problem}) "
                "Then it behaves correctly",
                "Given the fix When the existing tests run Then all of them still pass"],
            points=points, priority=1)
        tools.log("maintenance_requested", title.strip(), story_id=story.id,
                  description=description.strip())
        repo.update(self.db, p, phase=Phase.RELEASE.value)  # the next step plans the sprint
        return p

    def step(self, project_id: int) -> m.Project:
        """Move to the next phase and run its agents. Blocked while awaiting approval."""
        p = self._project(project_id)
        if p.awaiting_approval:
            raise RuntimeError("Awaiting human approval; call approve() first")
        if p.phase == Phase.DONE:
            return p
        nxt = self.next_phase(p)
        repo.update(self.db, p, phase=nxt.value)
        repo.log_event(self.db, project_id, "orchestrator", "phase_started", nxt.value)
        process_model.log_check(self.db, project_id, nxt.value, "entry")
        for role in PHASE_AGENTS.get(nxt, []):
            self.agents[role].run(self.db, project_id, {"name": nxt.value, "phase": nxt.value})
        process_model.log_check(self.db, project_id, nxt.value, "exit")
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
        sprint = repo.current_sprint(self.db, project_id)
        if not approved and p.phase == Phase.SPRINT_PLANNING and sprint is not None \
                and sprint.status == "active":
            Tools(self.db, project_id, "orchestrator").reset_sprint_plan(sprint.id, comment)
        return p

    def run_to_end(self, project_id: int) -> m.Project:
        """Auto-approve all gates (demo/testing)."""
        p = self._project(project_id)
        for _ in range(MAX_STEPS):
            if p.phase == Phase.DONE:
                return p
            self.step(project_id)
            if p.awaiting_approval:
                self.approve(project_id)
        if p.phase != Phase.DONE:
            raise RuntimeError(f"Project did not finish within {MAX_STEPS} steps")
        return p
