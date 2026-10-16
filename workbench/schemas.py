"""Shared contracts. Every agent's structured output is a pydantic model; the LLM wrapper
validates against it. Change these only with team agreement (see docs/architecture.md)."""

from pydantic import BaseModel, Field, field_validator

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


class StandupOutput(AgentOutput):  # Scrum Master, from task states
    yesterday: list[str] = []
    today: list[str] = []
    blockers: list[str] = []


class ProcessChanges(BaseModel):
    """Process levers the retrospective may change for the next sprint. Bounds are applied in
    code (`workbench.process.ProcessConfig.apply`), not here."""

    capacity: int | None = Field(None, description="Story points for the next sprint, 3 to 40, "
                                 "or null to keep")
    max_fix_retries: int | None = Field(None, description="Developer attempts per bug, 1 to 5, "
                                        "or null to keep")
    test_first: bool | None = Field(None, description="true: QA writes the acceptance tests "
                                    "before the Developer codes; null to keep")
    add_guidelines: list[str] = Field(default=[], description="New working agreements for every "
                                      "agent, short sentences (at most 5 are kept)")
    reason: str = Field("", description="One sentence: which data justifies these changes")


class RetroOutput(AgentOutput):  # Scrum Master
    went_well: list[str] = []
    went_wrong: list[str] = []
    actions: list[str] = Field(default=[], description="Improvements for the next sprint")
    process_changes: ProcessChanges = ProcessChanges()


class FileOut(BaseModel):
    path: str
    content: str


class CodeOutput(AgentOutput):  # Developer / Architect / QA / DevOps write files
    files: list[FileOut] = []


MERMAID_TYPES = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "erDiagram",
                 "stateDiagram", "stateDiagram-v2")


def _check_mermaid(text: str) -> str:
    """Reject diagrams that do not start with a Mermaid diagram type, so the LLM retries."""
    first = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    if first not in MERMAID_TYPES:
        raise ValueError(f"Mermaid diagram must start with one of {', '.join(MERMAID_TYPES)}")
    return text.strip()


class DiagramOut(BaseModel):
    name: str = Field(description="Short kebab-case name, e.g. components, data-model")
    mermaid: str = Field(description="Mermaid source, no ``` fences")

    @field_validator("mermaid")
    @classmethod
    def _mermaid(cls, v: str) -> str:
        return _check_mermaid(v)


class ArchitectureOutput(AgentOutput):  # Architect, sprint 0
    overview: str = Field(description="Markdown: tech stack, components, key decisions")
    diagrams: list[DiagramOut] = Field(min_length=1)
    api_spec: str = Field(description="OpenAPI 3 YAML")


class StoryDesignOut(BaseModel):
    story_id: int
    notes: str = Field(description="Markdown: what changes in the design for this story")
    diagram: str = Field("", description="Optional Mermaid diagram, no ``` fences")
    api_spec: str = Field("", description="Optional OpenAPI 3 YAML snippet (paths only)")

    @field_validator("diagram")
    @classmethod
    def _diagram(cls, v: str) -> str:
        return _check_mermaid(v) if v.strip() else ""


class DesignDeltaOutput(AgentOutput):  # Architect, per sprint
    designs: list[StoryDesignOut] = []
