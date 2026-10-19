"""Architect agent.

It runs in two phases, each with its own prompt and output schema:
  backlog   -> sprint-0 architecture: overview, Mermaid diagrams (components, data model,
               sequence), OpenAPI spec; every artifact is traced to the whole backlog
  execution -> per-story design delta for sprint stories that have no design yet

`ArchitectAgent` is the single registered agent; it delegates to one handler per phase."""

import re

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import contract, requirements
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.schemas import ArchitectureOutput, DesignDeltaOutput

DESIGN_DIR = "docs/design"
OVERVIEW_CHARS = 4000  # how much of the sprint-0 overview to feed into each design delta


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _story_lines(stories: list[m.UserStory]) -> list[str]:
    lines = []
    for s in stories:
        lines.append(f"[{s.id}] {s.title}: As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
        lines += [f"    - {c}" for c in s.acceptance_criteria]
    return lines


def _designed_endpoints(db: Session, project_id: int) -> list[contract.Endpoint]:
    """The endpoints of the story contracts written so far (each artifact is named `API: ...`)."""
    return [e for a in repo.artifacts(db, project_id, "api_spec") if a.name.startswith("API:")
            for e in contract.parse(a.content)]


class SystemDesigner(BaseAgent):
    role = "architect"
    output_schema = ArchitectureOutput
    system_prompt = """You are a pragmatic software architect doing sprint-0 design.
Design the simplest architecture that delivers the backlog.

Rules:
- The runtime is fixed by the platform: a Python 3.12 FastAPI service with pydantic and SQLite
  through the standard library `sqlite3`. The Tech stack section must name exactly this. Do not
  choose another language, framework or database (no Node.js, MongoDB, Redis or ORMs).
- overview is Markdown with sections: Tech stack, Components, Key decisions (each with a reason).
- diagrams: exactly three, named components, data-model and main-flow.
  components is a Mermaid flowchart, data-model is a Mermaid erDiagram with entity attributes,
  main-flow is a Mermaid sequenceDiagram of the most important user story.
  Write raw Mermaid source without ``` fences.
- api_spec is an OpenAPI 3.0 YAML document covering the endpoints the stories need,
  with request and response schemas.
- Keep it small enough for a team to build in a few days. Do not add features the stories
  do not ask for.
- summary is one sentence."""

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        stories = repo.backlog(db, project_id)
        lines = [f"Project: {project.name}", f"Idea: {project.idea}",
                 f"Vision: {project.vision or project.idea}", ""]
        if stories:
            lines += ["Backlog ([id] title: story, then acceptance criteria):"]
            lines += _story_lines(stories)
        else:
            lines.append("There is no backlog yet; design from the idea.")
        nfrs = requirements.nfrs(db, project_id)
        if nfrs:
            lines += ["", "Non-functional requirements (the architecture must meet these; "
                      "name the decision that meets each one under Key decisions):"]
            lines += [f"- [{n['category']}] {n['requirement']} Measure: {n['measure']}"
                      for n in nfrs]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        project = repo.get(db, m.Project, project_id)
        return {
            "summary": "Designed a three-tier architecture with a REST API and SQLite",
            "overview": (
                f"# Architecture: {project.name}\n\n"
                "## Tech stack\n- Frontend: React\n- Backend: FastAPI (Python)\n"
                "- Database: SQLite via SQLAlchemy\n\n"
                "## Components\n- Web UI calls the REST API\n"
                "- API validates input and stores items\n\n"
                "## Key decisions\n- SQLite: no setup needed for a small app\n"
                "- REST over JSON: simple to test and document with OpenAPI\n"
            ),
            "diagrams": [
                {"name": "components", "mermaid":
                    "flowchart LR\n  UI[Web UI] -->|REST| API[FastAPI]\n  API --> DB[(SQLite)]"},
                {"name": "data-model", "mermaid":
                    "erDiagram\n  USER ||--o{ ITEM : owns\n"
                    "  USER {\n    int id\n    string name\n  }\n"
                    "  ITEM {\n    int id\n    string title\n    bool done\n  }"},
                {"name": "main-flow", "mermaid":
                    "sequenceDiagram\n  actor U as User\n  U->>UI: submit title\n"
                    "  UI->>API: POST /items\n  API->>DB: insert item\n  API-->>UI: 201 item"},
            ],
            "api_spec": (
                "openapi: 3.0.3\n"
                f"info:\n  title: {project.name} API\n  version: 0.1.0\n"
                "paths:\n"
                "  /items:\n"
                "    get:\n      summary: List items\n"
                "      responses:\n        '200':\n          description: All items\n"
                "    post:\n      summary: Create an item\n"
                "      requestBody:\n        content:\n          application/json:\n"
                "            schema:\n              $ref: '#/components/schemas/NewItem'\n"
                "      responses:\n        '201':\n          description: Created\n"
                "        '422':\n          description: Empty title\n"
                "components:\n  schemas:\n"
                "    NewItem:\n      type: object\n      required: [title]\n"
                "      properties:\n        title:\n"
                "          type: string\n          minLength: 1\n"
            ),
        }

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, ArchitectureOutput)
        story_ids = [s.id for s in repo.backlog(tools.db, tools.project_id)]
        written = [tools.write_artifact("architecture", "Architecture overview", out.overview,
                                        path=f"{DESIGN_DIR}/architecture.md")]
        for d in out.diagrams:
            name = _slug(d.name)
            written.append(tools.write_artifact("diagram", f"{name}.mmd", d.mermaid,
                                                path=f"{DESIGN_DIR}/{name}.mmd"))
        written.append(tools.write_artifact("api_spec", "openapi.yaml", out.api_spec,
                                            path=f"{DESIGN_DIR}/openapi.yaml"))
        if story_ids:
            for a in written:
                tools.link_artifact(a.id, story_ids, "architecture")


