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
    version: int = 1


class TraceRow(BaseModel):
    """One row of the story -> design -> code -> test table."""

    story_id: int
    title: str
    status: str
    design: list[TraceItem] = []
    code: list[TraceItem] = []
    test: list[TraceItem] = []
    other: list[TraceItem] = []
    sprint_number: int | None = None
    tests_passed: int = 0
    tests_failed: int = 0
    last_test_ok: bool | None = None
    open_bugs: int = 0
    ac_count: int = 0
    test_count: int = 0
    complete: bool = False


class EventView(BaseModel):
    id: int
    agent: str
    kind: str
    message: str
    payload: dict
    at: datetime


class BurndownPoint(BaseModel):
    t: float
    step: int
    at: datetime
    remaining: float
    story_id: int | None
    label: str


class IdealPoint(BaseModel):
    t: float
    remaining: float


class BurndownView(BaseModel):
    sprint_id: int
    sprint_number: int
    committed_points: float
    remaining_points: float
    duration_s: float
    closed: bool
    series: list[BurndownPoint]
    ideal: list[IdealPoint]


class SprintMetricsView(BaseModel):
    """Per-sprint GQM metrics; see docs/metrics.md for each definition."""

    sprint_id: int
    sprint_number: int
    goal: str
    closed: bool
    committed_points: int
    committed_stories: int
    completed_points: int
    completed_stories: int
    commitment_reliability: float | None
    carried_over_stories: int
    test_runs: int
    first_pass_yield: float | None
    test_pass_rate: float | None
    bugs_reported: int
    bugs_fixed_in_sprint: int
    bugs_open_at_end: int
    fix_attempts: int
    retry_limit_hits: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_hits: int
    llm_invalid_outputs: int
    est_cost_usd: float
    cost_per_completed_point: float | None
    trace_completeness: float | None
    ac_coverage: float | None
    duration_s: float
    process: dict


class ProjectTotalsView(BaseModel):
    stories_total: int
    stories_done: int
    points_total: int
    points_done: int
    sprint_count: int
    avg_velocity: float | None
    total_llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    llm_modes: list[str]
    loc: int
    trace_completeness: float | None


class UsageView(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    est_cost_usd: float


class GqmMetric(BaseModel):
    key: str
    name: str
    definition: str
    unit: str


class GqmQuestion(BaseModel):
    id: str
    text: str
    metrics: list[GqmMetric]


class GqmGoal(BaseModel):
    id: str
    goal: str
    viewpoint: str
    questions: list[GqmQuestion]


class PricingView(BaseModel):
    model: str
    input_per_mtok: float
    output_per_mtok: float
    source: str


class ProjectMetricsView(BaseModel):
    project: ProjectTotalsView
    sprints: list[SprintMetricsView]
    unattributed: UsageView
    gqm: list[GqmGoal]
    pricing: PricingView
