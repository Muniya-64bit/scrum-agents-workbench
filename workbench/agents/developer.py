"""Developer agent: implements sprint stories as code in the project's sandbox git repository.

One LLM call per story. For each story it:
  1. builds a prompt from the story, its acceptance criteria, the architecture and design notes,
     open bugs from QA and the current workspace files
  2. writes the returned files into the workspace and commits them with a message that references
     the story id (one commit per story)
  3. saves each changed file as a `code` artifact traced to the story and marks the developer's
     tasks done

Stories that already have code are skipped unless QA has filed open bugs against them; then the
agent reruns as a bug fix. Each attempt counts against the bug's `retries`, and after the
sprint's `max_fix_retries` attempts (MAX_FIX_RETRIES unless the process says otherwise) the bug is
left for a human (`bug_retry_limit` event).

With the `test_first` lever the Developer asks QA (`test_writer`) for the story's tests before it
writes any code, and the prompt then lists those tests as the target."""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import contract
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.process import effective_process, fix_retry_limit
from workbench.schemas import CodeOutput
from workbench.workspace import UnsafePath, Workspace, repo_path

MAX_FIX_RETRIES = 3  # default when neither the task nor the sprint's process sets a limit
ARCHITECTURE_CHARS = 4000  # how much of the architecture overview goes into the prompt
FILES_CHARS = 12000  # budget for current file contents in the prompt

SYSTEM_PROMPT = """You are a senior developer on a Scrum team. Implement exactly one user story
in the project's code base.

Rules:
- Return the FULL content of every file you create or change in `files`, with paths relative to
  the repository root using forward slashes and NO leading slash (app/main.py, not
  /app/main.py). Leave out files you do not change.
- Follow the existing architecture and code. If there is no code yet, build a small Python
  FastAPI app: the FastAPI object `app` in app/main.py, dependencies in requirements.txt, data
  kept in SQLite or in memory.
- Satisfy every acceptance criterion. Validate input and return clear HTTP errors.
- When you change a file, return it whole and keep everything in it that other stories already
  use (imports, `app = FastAPI()`, routes, models). Add or change only what this story needs.
- If an API contract is given, implement exactly its methods, paths, JSON field names and success
  status codes (put status_code=201 on a create route), and add no other endpoints.
- Read POST and PUT data from a JSON body declared as a pydantic model, never as bare function
  parameters (FastAPI reads those from the query string). Return 201 for a create and 404 for
  an unknown id. Import every module you use.
- If bugs are listed, fix them first without breaking existing behaviour.
- Only fastapi, pydantic, httpx and the Python standard library are installed; use `sqlite3` for
  storage. Import nothing else, even if the architecture names another stack.
- If the app uses SQLite, create every table with CREATE TABLE IF NOT EXISTS in a function that
  you also call at module level (for example `init_db()` right after its definition). Do not
  create tables only in a startup event or a lifespan: tests import the app and may not run them.
- Do not write tests; QA writes them in tests/. Keep the code small and readable.
- summary is one sentence describing what you changed."""


def _open_bugs(db: Session, story_id: int) -> list[m.Bug]:
    return list(db.query(m.Bug).filter_by(story_id=story_id, status="open").order_by(m.Bug.id))


def _fixable_bugs(db: Session, story_id: int, max_retries: int) -> list[m.Bug]:
    return [b for b in _open_bugs(db, story_id) if b.retries < max_retries]


def _linked(db: Session, project_id: int, story_id: int, relation: str) -> list[m.Artifact]:
    """Artifacts of one relation traced to a story, oldest first."""
    return [a for link, a in repo.trace_links(db, project_id)
            if link.story_id == story_id and link.relation == relation]


def _commit_message(story: m.UserStory, bugs: list[m.Bug]) -> str:
    if bugs:
        ids = ", ".join(f"#{b.id}" for b in bugs)
        return f"Fix bug {ids} in story #{story.id}: {story.title}"
    return f"Story #{story.id}: {story.title}"


