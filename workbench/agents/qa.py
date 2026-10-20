"""QA agent: turns acceptance criteria into pytest tests, runs them, files bugs.

For each sprint story that has code:
  1. one LLM call writes pytest files under `tests/` in the workspace (committed, saved as
     `test` artifacts traced to the story). Stories that already have tests are not rewritten.
  2. the tests run in the workspace (workbench.runner) and the result is parsed
  3. failures become Bug records (one per failing test, no duplicates); a bug the Developer
     called fixed that still fails is reopened
  4. while bugs are open and the Developer has attempts left (the sprint's `max_fix_retries`,
     MAX_FIX_RETRIES by default, tracked in `Bug.retries`), the Developer reruns the story and QA
     tests again. After that the bug stays open for a human.

With the `test_first` lever the Developer calls `write_tests` before it codes: QA writes the tests
from the acceptance criteria and the planned design, and runs them once the code exists.

QA tasks move to `testing` while tests fail and to `done` once they pass."""

import re
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config, contract, runner
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.process import fix_retry_limit
from workbench.schemas import CodeOutput
from workbench.workspace import UnsafePath, Workspace, repo_path

FILES_CHARS = 12000  # budget for code shown to the LLM
DESIGN_CHARS = 4000  # per design / API artifact shown when writing tests before the code
MAX_BUGS_PER_RUN = 5  # one bug per failing test, capped so a broken app does not flood the board
PYTEST_INI = "[pytest]\ntestpaths = tests\npythonpath = .\n"  # keeps pytest off the parent config
GITIGNORE = "__pycache__/\n*.pyc\n.pytest_cache/\n*.db\n*.sqlite3\n"

SYSTEM_PROMPT = """You are a QA engineer on a Scrum team. Write pytest tests for ONE user story.

Rules:
- Write one test per acceptance criterion. Name each test after its criterion, and put the
  Given/When/Then text in a comment or docstring.
- Put all files under `tests/`, for example `tests/test_story_<id>.py`. Return the FULL file
  content in `files`, with relative forward-slash paths and NO leading slash.
- Test the code that exists. For a FastAPI app, use `from fastapi.testclient import TestClient`
  and `from app.main import app`. Keep each test independent of the others.
- Create the client with `with TestClient(app) as client:` so the app's startup code runs. Send
  request data as a JSON body: `client.post(url, json={...})`. Import every module your tests use.
- Assert status codes and key fields, never the exact text of an error message: frameworks word
  their own validation errors.
- Do not change application code. Do not use the network or sleep.
- summary is one sentence."""


# A failure caused by the test code itself (not by the application): QA rewrites its tests
_TEST_SIDE = re.compile(r"NameError|ImportError|ModuleNotFoundError|SyntaxError|IndentationError|"
                        r"fixture .* not found|failed on setup|collection|No tests were collected",
                        re.IGNORECASE)


def _code_error(output: str) -> bool:
    """The traceback names the application's own files (`app/main.py:37` or, for a syntax
    error, `File ".../app/main.py", line 37`), so the code is at fault, not the test."""
    return bool(re.search(r"\bapp/[\w/]+\.py\b", output))


def _test_side(f: runner.Failure, output: str = "") -> bool:
    """True when the test code itself is broken (and not the application it imports)."""
    return (not f.test.startswith("contract") and not _code_error(output)
            and (f.test in ("collection", "pytest") or bool(_TEST_SIDE.search(f.message))))


def _error_line(output: str) -> str:
    """The `E   SomeError: ...` line of pytest's output that names the real reason."""
    named = re.search(r"^E\s+(\w*(?:Error|Exception)\b.*)$", output, re.MULTILINE)
    first = re.search(r"^E\s+(.+)$", output, re.MULTILINE)
    m = named or first
    return m.group(1).strip()[:200] if m else ""


def _tests_for(db: Session, project_id: int, story_id: int) -> list[str]:
    paths = {a.path for link, a in repo.trace_links(db, project_id)
             if link.story_id == story_id and link.relation == "test" and a.path}
    return sorted(paths)


def _has_code(db: Session, project_id: int, story_id: int) -> bool:
    return any(link.story_id == story_id and link.relation == "code"
               for link, _ in repo.trace_links(db, project_id))


def _bugs(db: Session, story_id: int) -> list[m.Bug]:
    return list(db.query(m.Bug).filter_by(story_id=story_id).order_by(m.Bug.id))


