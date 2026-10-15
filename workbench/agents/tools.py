"""Tool API: the only way agents change project state. Every call is logged as an Event."""

from sqlalchemy.orm import Session

from workbench.db import models as m
from workbench.db import repo


class Tools:
    def __init__(self, db: Session, project_id: int, agent: str):
        self.db, self.project_id, self.agent = db, project_id, agent

    def log(self, kind: str, message: str = "", **payload):
        return repo.log_event(self.db, self.project_id, self.agent, kind, message, **payload)

    def create_epic(self, title: str, description: str = "") -> m.Epic:
        e = m.Epic(project_id=self.project_id, title=title, description=description)
        e = repo.add(self.db, e)
        self.log("epic_created", title, epic_id=e.id)
        return e

    def create_story(self, epic_id: int, **fields) -> m.UserStory:
        s = repo.add(self.db, m.UserStory(epic_id=epic_id, **fields))
        self.log("story_created", s.title, story_id=s.id)
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
                       path: str = "") -> m.Artifact:
        a = repo.add(self.db, m.Artifact(project_id=self.project_id, kind=kind, name=name,
                                         content=content, path=path, created_by=self.agent))
        if story_id:
            repo.add(self.db, m.TraceLink(story_id=story_id, artifact_id=a.id, relation=kind))
        self.log("artifact_created", name, artifact_id=a.id, artifact_kind=kind)
        return a

    def report_bug(self, story_id: int, description: str) -> m.Bug:
        b = repo.add(self.db, m.Bug(story_id=story_id, description=description))
        self.log("bug_reported", description, bug_id=b.id)
        return b

    def link_artifact(self, artifact_id: int, story_ids: list[int], relation: str) -> None:
        """Trace one artifact to several stories (e.g. sprint-0 architecture -> whole backlog)."""
        for sid in story_ids:
            repo.add(self.db, m.TraceLink(story_id=sid, artifact_id=artifact_id, relation=relation))
        self.log("artifact_linked", relation, artifact_id=artifact_id, story_ids=story_ids)
