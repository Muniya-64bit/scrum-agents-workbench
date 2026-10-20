"""Scrum Master agent.

It runs in three phases, each with its own prompt and output schema:
  sprint_planning -> pick stories that fit the capacity, create tasks
  review          -> stand-up style summary from task states, burndown snapshot
  retro           -> what went well/wrong, actions and typed process changes; unfinished
                     stories go back to the backlog; the changes shape the next sprint's plan

`ScrumMasterAgent` is the single registered agent; it delegates to one handler per phase."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config, metrics
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.process import (
    ProcessConfig,
    current_process,
    next_process,
    suggest_process_changes,
)
from workbench.schemas import (
    ProcessChanges,
    RetroOutput,
    SprintPlanOutput,
    StandupOutput,
)

DEFAULT_CAPACITY = config.DEFAULT_CAPACITY  # story points per sprint (kept for compatibility)

LEVER_HELP = [
    "capacity (3 to 40): story points committed per sprint",
    "max_fix_retries (1 to 5): developer attempts per bug before it stays open",
    "test_first (true/false): QA writes the acceptance tests before the Developer codes",
    "add_guidelines (up to 5 kept, 200 characters each): working agreements for every agent",
]


def _select_stories(candidates: list[m.UserStory], requested: list[int], capacity: int) -> list:
    """Keep the requested stories that exist and fit the capacity.

    The LLM proposes, this decides: unknown or duplicate ids are dropped and anything that
    would exceed the capacity is skipped. If nothing usable is left, fall back to filling the
    sprint by priority so a bad answer never produces an empty sprint."""
    by_id = {s.id: s for s in candidates}
    chosen, used = [], 0
    for sid in dict.fromkeys(requested):
        story = by_id.get(sid)
        if story and used + story.points <= capacity:
            chosen.append(story)
            used += story.points
    if not chosen:
        for story in candidates:
            if used + story.points <= capacity:
                chosen.append(story)
                used += story.points
    return chosen


# Only these agents ever mark a task done (the Developer when it commits, QA when the tests pass).
# A task for any other role would stay open forever and the story could never be completed.
TASK_ROLES = ("developer", "qa")


class SprintPlanner(BaseAgent):
    role = "scrum_master"
    output_schema = SprintPlanOutput
    system_prompt = """You are a Scrum Master running sprint planning.
Choose stories from the backlog and break them into tasks.

Rules:
- Use only story ids from the backlog list. The total points must not exceed the capacity.
- Prefer high-priority stories (1 is highest) and give the sprint one clear goal.
- Create 2 to 4 tasks per chosen story. Each task has a story_id, a short title and an assignee.
- assignee must be developer or qa. Implementation goes to developer, tests to qa. No other
  role takes tasks.