class DesignDelta(BaseAgent):
    role = "architect"
    output_schema = DesignDeltaOutput
    system_prompt = """You are the software architect refining the design for the current sprint.
For each story listed, describe only what changes relative to the existing architecture.

Rules:
- Return one design per story, using the story_id from the list. Do not invent stories.
- notes is short Markdown: components touched, data model changes, edge cases from the
  acceptance criteria.
- diagram is an optional raw Mermaid sequenceDiagram (no ``` fences) for the story's flow.
- endpoints is the API contract of the story: every HTTP endpoint it needs, and at least one.
  Each has method, path (path parameters in braces, e.g. /books/{book_id}), purpose,
  request_fields ("name: type" for the JSON body), success_status and error_statuses. Use 201 for
  a create, 404 for an unknown id, 409 for a conflict with existing data and 422 for invalid
  input. The Developer builds exactly these endpoints and QA tests exactly these.
- Reuse the paths listed under "Endpoints already designed" and keep one naming style.
- Stay consistent with the existing architecture; do not redesign it.
- summary is one sentence."""

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        overview = repo.artifacts(db, project_id, "architecture")
        lines = ["Existing architecture:",
                 overview[-1].content[:OVERVIEW_CHARS] if overview else "(none yet)", ""]
        existing = _designed_endpoints(db, project_id)
        if existing:
            lines += ["Endpoints already designed:"] + [f"- {e} -> {e.success_status}"
                                                        for e in existing] + [""]
        lines += ["Sprint stories needing design ([id] title: story, then acceptance criteria):"]
        lines += _story_lines(repo.stories_without_design(db, project_id))
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        designs = []
        for s in repo.stories_without_design(db, project_id):
            path = f"/{_slug(s.title)}"
            designs.append({
                "story_id": s.id,
                "notes": f"## {s.title}\n- API: add `POST {path}`\n- Data: no schema change\n"
                         + "".join(f"- Covers: {c}\n" for c in s.acceptance_criteria),
                "diagram": f"sequenceDiagram\n  actor U as User\n  U->>API: POST {path}\n"
                           "  API-->>U: 201 Created",
                "endpoints": [{"method": "POST", "path": path, "purpose": s.title,
                               "request_fields": ["title: str"], "success_status": 201,
                               "error_statuses": [422]}],
            })
        return {"summary": f"Designed {len(designs)} sprint stories", "designs": designs}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, DesignDeltaOutput)
        pending = {s.id: s for s in repo.stories_without_design(tools.db, tools.project_id)}
        for d in out.designs:
            story = pending.pop(d.story_id, None)
            if story is None:  # unknown or duplicate id from the LLM
                continue
            base = f"{DESIGN_DIR}/stories/{story.id}-{_slug(story.title)}"
            tools.write_artifact("design", f"Design: {story.title}", d.notes, story_id=story.id,
                                 path=f"{base}.md")
            if d.diagram:
                tools.write_artifact("diagram", f"Flow: {story.title}", d.diagram,
                                     story_id=story.id, path=f"{base}.mmd")
            tools.write_artifact("api_spec", f"API: {story.title}", contract.render(d.endpoints),
                                 story_id=story.id, path=f"{base}.yaml")
        for story in pending.values():
            tools.log("design_missing", story.title, story_id=story.id)

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        if not repo.stories_without_design(db, project_id):  # nothing to design: no LLM call
            Tools(db, project_id, self.role).log("design_skipped", "No sprint stories need design")
            return DesignDeltaOutput(summary="No sprint stories need design")
        return super().run(db, project_id, task)


class ArchitectAgent(BaseAgent):
    """Registered agent for the `architect` role; picks a handler by the task's phase."""

    role = "architect"

    def __init__(self, llm: LLMClient | None = None):
        super().__init__(llm)
        self.handlers: dict[str, BaseAgent] = {
            "backlog": SystemDesigner(self.llm),
            "execution": DesignDelta(self.llm),
        }

    def _handler(self, task: dict) -> BaseAgent:
        phase = task.get("phase", "backlog")
        if phase not in self.handlers:
            raise ValueError(f"Architect has no handler for phase {phase!r}")
        return self.handlers[phase]

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        return self._handler(task).build_prompt(db, project_id, task)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        return self._handler(task).mock_output(db, project_id, task)

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        self._handler(task).apply(tools, out, task)

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        return self._handler(task).run(db, project_id, task)
