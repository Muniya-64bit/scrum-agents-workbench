"""Tool API: the only way agents change project state. Every call is logged as an Event."""

from sqlalchemy.orm import Session

from workbench.db import models as m
from workbench.db import repo


class Tools:
    def __init__(self, db: Session, project_id: int, agent: str):
        self.db, self.project_id, self.agent = db, project_id, agent

    def log(self, kind: str, message: str = "", **payload):
        return repo.log_event(self.db, self.project_id, self.agent, kind, message, **payload)

    def set_vision(self, vision: str) -> m.Project:
        p = repo.update(self.db, repo.get(self.db, m.Project, self.project_id), vision=vision)
        self.log("vision_set", vision)
        return p

    def create_epic(self, title: str, description: str = "") -> m.Epic:
        e = m.Epic(project_id=self.project_id, title=title, description=description)
        e = repo.add(self.db, e)
        self.log("epic_created", title, epic_id=e.id)
        return e

    def create_story(self, epic_id: int, **fields) -> m.UserStory:
        s = repo.add(self.db, m.UserStory(epic_id=epic_id, **fields))
        self.log("story_created", s.title, story_id=s.id)
        return s

    def create_sprint(self, goal: str, capacity: int = 10) -> m.Sprint:
        number = len(repo.sprints(self.db, self.project_id)) + 1
        s = repo.add(self.db, m.Sprint(project_id=self.project_id, number=number, goal=goal,
                                       capacity=capacity, status="active"))
        self.log("sprint_created", f"Sprint {number}: {goal}", sprint_id=s.id)
        return s

    def add_story_to_sprint(self, sprint_id: int, story_id: int) -> m.UserStory:
        s = repo.update(self.db, repo.get(self.db, m.UserStory, story_id),
                        sprint_id=sprint_id, status="sprint")
        self.log("story_planned", s.title, story_id=s.id, sprint_id=sprint_id)
        return s

    def snapshot_burndown(self, sprint_id: int) -> dict:
        """Record points remaining; the burndown chart is built from these events."""
        sprint = repo.get(self.db, m.Sprint, sprint_id)
        remaining = repo.remaining_points(sprint)
        self.log("burndown_snapshot", f"{remaining} points remaining",
                 sprint_id=sprint_id, remaining=remaining)
        return {"sprint_id": sprint_id, "remaining": remaining}

    def save_retro(self, sprint_id: int, retro: dict) -> m.Sprint:
        s = repo.update(self.db, repo.get(self.db, m.Sprint, sprint_id),
                        retro=retro, status="done")
        self.log("retro_saved", f"Sprint {s.number} retrospective", sprint_id=s.id, **retro)
        return s

    def create_task(self, story_id: int, title: str, assignee: str = "") -> m.Task:
        t = repo.add(self.db, m.Task(story_id=story_id, title=title, assignee=assignee))
        self.log("task_created", title, task_id=t.id)
        return t

    def update_task(self, task_id: int, status: str) -> m.Task:
        t = repo.update(self.db, repo.get(self.db, m.Task, task_id), status=status)
        self.log("task_updated", f"{t.title} -> {status}", task_id=t.id)
        return t

    def write_artifact(self, kind: str, name: str, content: str, story_id: int | None = None,
                       path: str = "", version: int = 1) -> m.Artifact:
        a = repo.add(self.db, m.Artifact(project_id=self.project_id, kind=kind, name=name,
                                         content=content, path=path, version=version,
                                         created_by=self.agent))
        if story_id:
            repo.add(self.db, m.TraceLink(story_id=story_id, artifact_id=a.id, relation=kind))
        self.log("artifact_created", name, artifact_id=a.id, artifact_kind=kind)
        return a

    def report_bug(self, story_id: int, description: str) -> m.Bug:
        b = repo.add(self.db, m.Bug(story_id=story_id, description=description))
        self.log("bug_reported", description, bug_id=b.id)
        return b

    def record_fix_attempt(self, bug_id: int, fixed: bool) -> m.Bug:
        """Count one Developer attempt at a bug; `fixed` marks it fixed until QA re-tests."""
        b = repo.get(self.db, m.Bug, bug_id)
        b = repo.update(self.db, b, retries=b.retries + 1, status="fixed" if fixed else b.status)
        self.log("bug_fixed" if fixed else "bug_fix_failed", b.description, bug_id=b.id,
                 story_id=b.story_id, retries=b.retries)
        return b
    def link_artifact(self, artifact_id: int, story_ids: list[int], relation: str) -> None:
        """Trace one artifact to several stories (e.g. sprint-0 architecture -> whole backlog)."""
        for sid in story_ids:
            repo.add(self.db, m.TraceLink(story_id=sid, artifact_id=artifact_id, relation=relation))
        self.log("artifact_linked", relation, artifact_id=artifact_id, story_ids=story_ids)