- If retro actions from the previous sprint are listed, plan so that they are followed.
- Stories marked (carried over) were not finished last sprint; plan them first.
- summary is one sentence."""

    def _process(self, db: Session, project_id: int, task: dict):
        """(levers for this sprint, diff vs the last sprint, reason, capacity to plan with).

        An explicit `task["capacity"]` overrides the retrospective's decision."""
        cfg, diff, reason = next_process(db, project_id)
        capacity = task["capacity"] if "capacity" in task else cfg.capacity
        return cfg, diff, reason, capacity

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        cfg, diff, reason, capacity = self._process(db, project_id, task)
        carried = _carried_over_ids(db, project_id)
        lines = [f"Vision: {project.vision or project.idea}", f"Sprint capacity: {capacity} points",
                 "", "Backlog (id | priority | points | title):"]
        for s in repo.unplanned_stories(db, project_id):
            mark = " (carried over)" if s.id in carried else ""
            lines.append(f"{s.id} | {s.priority} | {s.points} | {s.title}{mark}")
        lines += ["", "Process for this sprint:", *_describe_process(cfg)]
        if diff:
            lines.append(f"Changed after the last retrospective: {_describe_diff(diff)}"
                         + (f" ({reason})" if reason else ""))
        actions = _previous_retro_actions(db, project_id)
        if actions:
            lines += ["", "Retro actions from the previous sprint, follow these:"]
            lines += [f"- {a}" for a in actions]
        if _rejected_sprint(db, project_id):
            reason = _rejection_reason(db, project_id, "sprint_planning")
            lines += ["", "The human rejected your previous plan for this sprint. "
                      "Plan it again and address the reason:",
                      f"- {reason or 'No reason given; reconsider the scope and the tasks.'}"]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        capacity = self._process(db, project_id, task)[3]
        chosen = _select_stories(repo.unplanned_stories(db, project_id), [], capacity)
        if _rejected_sprint(db, project_id) and len(chosen) > 1:
            chosen = chosen[:-1]  # the plan was rejected: commit to less
        tasks = []
        for s in chosen:
            if _has_tasks(db, s.id):  # carried over: keeps its tasks
                continue
            tasks.append({"story_id": s.id, "title": f"Implement: {s.title}",
                          "assignee": "developer"})
            tasks.append({"story_id": s.id, "title": f"Test: {s.title}", "assignee": "qa"})
        return {"summary": f"Planned {len(chosen)} stories", "goal": "Deliver the core features",
                "story_ids": [s.id for s in chosen], "tasks": tasks}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, SprintPlanOutput)
        cfg, diff, reason, capacity = self._process(tools.db, tools.project_id, task)
        chosen = _select_stories(repo.unplanned_stories(tools.db, tools.project_id),
                                 out.story_ids, capacity)
        if not chosen:
            tools.log("sprint_skipped", "No planned stories fit the sprint")
            return
        rejected = _rejected_sprint(tools.db, tools.project_id)
        sprint = (tools.reopen_sprint(rejected.id, out.goal, capacity) if rejected
                  else tools.create_sprint(out.goal, capacity))
        for story in chosen:
            tools.add_story_to_sprint(sprint.id, story.id)
            if _has_tasks(tools.db, story.id):  # carried over: keep its tasks
                continue
            roles = set()
            for t in (t for t in out.tasks if t.story_id == story.id):
                assignee = t.assignee if t.assignee in TASK_ROLES else "developer"
                roles.add(assignee)
                tools.create_task(story.id, t.title, assignee)
            # a story is done when its code is written and its tests pass: it needs both tasks
            if "developer" not in roles:
                tools.create_task(story.id, f"Implement: {story.title}", "developer")
            if "qa" not in roles:
                tools.create_task(story.id, f"Test: {story.title}", "qa")
        committed = sum(story.points for story in chosen)
        used = cfg.model_copy(update={"capacity": capacity})  # the process actually used
        tools.log("sprint_planned", f"Sprint {sprint.number}: {committed} points committed",
                  sprint_id=sprint.id, number=sprint.number, story_ids=[s.id for s in chosen],
                  committed_points=committed, capacity=capacity, process=used.model_dump(),
                  process_changes=diff, process_reason=reason)
        if diff:
            tools.log("process_changed", f"Process changed: {_describe_diff(diff)}",
                      sprint_id=sprint.id, diff=diff, reason=reason)


class StandupAgent(BaseAgent):
    role = "scrum_master"
    output_schema = StandupOutput
    system_prompt = """You are a Scrum Master writing the daily stand-up summary.
Use only the task states you are given.
- yesterday: what was finished. today: what is in progress or next. blockers: anything stuck.
- Keep each item to one short line. summary is one sentence."""

    def _tasks(self, db: Session, project_id: int) -> list[m.Task]:
        sprint = repo.current_sprint(db, project_id)
        return [t for s in sprint.stories for t in s.tasks] if sprint else []

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        sprint = repo.current_sprint(db, project_id)
        if not sprint:
            return "There is no active sprint."
        lines = [f"Sprint {sprint.number} goal: {sprint.goal}", "Tasks (story | task | status):"]
        for s in sprint.stories:
            lines += [f"{s.title} | {t.title} | {t.status}" for t in s.tasks]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        tasks = self._tasks(db, project_id)
        by = {st: [t.title for t in tasks if t.status == st]
              for st in ("done", "doing", "testing", "todo")}
        return {"summary": f"{len(by['done'])} of {len(tasks)} tasks done",
                "yesterday": by["done"], "today": by["doing"] + by["testing"] + by["todo"],
                "blockers": []}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, StandupOutput)
        sprint = repo.current_sprint(tools.db, tools.project_id)
        if not sprint:
            return
        tools.log("standup", out.summary, sprint_id=sprint.id, yesterday=out.yesterday,
                  today=out.today, blockers=out.blockers)
        tools.snapshot_burndown(sprint.id)