class DeveloperAgent(BaseAgent):
    role = "developer"
    system_prompt = SYSTEM_PROMPT
    output_schema = CodeOutput

    def __init__(self, llm: LLMClient | None = None, workspaces_dir: str | Path | None = None):
        super().__init__(llm)
        self.workspaces_dir = workspaces_dir  # None: use config.WORKSPACES_DIR at run time
        # test-first hook: QA sets this to its `write_tests`; None means the lever has no effect
        self.test_writer: Callable[[Session, int, dict], None] | None = None

    def workspace(self, project_id: int) -> Workspace:
        return Workspace(project_id, self.workspaces_dir)

    # --- choosing what to build -------------------------------------------------------------

    def stories_to_build(self, db: Session, project_id: int, task: dict,
                         max_retries: int | None = None) -> list[m.UserStory]:
        """`task["story_id"]` forces one story (QA uses this for a rerun). Otherwise: sprint
        stories with no code yet, plus coded stories that have bugs left to fix."""
        if max_retries is None:
            max_retries = fix_retry_limit(db, project_id, task)
        if task.get("story_id"):
            s = repo.get(db, m.UserStory, task["story_id"])
            return [s] if s and s.epic.project_id == project_id else []
        coded = {link.story_id for link, _ in repo.trace_links(db, project_id)
                 if link.relation == "code"}
        return [s for s in repo.backlog(db, project_id)
                if s.sprint_id is not None
                and (s.id not in coded or _fixable_bugs(db, s.id, max_retries))]

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        tools = Tools(db, project_id, self.role)
        phase = task.get("phase", "execution")
        max_retries = fix_retry_limit(db, project_id, task)  # resolved once per run
        test_first = effective_process(db, project_id, phase).test_first
        for s in repo.backlog(db, project_id):
            for b in _open_bugs(db, s.id):
                if b.retries >= max_retries:
                    tools.log("bug_retry_limit", b.description, bug_id=b.id, story_id=s.id)
        stories = self.stories_to_build(db, project_id, task, max_retries)
        if not stories:  # nothing to implement: no LLM call
            tools.log("code_skipped", "No sprint stories need code")
            return CodeOutput(summary="No sprint stories need code")
        files = []
        for story in stories:
            for t in story.tasks:
                if t.assignee == self.role and t.status == "todo":
                    tools.update_task(t.id, "doing")
            if (test_first and self.test_writer is not None
                    and not _linked(db, project_id, story.id, "code")
                    and not _linked(db, project_id, story.id, "test")):
                self.test_writer(db, project_id, {**task, "story_id": story.id})
            story_task = {**task, "story_id": story.id, "max_fix_retries": max_retries}
            out = super().run(db, project_id, story_task)
            if story_task.get("rejected_routes"):  # refused: ask once more, with the reason
                story_task["retried"] = True
                out = super().run(db, project_id, story_task)
            files += out.files
        return CodeOutput(summary=f"Implemented {len(stories)} stories", files=files)

    # --- one story ----------------------------------------------------------------------------

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        story = repo.get(db, m.UserStory, task["story_id"])
        overview = repo.artifacts(db, project_id, "architecture")
        lines = [f"Project: {project.name}", f"Vision: {project.vision or project.idea}", "",
                 "Architecture:",
                 overview[-1].content[:ARCHITECTURE_CHARS] if overview else "(none yet)", "",
                 f"Story [{story.id}] {story.title}",
                 f"As a {story.as_a}, I want {story.i_want}, so that {story.so_that}",
                 "Acceptance criteria:"]
        lines += [f"- {c}" for c in story.acceptance_criteria] or ["- (none given)"]

        design = [a for link, a in repo.trace_links(db, project_id)
                  if link.story_id == story.id and link.relation in ("design", "api_spec")]
        notes = [a for a in design if a.kind != "api_spec"]
        if notes:
            lines += ["", "Design notes for this story:"] + [a.content for a in notes]
        spec = contract.for_story(db, project_id, story.id)[0]
        if spec:
            lines += ["", "API contract from the Architect (implement exactly these endpoints, "
                          "JSON field names and status codes):", spec]

        max_retries = fix_retry_limit(db, project_id, task)
        bugs = _fixable_bugs(db, story.id, max_retries)
        if bugs:
            lines += ["", "Bugs to fix (from QA):"]
            lines += [f"- [bug {b.id}] {b.description} (attempt {b.retries + 1} of "
                      f"{max_retries})" for b in bugs]

        latest_tests = {a.path: a for a in _linked(db, project_id, story.id, "test")}
        if latest_tests:  # outside the file budget: these define "done"
            lines += ["", "Tests you must make pass (do not edit them):"]
            for path, a in latest_tests.items():
                lines += [f"=== {path} ===", a.content]

        if task.get("rejected_routes"):
            removed = ", ".join(task["rejected_routes"])
            lines += ["", "Your previous answer was refused: it would have removed these "
                          f"endpoints, which other stories already use: {removed}. Return the "
                          "changed files again and keep every existing endpoint."]

        lines += ["", "Current files:"]
        ws, used, skipped = self.workspace(project_id), 0, []
        for path in ws.text_files():
            content = ws.read(path)
            if used + len(content) > FILES_CHARS:
                skipped.append(path)
                continue
            used += len(content)
            lines += [f"=== {path} ===", content]
        if skipped:
            lines.append("Not shown (too large): " + ", ".join(skipped))
        if not ws.text_files():
            lines.append("(empty repository)")
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        project = repo.get(db, m.Project, project_id)
        story = repo.get(db, m.UserStory, task["story_id"])
        criteria = "".join(f"- {c}\n" for c in story.acceptance_criteria)
        max_retries = fix_retry_limit(db, project_id, task)
        fixes = [b for b in db.query(m.Bug).filter_by(story_id=story.id).order_by(m.Bug.id)
                 if b.status == "fixed" or b.retries < max_retries]
        feature = (f'"""Story #{story.id}: {story.title}\n\n'
                   f"As a {story.as_a}, I want {story.i_want}, so that {story.so_that}.\n\n"
                   f'Acceptance criteria:\n{criteria}"""\n\n\n'
                   f"def story_{story.id}() -> str:\n    return {story.title!r}\n")
        feature += "".join(f"\n# Fixed bug #{b.id}: {b.description}\n" for b in fixes)
        files = [{"path": f"app/features/story_{story.id}.py", "content": feature}]
        if not self.workspace(project_id).resolve("app/main.py").exists():
            files += [
                {"path": "requirements.txt", "content": "fastapi\nuvicorn\n"},
                {"path": "app/__init__.py", "content": ""},
                {"path": "app/features/__init__.py", "content": ""},
                {"path": "app/main.py", "content": _MOCK_MAIN.format(title=project.name)},
            ]
        return {"summary": f"Implemented story #{story.id}: {story.title}", "files": files}

    def _removed_routes(self, ws: Workspace, files: list) -> list[contract.Endpoint]:
        """Endpoints the workspace has now that the answer's `app/*.py` files would take away."""
        new: dict[str, str] = {}
        for f in files:
            try:
                path = ws.resolve(repo_path(f.path)).relative_to(ws.path).as_posix()
            except UnsafePath:
                continue
            if path.startswith("app/") and path.endswith(".py"):
                new[path] = f.content
        before = contract.implemented(ws)
        if not new or not before:
            return []
        after = [e for path in ws.text_files()
                 if path.startswith("app/") and path.endswith(".py") and path not in new
                 for e in contract.routes_in(ws.read(path))]
        after += [e for content in new.values() for e in contract.routes_in(content)]
        return contract.lost(before, after)

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, CodeOutput)
        db, story = tools.db, repo.get(tools.db, m.UserStory, task["story_id"])
        bugs = _fixable_bugs(db, story.id, fix_retry_limit(db, tools.project_id, task))
        ws = self.workspace(tools.project_id).init()

        removed = self._removed_routes(ws, out.files)
        if removed:  # a rewrite that drops endpoints other stories use is not applied
            task["rejected_routes"] = [str(e) for e in removed]
            names = ", ".join(task["rejected_routes"])
            tools.log("code_rejected", f"{story.title}: would remove {names}", story_id=story.id,
                      endpoints=task["rejected_routes"])
            if task.get("retried"):  # the second answer was refused as well: a failed attempt
                for b in bugs:
                    tools.record_fix_attempt(b.id, fixed=False)
            return

        changed: dict[str, str] = {}
        for f in out.files:
            try:
                path = ws.resolve(repo_path(f.path)).relative_to(ws.path).as_posix()
                if ws.write(path, f.content):
                    changed[path] = f.content
            except UnsafePath:
                tools.log("file_rejected", f.path, story_id=story.id)

        message = _commit_message(story, bugs)
        sha = ws.commit(message) if changed else None
        if sha is None:
            tools.log("code_unchanged", story.title, story_id=story.id)
        else:
            versions = {}
            for a in repo.artifacts(db, tools.project_id, "code"):
                versions[a.path] = versions.get(a.path, 0) + 1
            for path, content in changed.items():
                tools.write_artifact("code", path, content, story_id=story.id, path=path,
                                     version=versions.get(path, 0) + 1)
            tools.log("code_committed", message, story_id=story.id, sha=sha,
                      files=sorted(changed))
            for t in story.tasks:
                if t.assignee == self.role and t.status != "done":
                    tools.update_task(t.id, "done")
        for b in bugs:
            tools.record_fix_attempt(b.id, fixed=sha is not None)


_MOCK_MAIN = '''from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title={title!r})
items: dict[int, dict] = {{}}


class NewItem(BaseModel):
    title: str


@app.get("/items")
def list_items() -> list[dict]:
    return list(items.values())


@app.post("/items", status_code=201)
def create_item(body: NewItem) -> dict:
    if not body.title.strip():
        raise HTTPException(422, "title must not be empty")
    item = {{"id": len(items) + 1, "title": body.title, "done": False}}
    items[item["id"]] = item
    return item
'''
