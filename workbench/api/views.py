"""Response and request models for the REST API. They also define the OpenAPI schema at /docs,
which the frontend uses as its contract."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TaskStatus = Literal["todo", "doing", "testing", "done"]


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectView(_ORM):
    id: int
    name: str
    idea: str
    phase: str
    awaiting_approval: bool


class StoryView(_ORM):
    id: int
    epic_id: int
    sprint_id: int | None
    title: str
    as_a: str
    i_want: str
    so_that: str
    acceptance_criteria: list[str]
    priority: int
    points: int
    status: str


class EpicView(BaseModel):
    id: int
    title: str
    description: str
    stories: list[StoryView]


class BacklogView(BaseModel):
    vision: str
    epics: list[EpicView]


class TaskView(_ORM):
    id: int
    story_id: int
    title: str
    assignee: str
    status: str
    updated_at: datetime


class TaskPatch(BaseModel):
    status: TaskStatus


class SprintView(BaseModel):
    id: int
    number: int
    goal: str
    capacity: int
    status: str
    retro: dict
    story_ids: list[int]
    points: int


class SprintDetailView(SprintView):
    stories: list[StoryView]
    tasks: list[TaskView]


class ArtifactSummary(_ORM):
    id: int
    kind: str
    name: str
    path: str
    version: int
    created_by: str
    created_at: datetime


class ArtifactView(ArtifactSummary):
    content: str
    story_ids: list[int]


class BugView(_ORM):
    id: int
    story_id: int
    description: str
    status: str
    retries: int


class TraceItem(BaseModel):
    artifact_id: int
    name: str
    kind: str
    path: str


class TraceRow(BaseModel):
    """One row of the story -> design -> code -> test table."""

    story_id: int
    title: str
    status: str
    design: list[TraceItem] = []
    code: list[TraceItem] = []
    test: list[TraceItem] = []
    other: list[TraceItem] = []


class EventView(BaseModel):
    id: int
    agent: str
    kind: str
    message: str
    payload: dict
    at: datetime