class RetroAgent(BaseAgent):
    role = "scrum_master"
    output_schema = RetroOutput
    system_prompt = """You are a Scrum Master facilitating the sprint retrospective.
Base it on the sprint data you are given. Do not invent events.
- went_well and went_wrong: 2 to 4 short items each.
- actions: 1 to 3 concrete improvements the team can apply in the NEXT sprint.
- process_changes: change the process levers only when the measured data supports it; leave a
  field null to keep it. Put the data-based justification in process_changes.reason.
- summary is one sentence."""

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        sprint = repo.current_sprint(db, project_id)
        if not sprint:
            return "There is no sprint to review."
        tasks = [t for s in sprint.stories for t in s.tasks]
        done = sum(1 for s in sprint.stories if repo.story_is_done(s))
        bugs = [b for s in sprint.stories for b in db.query(m.Bug).filter_by(story_id=s.id)]
        sm = metrics.sprint_metrics(db, sprint)
        cfg = current_process(db, project_id)
        lines = [
            f"Sprint {sprint.number} goal: {sprint.goal}",
            f"Stories done: {done} of {len(sprint.stories)}",
            f"Tasks done: {sum(1 for t in tasks if t.status == 'done')} of {len(tasks)}",
            f"Points remaining: {repo.remaining_points(sprint)} of "
            f"{sum(s.points for s in sprint.stories)}",
            f"Bugs reported: {len(bugs)}",
            "",
            "Sprint metrics:",
            f"- committed {sm['committed_points']} points, completed {sm['completed_points']}",
            f"- commitment reliability: {_fmt(sm['commitment_reliability'])}",
            f"- first-pass yield: {_fmt(sm['first_pass_yield'])}",
            f"- test pass rate: {_fmt(sm['test_pass_rate'])}",
            f"- bugs reported: {sm['bugs_reported']}, fix attempts: {sm['fix_attempts']}",
            f"- retry-limit hits: {sm['retry_limit_hits']}",
            f"- stories carried over: {sm['carried_over_stories']}",
            "",
            "Current process:", *_describe_process(cfg),
            "",
            "Levers you may change (bounds):", *[f"- {h}" for h in LEVER_HELP],
            "",
            "Advisor suggestion:", *_describe_changes(suggest_process_changes(sm, cfg)),
            "",
            "Propose process_changes only when the data supports them; "
            "leave fields null to keep them.",
        ]
        rejection = _review_rejection(db, sprint)
        if rejection is not None:
            lines += ["", "The human REJECTED this sprint's review. Respond to it in went_wrong "
                      "and give at least one action that addresses it. Reason:",
                      f"- {rejection or 'No reason given.'}"]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        sprint = repo.current_sprint(db, project_id)
        changes = ProcessChanges()
        went_wrong = ["Work was not tracked in small enough tasks"]
        actions = ["Split large tasks so each fits in one stand-up cycle"]
        if sprint:
            changes = suggest_process_changes(metrics.sprint_metrics(db, sprint),
                                              current_process(db, project_id))
            rejection = _review_rejection(db, sprint)
            if rejection is not None:
                went_wrong.append(f"The sprint review was rejected: {rejection or 'no reason'}")
                actions.append(f"Address the review feedback: {rejection or 'ask the reviewer'}")
        return {"summary": "Retrospective complete",
                "went_well": ["The sprint goal was clear"],
                "went_wrong": went_wrong, "actions": actions,
                "process_changes": changes.model_dump()}

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        """Idempotent: a sprint whose retrospective is already saved is not reviewed again."""
        sprint = repo.current_sprint(db, project_id)
        retro = (sprint.retro or {}) if sprint else {}
        if retro.get("went_well") or retro.get("process_changes"):
            Tools(db, project_id, self.role).log(
                "retro_exists", f"Sprint {sprint.number} already has a retrospective",
                sprint_id=sprint.id)
            return RetroOutput(
                summary="Retrospective already saved", went_well=retro.get("went_well", []),
                went_wrong=retro.get("went_wrong", []), actions=retro.get("actions", []),
                process_changes=ProcessChanges(**(retro.get("process_changes") or {})))
        return super().run(db, project_id, task)

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, RetroOutput)
        sprint = repo.current_sprint(tools.db, tools.project_id)
        if not sprint:
            return
        measured = metrics.sprint_metrics(tools.db, sprint)
        for story in list(sprint.stories):  # unfinished work goes back to the backlog
            if not repo.story_is_done(story):
                tools.unplan_story(story.id, sprint.id)
        tools.save_retro(sprint.id, {"went_well": out.went_well,
                                     "went_wrong": out.went_wrong, "actions": out.actions,
                                     "process_changes": out.process_changes.model_dump(),
                                     "metrics": measured})


