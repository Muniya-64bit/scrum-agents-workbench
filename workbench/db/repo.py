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


def artifacts(db: Session, project_id: int, kind: str | None = None) -> list[m.Artifact]:
    q = select(m.Artifact).where(m.Artifact.project_id == project_id).order_by(m.Artifact.id)
    if kind:
        q = q.where(m.Artifact.kind == kind)
    return list(db.scalars(q))


def stories_without_design(db: Session, project_id: int) -> list[m.UserStory]:
    """Sprint stories that have no per-story design artifact yet (relation `design`)."""
    designed = set(db.scalars(select(m.TraceLink.story_id).where(m.TraceLink.relation == "design")))
    return [s for s in backlog(db, project_id) if s.sprint_id is not None and s.id not in designed]
