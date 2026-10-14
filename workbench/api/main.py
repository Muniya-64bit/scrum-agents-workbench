from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.registry import AGENTS
from workbench.db import models as m
from workbench.db import repo
from workbench.db.session import get_session, init_db
from workbench.orchestrator.engine import Orchestrator


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Scrum Agents Workbench", lifespan=lifespan)


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


def _view(p: m.Project) -> dict:
    return {"id": p.id, "name": p.name, "idea": p.idea, "phase": p.phase,
            "awaiting_approval": p.awaiting_approval}


@app.post("/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_session)):
    return _view(repo.create_project(db, body.name, body.idea))


@app.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_session)):
    return _view(_proj(db, project_id))


@app.post("/projects/{project_id}/advance")
def advance(project_id: int, db: Session = Depends(get_session)):
    _proj(db, project_id)
    try:
        return _view(Orchestrator(db, AGENTS).step(project_id))
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/projects/{project_id}/approve")
def approve(project_id: int, approved: bool = True, db: Session = Depends(get_session)):
    _proj(db, project_id)
    try:
        return _view(Orchestrator(db, AGENTS).approve(project_id, approved))
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/projects/{project_id}/events")
def events(project_id: int, after: int = 0, db: Session = Depends(get_session)):
    _proj(db, project_id)
    return [{"id": e.id, "agent": e.agent, "kind": e.kind, "message": e.message,
             "payload": e.payload, "at": e.created_at.isoformat()}
            for e in repo.events_since(db, project_id, after)]
