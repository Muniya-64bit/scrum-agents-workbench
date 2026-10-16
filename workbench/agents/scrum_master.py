"""Scrum Master agent.

It runs in three phases, each with its own prompt and output schema:
  sprint_planning -> pick stories that fit the capacity, create tasks
  review          -> stand-up style summary from task states, burndown snapshot
  retro           -> what went well/wrong and actions, fed into the next sprint's planning

`ScrumMasterAgent` is the single registered agent; it delegates to one handler per phase."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.schemas import ROLES, RetroOutput, SprintPlanOutput, StandupOutput

DEFAULT_CAPACITY = 10  # story points per sprint


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


class SprintPlanner(BaseAgent):
    role = "scrum_master"
    output_schema = SprintPlanOutput
    system_prompt = f"""You are a Scrum Master running sprint planning.
Choose stories from the backlog and break them into tasks.

Rules:
- Use only story ids from the backlog list. The total points must not exceed the capacity.
- Prefer high-priority stories (1 is highest) and give the sprint one clear goal.
- Create 2 to 4 tasks per chosen story. Each task has a story_id, a short title and an assignee.
- assignee must be one of: {", ".join(ROLES)}. Implementation goes to developer, tests to qa.
- If retro actions from the previous sprint are listed, plan so that they are followed.
- summary is one sentence."""

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        capacity = task.get("capacity", DEFAULT_CAPACITY)
        lines = [f"Vision: {project.vision or project.idea}", f"Sprint capacity: {capacity} points",
                 "", "Backlog (id | priority | points | title):"]
        for s in repo.unplanned_stories(db, project_id):
            lines.append(f"{s.id} | {s.priority} | {s.points} | {s.title}")
        actions = _previous_retro_actions(db, project_id)
        if actions:
            lines += ["", "Retro actions from the previous sprint, follow these:"]
            lines += [f"- {a}" for a in actions]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        capacity = task.get("capacity", DEFAULT_CAPACITY)
        chosen = _select_stories(repo.unplanned_stories(db, project_id), [], capacity)
        tasks = []
        for s in chosen:
            tasks.append({"story_id": s.id, "title": f"Implement: {s.title}",
                          "assignee": "developer"})
            tasks.append({"story_id": s.id, "title": f"Test: {s.title}", "assignee": "qa"})
        return {"summary": f"Planned {len(chosen)} stories", "goal": "Deliver the core features",
                "story_ids": [s.id for s in chosen], "tasks": tasks}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, SprintPlanOutput)
        capacity = task.get("capacity", DEFAULT_CAPACITY)
        chosen = _select_stories(repo.unplanned_stories(tools.db, tools.project_id),
                                 out.story_ids, capacity)
        if not chosen:
            tools.log("sprint_skipped", "No planned stories fit the sprint")
            return
        sprint = tools.create_sprint(out.goal, capacity)
        for story in chosen:
            tools.add_story_to_sprint(sprint.id, story.id)
            titles = [t for t in out.tasks if t.story_id == story.id]
            if not titles:  # the LLM gave no tasks for this story: add a default pair
                tools.create_task(story.id, f"Implement: {story.title}", "developer")
                tools.create_task(story.id, f"Test: {story.title}", "qa")
            for t in titles:
                tools.create_task(story.id, t.title,
                                  t.assignee if t.assignee in ROLES else "developer")
        committed = sum(story.points for story in chosen)
        tools.log("sprint_planned", f"Sprint {sprint.number}: {committed} points committed",
                  sprint_id=sprint.id, number=sprint.number, story_ids=[s.id for s in chosen],
                  committed_points=committed, capacity=capacity)


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
- summary is one sentence."""

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        sprint = repo.current_sprint(db, project_id)
        if not sprint:
            return "There is no sprint to review."
        tasks = [t for s in sprint.stories for t in s.tasks]
        done = sum(1 for s in sprint.stories if repo.story_is_done(s))
        bugs = [b for s in sprint.stories for b in db.query(m.Bug).filter_by(story_id=s.id)]
        return "\n".join([
            f"Sprint {sprint.number} goal: {sprint.goal}",
            f"Stories done: {done} of {len(sprint.stories)}",
            f"Tasks done: {sum(1 for t in tasks if t.status == 'done')} of {len(tasks)}",
            f"Points remaining: {repo.remaining_points(sprint)} of "
            f"{sum(s.points for s in sprint.stories)}",
            f"Bugs reported: {len(bugs)}",
        ])

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        return {"summary": "Retrospective complete",
                "went_well": ["The sprint goal was clear"],
                "went_wrong": ["Work was not tracked in small enough tasks"],
                "actions": ["Split large tasks so each fits in one stand-up cycle"]}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, RetroOutput)
        sprint = repo.current_sprint(tools.db, tools.project_id)
        if not sprint:
            return
        tools.save_retro(sprint.id, {"went_well": out.went_well,
                                     "went_wrong": out.went_wrong, "actions": out.actions})


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