def _fixable(bugs: list[m.Bug], max_retries: int) -> list[m.Bug]:
    return [b for b in bugs if b.status == "open" and b.retries < max_retries]


def _stories_with_runs(db: Session, project_id: int) -> set[int]:
    return {e.payload.get("story_id") for e in repo.events_since(db, project_id)
            if e.kind == "test_run"}


def _changed_since_run(db: Session, project_id: int) -> set[int]:
    """Stories whose code was committed after their last test run, for example a carried-over
    bug that the Developer fixed before QA's turn."""
    committed: dict[int, int] = {}
    ran: dict[int, int] = {}
    for e in repo.events_since(db, project_id):
        story_id = e.payload.get("story_id")
        if story_id is None:
            continue
        if e.kind == "code_committed":
            committed[story_id] = e.id
        elif e.kind == "test_run":
            ran[story_id] = e.id
    return {sid for sid, event_id in committed.items() if event_id > ran.get(sid, 0)}


class QAAgent(BaseAgent):
    role = "qa"
    system_prompt = SYSTEM_PROMPT
    output_schema = CodeOutput

    def __init__(self, llm: LLMClient | None = None, workspaces_dir: str | Path | None = None,
                 developer: BaseAgent | None = None, timeout: int = runner.TIMEOUT_SECONDS):
        super().__init__(llm)
        self.workspaces_dir = workspaces_dir  # None: use config.WORKSPACES_DIR at run time
        self.developer = developer  # reran for bug fixes; None means QA only reports bugs
        self.timeout = timeout
        if developer is not None and hasattr(developer, "test_writer"):
            developer.test_writer = self.write_tests  # the test-first lever

    def workspace(self, project_id: int) -> Workspace:
        return Workspace(project_id, self.workspaces_dir)

    # --- choosing what to test --------------------------------------------------------------

    def stories_to_test(self, db: Session, project_id: int, task: dict,
                        max_retries: int | None = None) -> list[m.UserStory]:
        """`task["story_id"]` forces one story. Otherwise: sprint stories that have code and
        either no tests yet, tests that never ran (written first), code changed since the last
        run or open bugs."""
        if task.get("story_id"):
            s = repo.get(db, m.UserStory, task["story_id"])
            return [s] if s and s.epic.project_id == project_id else []
        if max_retries is None:
            max_retries = fix_retry_limit(db, project_id, task)
        ran = _stories_with_runs(db, project_id)
        changed = _changed_since_run(db, project_id)
        return [s for s in repo.backlog(db, project_id)
                if s.sprint_id is not None and _has_code(db, project_id, s.id)
                and (not _tests_for(db, project_id, s.id) or s.id not in ran
                     or s.id in changed or _fixable(_bugs(db, s.id), max_retries))]

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        tools = Tools(db, project_id, self.role)
        max_retries = fix_retry_limit(db, project_id, task)  # resolved once per run
        stories = self.stories_to_test(db, project_id, task, max_retries)
        if not stories:  # nothing to test: no LLM call
            tools.log("tests_skipped", "No stories with code need testing")
            return CodeOutput(summary="No stories need testing")
        passing = sum(self._test_story(db, tools, s, task, max_retries) for s in stories)
        return CodeOutput(summary=f"Tested {len(stories)} stories, {passing} passing")

    # --- one story ----------------------------------------------------------------------------

    def write_tests(self, db: Session, project_id: int, task: dict) -> None:
        """Test-first: write the story's tests before its code exists. The Developer calls this
        when the `test_first` lever is on. The tests run later, in `run`."""
        story_id = task["story_id"]
        if _tests_for(db, project_id, story_id):
            return
        BaseAgent.run(self, db, project_id, {**task, "name": "tests first", "story_id": story_id,
                                             "test_first": True})
        if _tests_for(db, project_id, story_id):
            Tools(db, project_id, self.role).log(
                "tests_written_first", f"Tests for story #{story_id} written before the code",
                story_id=story_id)

    def _test_story(self, db: Session, tools: Tools, story: m.UserStory, task: dict,
                    max_retries: int) -> bool:
        project_id = tools.project_id
        if not _has_code(db, project_id, story.id):
            tools.log("tests_skipped", f"Story #{story.id} has no code yet", story_id=story.id)
            return False
        if not _tests_for(db, project_id, story.id):
            super().run(db, project_id, {**task, "story_id": story.id})  # LLM writes the tests
        targets = _tests_for(db, project_id, story.id)
        if not targets:
            tools.log("tests_missing", f"No valid tests for story #{story.id}", story_id=story.id)
            return False
        for attempt in range(max_retries + 1):
            result = runner.run_pytest(self.workspace(project_id).path, targets, self.timeout)
            result.failures[:0] = self._contract_failures(db, project_id, story)
            self._record(tools, story, result)
            if result.ok:
                return True
            if attempt == max_retries:
                break
            if any(_test_side(f, result.output) for f in result.failures):  # tests are wrong
                if not self._revise_tests(db, tools, story, task, result):
                    break  # the same file again: another attempt would repeat this one
            elif self.developer is not None and _fixable(_bugs(db, story.id), max_retries):
                self.developer.run(db, project_id, {"name": "bug fix", "phase": "execution",
                                                    "story_id": story.id,
                                                    "max_fix_retries": max_retries})
            else:
                break
        if _bugs(db, story.id):
            tools.log("bugs_left_open", f"Story #{story.id} still fails after the fix attempts",
                      story_id=story.id)
        return False

    def _contract_failures(self, db: Session, project_id: int,
                           story: m.UserStory) -> list[runner.Failure]:
        """Endpoints of the Architect's contract that the code does not implement (checked by
        rules, live runs only: the mock Developer writes no routes)."""
        if config.MOCK_LLM:
            return []
        wanted = contract.for_story(db, project_id, story.id)[1]
        if not wanted:
            return []
        code = contract.implemented(self.workspace(project_id))
        return [runner.Failure(f"contract {e}", problem)
                for e, problem in contract.violations(wanted, code)]

    def _revise_tests(self, db: Session, tools: Tools, story: m.UserStory, task: dict,
                      result: runner.TestResult) -> bool:
        """One LLM call: rewrite the story's tests from the failing output. True if they changed."""
        ws = self.workspace(tools.project_id)
        targets = _tests_for(db, tools.project_id, story.id)
        before = {p: ws.read(p) for p in targets}
        errors = "\n".join(f"- {f.test}: {f.message}" for f in result.failures[:MAX_BUGS_PER_RUN])
        BaseAgent.run(self, db, tools.project_id, {
            **task, "story_id": story.id, "name": "revise tests", "revise_tests": True,
            "failures": f"{errors}\n\npytest output:\n{result.output[-1500:]}"})
        changed = {p: ws.read(p) for p in targets} != before
        tools.log("tests_revised" if changed else "tests_revision_unchanged",
                  f"Story #{story.id}: {story.title}", story_id=story.id)
        return changed

    def _record(self, tools: Tools, story: m.UserStory, result: runner.TestResult) -> None:
        failed = len(result.failures)
        tools.log("test_run", f"{result.passed} passed, {failed} failed", story_id=story.id,
                  passed=result.passed, failed=failed, ok=result.ok)
        qa_tasks = [t for t in story.tasks if t.assignee == self.role]
        bugs = _bugs(tools.db, story.id)
        if result.ok:
            for b in bugs:  # open ones no longer reproduce; "fixed" ones are now confirmed
                tools.verify_bug(b.id)
            for t in qa_tasks:
                if t.status != "done":
                    tools.update_task(t.id, "done")
            return
        for t in qa_tasks:
            if t.status in ("todo", "doing"):
                tools.update_task(t.id, "testing")
        reportable = [f for f in result.failures if not _test_side(f, result.output)]
        reason = _error_line(result.output)
        for f in reportable[:MAX_BUGS_PER_RUN]:
            known = next((b for b in bugs if b.description.startswith(f"{f.test}:")), None)
            if known is None:
                detail = f" ({reason})" if reason and reason not in f.message and (
                    f.test in ("collection", "pytest") or "collection" in f.message) else ""
                tools.report_bug(story.id, f"{f.test}: {f.message}{detail}")
            elif known.status == "fixed":  # the Developer said fixed, but it still fails
                tools.reopen_bug(known.id)

    # --- writing the tests (one LLM call per story) -------------------------------------------

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        story = repo.get(db, m.UserStory, task["story_id"])
        lines = [f"Project: {project.name}", "",
                 f"Story [{story.id}] {story.title}",
                 f"As a {story.as_a}, I want {story.i_want}, so that {story.so_that}",
                 "Acceptance criteria:"]
        lines += [f"- {c}" for c in story.acceptance_criteria] or ["- (none given)"]
        spec = contract.for_story(db, project_id, story.id)[0]
        if spec:
            lines += ["", "API contract from the Architect (call exactly these methods and paths, "
                          "send these JSON fields, expect these status codes):", spec]
        lines += ["", f"Write the tests in tests/test_story_{story.id}.py.", ""]
        if task.get("test_first"):
            lines += self._planned_api(db, project_id, story)
            return "\n".join(lines)
        lines.append("Code to test:")
        ws, used = self.workspace(project_id), 0
        for path in ws.text_files():
            if path.startswith("tests/") or not path.endswith((".py", ".txt")):
                continue
            content = ws.read(path)
            if used + len(content) > FILES_CHARS:
                lines.append(f"(not shown, too large: {path})")
                continue
            used += len(content)
            lines += [f"=== {path} ===", content]
        if task.get("revise_tests"):
            lines += ["", "Your tests failed because of a mistake in the test code itself (a "
                          "missing import, a wrong name, a bad setup), not in the application:",
                      task.get("failures", ""), "", "Your current test file:"]
            ws = self.workspace(project_id)
            for path in _tests_for(db, project_id, story.id):
                lines += [f"=== {path} ===", ws.read(path)]
            lines += ["", "Return the corrected file in full. Keep one test per acceptance "
                          "criterion and the same expectations."]
        return "\n".join(lines)

    def _planned_api(self, db: Session, project_id: int, story: m.UserStory) -> list[str]:
        """Prompt lines for tests written before the code: the story's design and API spec."""
        lines = ["There is no implementation yet. Write the tests from the acceptance criteria "
                 "against this planned API:",
                 "Use `from fastapi.testclient import TestClient` and `from app.main import app`."]
        for link, a in repo.trace_links(db, project_id):
            if link.story_id == story.id and link.relation in ("design", "api_spec"):
                lines += [f"=== {a.name} ===", a.content[:DESIGN_CHARS]]
        specs = repo.artifacts(db, project_id, "api_spec")
        if specs:
            lines += [f"=== {specs[-1].name} ===", specs[-1].content[:DESIGN_CHARS]]
        return lines

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        story = repo.get(db, m.UserStory, task["story_id"])
        title = story.title
        body = [f'"""Tests for story #{story.id}: {title} (generated in mock mode)."""', "",
                f"from app.features import story_{story.id}", ""]
        for i, criterion in enumerate(story.acceptance_criteria or ["The story exists"], 1):
            comment = " ".join(criterion.split())
            body += ["", f"def test_criterion_{i}():", f"    # {comment}",
                     f"    assert story_{story.id}.story_{story.id}() == {title!r}", ""]
        return {"summary": f"Wrote tests for story #{story.id}",
                "files": [{"path": f"tests/test_story_{story.id}.py",
                           "content": "\n".join(body).rstrip() + "\n"}]}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, CodeOutput)
        db, story = tools.db, repo.get(tools.db, m.UserStory, task["story_id"])
        ws = self.workspace(tools.project_id).init()

        changed: dict[str, str] = {}
        for f in out.files:
            try:
                path = ws.resolve(repo_path(f.path)).relative_to(ws.path).as_posix()
            except UnsafePath:
                tools.log("file_rejected", f.path, story_id=story.id)
                continue
            if not path.startswith("tests/") or not path.endswith(".py"):
                tools.log("file_rejected", f"{f.path} (QA may only write tests/*.py)",
                          story_id=story.id)
                continue
            if ws.write(path, f.content):
                changed[path] = f.content
        if changed:  # scaffolded with the first tests, in the same commit
            ws.write("pytest.ini", PYTEST_INI)
            ws.write(".gitignore", GITIGNORE)

        sha = ws.commit(f"Tests for story #{story.id}: {story.title}") if changed else None
        if sha is None:
            tools.log("tests_unchanged", story.title, story_id=story.id)
            return
        versions: dict[str, int] = {}
        for a in repo.artifacts(db, tools.project_id, "test"):
            versions[a.path] = versions.get(a.path, 0) + 1
        for path, content in changed.items():
            tools.write_artifact("test", path, content, story_id=story.id, path=path,
                                 version=versions.get(path, 0) + 1)
        tools.log("tests_committed", story.title, story_id=story.id, sha=sha,
                  files=sorted(changed))