def _fmt(ratio: float | None) -> str:
    return "n/a" if ratio is None else f"{ratio * 100:.1f}%"


def _describe_process(cfg: ProcessConfig) -> list[str]:
    lines = [f"- capacity: {cfg.capacity} points", f"- max_fix_retries: {cfg.max_fix_retries}",
             f"- test_first: {'on' if cfg.test_first else 'off'}"]
    if cfg.guidelines:
        lines.append("- working agreements: " + "; ".join(cfg.guidelines))
    return lines


def _describe_changes(ch: ProcessChanges) -> list[str]:
    """One line per lever the advisor would change, then its reason."""
    lines = []
    if ch.capacity is not None:
        lines.append(f"- capacity -> {ch.capacity}")
    if ch.max_fix_retries is not None:
        lines.append(f"- max_fix_retries -> {ch.max_fix_retries}")
    if ch.test_first is not None:
        lines.append(f"- test_first -> {'on' if ch.test_first else 'off'}")
    lines += [f"- add working agreement: {g}" for g in ch.add_guidelines]
    if not lines:
        lines.append("- no change")
    lines.append(f"Reason: {ch.reason}")
    return lines


def _describe_diff(diff: dict) -> str:
    parts = []
    for lever, (old, new) in diff.items():
        if lever == "guidelines":
            parts.append(f"{len(new) - len(old):+d} working agreement(s)")
        elif lever == "test_first":
            parts.append(f"test-first {'on' if new else 'off'}")
        else:
            parts.append(f"{lever.replace('_', ' ')} {old} -> {new}")
    return ", ".join(parts)


def _has_tasks(db: Session, story_id: int) -> bool:
    """Queried, not read from `story.tasks`, so a stale cached collection cannot mislead."""
    return db.query(m.Task).filter_by(story_id=story_id).count() > 0


def _carried_over_ids(db: Session, project_id: int) -> set[int]:
    """Stories that an earlier retrospective returned to the backlog."""
    return {e.payload["story_id"] for e in repo.events_since(db, project_id)
            if e.kind == "story_carried_over"}


def _rejected_sprint(db: Session, project_id: int) -> m.Sprint | None:
    """The latest sprint, if its plan was rejected and it waits to be planned again."""
    sprint = repo.current_sprint(db, project_id)
    return sprint if sprint is not None and sprint.status == "replanning" else None


def _rejection_reason(db: Session, project_id: int, phase: str) -> str:
    """The human's reason on the latest `rejected` event of a gate, or ""."""
    for e in reversed(repo.events_since(db, project_id)):
        if e.kind == "rejected" and (e.payload or {}).get("phase") == phase:
            return e.message
    return ""


def _review_rejection(db: Session, sprint: m.Sprint) -> str | None:
    """The reason the human rejected this sprint's review ("" if none given), or None when the
    review was not rejected."""
    after = 0
    for e in repo.events_since(db, sprint.project_id):
        if e.kind == "sprint_planned" and (e.payload or {}).get("sprint_id") == sprint.id:
            after = e.id
    for e in reversed(repo.events_since(db, sprint.project_id, after)):
        if e.kind in ("approved", "rejected") and (e.payload or {}).get("phase") == "review":
            return e.message if e.kind == "rejected" else None
    return None


def _previous_retro_actions(db: Session, project_id: int) -> list[str]:
    """Improvement actions from the latest finished sprint, injected into the next plan."""
    for sprint in reversed(repo.sprints(db, project_id)):
        if sprint.retro and sprint.retro.get("actions"):
            return list(sprint.retro["actions"])
    return []


class ScrumMasterAgent(BaseAgent):
    """Registered agent for the `scrum_master` role; picks a handler by the task's phase."""

    role = "scrum_master"

    def __init__(self, llm: LLMClient | None = None):
        super().__init__(llm)
        self.handlers: dict[str, BaseAgent] = {
            "sprint_planning": SprintPlanner(self.llm),
            "review": StandupAgent(self.llm),
            "retro": RetroAgent(self.llm),
        }

    def _handler(self, task: dict) -> BaseAgent:
        phase = task.get("phase", "")
        if phase not in self.handlers:
            raise ValueError(f"Scrum Master has no handler for phase {phase!r}")
        return self.handlers[phase]

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        return self._handler(task).build_prompt(db, project_id, task)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        return self._handler(task).mock_output(db, project_id, task)

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        self._handler(task).apply(tools, out, task)

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        return self._handler(task).run(db, project_id, task)
