from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import metrics
from workbench.agents.registry import AGENTS
from workbench.agents.tools import Tools
from workbench.api.sse import event_stream, event_view
from workbench.api.views import (
    ArtifactSummary,
    ArtifactView,
    BacklogView,
    BugView,
    BurndownView,
    EpicView,
    EventView,
    ProjectMetricsView,
    ProjectView,
    SprintDetailView,
    SprintView,
    StoryView,
    TaskPatch,
    TaskStatus,
    TaskView,
    TraceItem,
    TraceRow,
)
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import SessionLocal, get_session, init_db
from workbench.orchestrator.engine import Orchestrator


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Scrum Agents Workbench", lifespan=lifespan)

DESIGN_KINDS = {"architecture", "diagram", "api_spec", "design"}


class ProjectIn(BaseModel):
    name: str
    idea: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _proj(db: Session, project_id: int) -> m.Project:
    p = repo.get(db, m.Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def _get_or_404(db: Session, model, id_: int, name: str):
    obj = repo.get(db, model, id_)
    if not obj:
        raise HTTPException(404, f"{name} not found")
    return obj


def _view(p: m.Project) -> ProjectView:
    return ProjectView.model_validate(p)


def _sprint_view(s: m.Sprint) -> SprintView:
    return SprintView(id=s.id, number=s.number, goal=s.goal, capacity=s.capacity,
                      status=s.status, retro=s.retro or {},
                      story_ids=[st.id for st in s.stories],
                      points=sum(st.points for st in s.stories))


def _by_priority(stories) -> list[StoryView]:
    return [StoryView.model_validate(s) for s in sorted(stories, key=lambda s: (s.priority, s.id))]


# --- Projects and orchestration ---------------------------------------------------------------

@app.get("/projects", response_model=list[ProjectView])
def list_projects(db: Session = Depends(get_session)):
    return [_view(p) for p in repo.list_projects(db)]


@app.post("/projects", response_model=ProjectView)
def create_project(body: ProjectIn, db: Session = Depends(get_session)):
    return _view(repo.create_project(db, body.name, body.idea))


@app.get("/projects/{project_id}", response_model=ProjectView)
def get_project(project_id: int, db: Session = Depends(get_session)):
    return _view(_proj(db, project_id))


@app.post("/projects/{project_id}/advance", response_model=ProjectView)
def advance(project_id: int, db: Session = Depends(get_session)):
    _proj(db, project_id)
    try:
        return _view(Orchestrator(db, AGENTS).step(project_id))
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/projects/{project_id}/approve", response_model=ProjectView)
def approve(project_id: int, approved: bool = True, comment: str = "",
            db: Session = Depends(get_session)):
    """Clear the pending gate. `comment` (e.g. a reason for rejecting) is logged on the event."""
    _proj(db, project_id)
    try:
        return _view(Orchestrator(db, AGENTS).approve(project_id, approved, comment))
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


# --- Backlog, sprints, tasks ------------------------------------------------------------------

@app.get("/projects/{project_id}/backlog", response_model=BacklogView)
def backlog(project_id: int, db: Session = Depends(get_session)):
    p = _proj(db, project_id)
    epics = [EpicView(id=e.id, title=e.title, description=e.description,
                      stories=_by_priority(e.stories))
             for e in repo.epics(db, project_id)]
    return BacklogView(vision=p.vision, epics=epics)


@app.get("/projects/{project_id}/sprints", response_model=list[SprintView])
def list_sprints(project_id: int, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [_sprint_view(s) for s in repo.sprints(db, project_id)]


@app.get("/sprints/{sprint_id}", response_model=SprintDetailView)
def get_sprint(sprint_id: int, db: Session = Depends(get_session)):
    s = _get_or_404(db, m.Sprint, sprint_id, "sprint")
    tasks = repo.tasks(db, s.project_id, sprint_id=s.id)
    return SprintDetailView(**_sprint_view(s).model_dump(), stories=_by_priority(s.stories),
                            tasks=[TaskView.model_validate(t) for t in tasks])


@app.get("/projects/{project_id}/tasks", response_model=list[TaskView])
def list_tasks(project_id: int, sprint_id: int | None = None, status: TaskStatus | None = None,
               db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [TaskView.model_validate(t) for t in repo.tasks(db, project_id, sprint_id, status)]


@app.patch("/tasks/{task_id}", response_model=TaskView)
def update_task(task_id: int, body: TaskPatch, db: Session = Depends(get_session)):
    """Move a task between board columns. Logged as a `task_updated` event by `human`."""
    t = _get_or_404(db, m.Task, task_id, "task")
    project_id = t.story.epic.project_id
    return TaskView.model_validate(Tools(db, project_id, "human").update_task(t.id, body.status))


# --- Artifacts, bugs, traceability ------------------------------------------------------------

@app.get("/projects/{project_id}/artifacts", response_model=list[ArtifactSummary])
def list_artifacts(project_id: int, kind: str | None = None, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [ArtifactSummary.model_validate(a) for a in repo.artifacts(db, project_id, kind)]


@app.get("/artifacts/{artifact_id}", response_model=ArtifactView)
def get_artifact(artifact_id: int, db: Session = Depends(get_session)):
    a = _get_or_404(db, m.Artifact, artifact_id, "artifact")
    story_ids = [link.story_id for link in db.query(m.TraceLink).filter_by(artifact_id=a.id)]
    return ArtifactView(**ArtifactSummary.model_validate(a).model_dump(), content=a.content,
                        story_ids=story_ids)


@app.get("/projects/{project_id}/bugs", response_model=list[BugView])
def list_bugs(project_id: int, status: str | None = None, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [BugView.model_validate(b) for b in repo.bugs(db, project_id, status)]


@app.get("/projects/{project_id}/traceability", response_model=list[TraceRow])
def traceability(project_id: int, db: Session = Depends(get_session)):
    """Story -> design -> code -> test, one row per backlog story in priority order."""
    _proj(db, project_id)
    details = metrics.trace_details(db, project_id)
    rows = {s.id: TraceRow(story_id=s.id, title=s.title, status=s.status, **details[s.id])
            for s in repo.backlog(db, project_id)}
    for link, a in repo.trace_links(db, project_id):
        row = rows.get(link.story_id)
        if row is None:
            continue
        item = TraceItem(artifact_id=a.id, name=a.name, kind=a.kind, path=a.path)
        if a.kind in DESIGN_KINDS:
            row.design.append(item)
        elif a.kind in ("code", "test"):
            getattr(row, a.kind).append(item)
        else:
            row.other.append(item)
    return list(rows.values())


# --- Metrics ----------------------------------------------------------------------------------

@app.get("/sprints/{sprint_id}/burndown", response_model=BurndownView)
def sprint_burndown(sprint_id: int, db: Session = Depends(get_session)):
    sprint = _get_or_404(db, m.Sprint, sprint_id, "sprint")
    return BurndownView.model_validate(metrics.burndown(db, sprint))


@app.get("/projects/{project_id}/metrics", response_model=ProjectMetricsView)
def project_metrics(project_id: int, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return ProjectMetricsView.model_validate(metrics.project_metrics(db, project_id))


# --- Activity feed ----------------------------------------------------------------------------

@app.get("/projects/{project_id}/events", response_model=list[EventView])
def events(project_id: int, after: int = 0, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [event_view(e) for e in repo.events_since(db, project_id, after)]


@app.get("/projects/{project_id}/stream")
def stream(project_id: int, request: Request, after: int = 0,
           last_event_id: int | None = Header(None), db: Session = Depends(get_session)):
    """Live activity feed as Server-Sent Events. Each `data:` line is one EventView as JSON."""
    _proj(db, project_id)
    start = last_event_id if last_event_id is not None else after
    return StreamingResponse(
        event_stream(SessionLocal, project_id, start, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
