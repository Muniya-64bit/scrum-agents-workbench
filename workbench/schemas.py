"""Shared contracts. Every agent's structured output is a pydantic model; the LLM wrapper
validates against it. Change these only with team agreement (see docs/architecture.md)."""

from pydantic import BaseModel, Field

ROLES = ["product_owner", "scrum_master", "architect", "developer", "qa", "devops"]


class AgentOutput(BaseModel):
    """Base for all agent outputs. `summary` is shown in the activity feed."""

    summary: str = ""


class StoryOut(BaseModel):
    title: str
    as_a: str
    i_want: str
    so_that: str
    acceptance_criteria: list[str] = Field(description="Given/When/Then strings")
    priority: int = Field(3, ge=1, le=5)
    points: int = Field(1, ge=1, le=13)


class EpicOut(BaseModel):
    title: str
    description: str = ""
    stories: list[StoryOut] = []


class BacklogOutput(AgentOutput):  # Product Owner
    vision: str
    epics: list[EpicOut]


class TaskOut(BaseModel):
    story_id: int
    title: str
    assignee: str


class SprintPlanOutput(AgentOutput):  # Scrum Master
    goal: str
    story_ids: list[int]
    tasks: list[TaskOut] = []


class FileOut(BaseModel):
    path: str
    content: str


class CodeOutput(AgentOutput):  # Developer / Architect / QA / DevOps write files
    files: list[FileOut] = []
