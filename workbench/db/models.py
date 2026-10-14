from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    idea: Mapped[str] = mapped_column(Text)
    vision: Mapped[str] = mapped_column(Text, default="")
    phase: Mapped[str] = mapped_column(String(30), default="idea")
    awaiting_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    epics = relationship("Epic", back_populates="project", cascade="all, delete-orphan")
    sprints = relationship("Sprint", back_populates="project", cascade="all, delete-orphan")


class Epic(Base):
    __tablename__ = "epics"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")

    project = relationship("Project", back_populates="epics")
    stories = relationship("UserStory", back_populates="epic", cascade="all, delete-orphan")


class Sprint(Base):
    __tablename__ = "sprints"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    number: Mapped[int] = mapped_column(Integer)
    goal: Mapped[str] = mapped_column(Text, default="")
    capacity: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned|active|done
    retro: Mapped[dict] = mapped_column(JSON, default=dict)

    project = relationship("Project", back_populates="sprints")
    stories = relationship("UserStory", back_populates="sprint")


class UserStory(Base):
    __tablename__ = "stories"
    id: Mapped[int] = mapped_column(primary_key=True)
    epic_id: Mapped[int] = mapped_column(ForeignKey("epics.id"))
    sprint_id: Mapped[int | None] = mapped_column(ForeignKey("sprints.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    as_a: Mapped[str] = mapped_column(String(200), default="")
    i_want: Mapped[str] = mapped_column(Text, default="")
    so_that: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)  # Given/When/Then strings
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 = highest
    points: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="backlog")

    epic = relationship("Epic", back_populates="stories")
    sprint = relationship("Sprint", back_populates="stories")
    tasks = relationship("Task", back_populates="story", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"))
    title: Mapped[str] = mapped_column(String(300))
    assignee: Mapped[str] = mapped_column(String(30), default="")  # agent role
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo|doing|testing|done
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    story = relationship("UserStory", back_populates="tasks")


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(30))  # architecture|diagram|api_spec|code|test|release
    name: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TraceLink(Base):
    """story -> artifact (design/code/test) traceability."""

    __tablename__ = "trace_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"))
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"))
    relation: Mapped[str] = mapped_column(String(30), default="implements")


class Bug(Base):
    __tablename__ = "bugs"
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|fixed
    retries: Mapped[int] = mapped_column(Integer, default=0)


class Event(Base):
    """Append-only log of everything that happens; feeds the activity feed + SSE."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    agent: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
