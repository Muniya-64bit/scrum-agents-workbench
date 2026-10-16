"""Thin repository layer; agents/API go through this, never raw SQL."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from workbench.db import models as m


def add(db: Session, obj):
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def create_project(db: Session, name: str, idea: str) -> m.Project:
    return add(db, m.Project(name=name, idea=idea))


def get(db: Session, model, id_: int):
    return db.get(model, id_)


def list_for_project(db: Session, project_id: int, model):
    return list(db.scalars(select(model).where(model.project_id == project_id)))


def backlog(db: Session, project_id: int) -> list[m.UserStory]:
    q = (
        select(m.UserStory)
        .join(m.Epic)
        .where(m.Epic.project_id == project_id)
        .order_by(m.UserStory.priority, m.UserStory.id)
    )
    return list(db.scalars(q))


def list_projects(db: Session) -> list[m.Project]:
    return list(db.scalars(select(m.Project).order_by(m.Project.id)))


def epics(db: Session, project_id: int) -> list[m.Epic]:
    q = select(m.Epic).where(m.Epic.project_id == project_id).order_by(m.Epic.id)
    return list(db.scalars(q))


def sprints(db: Session, project_id: int) -> list[m.Sprint]:
    q = select(m.Sprint).where(m.Sprint.project_id == project_id).order_by(m.Sprint.number)
    return list(db.scalars(q))


def tasks(db: Session, project_id: int, sprint_id: int | None = None,
          status: str | None = None) -> list[m.Task]:
    q = (
        select(m.Task)
        .join(m.UserStory)
        .join(m.Epic)
        .where(m.Epic.project_id == project_id)
        .order_by(m.Task.id)
    )
    if sprint_id is not None:
        q = q.where(m.UserStory.sprint_id == sprint_id)
    if status:
        q = q.where(m.Task.status == status)
    return list(db.scalars(q))


def artifacts(db: Session, project_id: int, kind: str | None = None) -> list[m.Artifact]:
    q = select(m.Artifact).where(m.Artifact.project_id == project_id).order_by(m.Artifact.id)
    if kind:
        q = q.where(m.Artifact.kind == kind)
    return list(db.scalars(q))


def bugs(db: Session, project_id: int, status: str | None = None) -> list[m.Bug]:
    q = (
        select(m.Bug)
        .join(m.UserStory)
        .join(m.Epic)
        .where(m.Epic.project_id == project_id)
        .order_by(m.Bug.id)
    )
    if status:
        q = q.where(m.Bug.status == status)
    return list(db.scalars(q))


def trace_links(db: Session, project_id: int) -> list[tuple[m.TraceLink, m.Artifact]]:
    q = (
        select(m.TraceLink, m.Artifact)
        .join(m.Artifact, m.TraceLink.artifact_id == m.Artifact.id)
        .where(m.Artifact.project_id == project_id)
        .order_by(m.TraceLink.id)
    )
    return [(link, art) for link, art in db.execute(q)]


def update(db: Session, obj, **fields):
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def log_event(db: Session, project_id: int, agent: str, kind: str, message: str = "", **payload):
    return add(
        db,
        m.Event(project_id=project_id, agent=agent, kind=kind, message=message, payload=payload),
    )


def events_since(db: Session, project_id: int, after_id: int = 0) -> list[m.Event]:
    q = (
        select(m.Event)
        .where(m.Event.project_id == project_id, m.Event.id > after_id)
        .order_by(m.Event.id)
    )
    return list(db.scalars(q))
