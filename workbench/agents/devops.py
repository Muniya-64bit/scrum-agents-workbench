"""DevOps agent: prepare a generated project for CI and container delivery.

The agent writes only three release files into the project's generated workspace, commits them,
records them as release artifacts, and attempts a Docker build when Docker is available.
"""

import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.schemas import CodeOutput
from workbench.workspace import Workspace

ALLOWED_FILES = {
    "Dockerfile",
    ".github/workflows/ci.yml",
    "RELEASE_NOTES.md",
}
DOCKER_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = """You are a DevOps engineer preparing a small Python application for release.

Return exactly these three files:
- Dockerfile: a small production image that installs the project's dependencies and runs the app.
- .github/workflows/ci.yml: GitHub Actions YAML that installs dependencies and runs pytest.
- RELEASE_NOTES.md: a concise release summary based only on the completed stories supplied.

Rules:
- Return complete file contents and use the paths above exactly.
- Do not add deployment credentials, secrets, registry pushes, or unrelated infrastructure.
- Do not claim incomplete stories were released.
- Keep the Dockerfile and workflow appropriate for the files shown in the project workspace.
- summary is one sentence describing the prepared release."""


def _completed_stories(db: Session, project_id: int) -> list[m.UserStory]:
    """Stories whose planned work is fully complete."""
    return [
        story
        for story in repo.backlog(db, project_id)
        if story.tasks and all(task.status == "done" for task in story.tasks)
    ]


def _release_notes(project: m.Project, stories: list[m.UserStory]) -> str:
    lines = [f"# Release notes: {project.name}", "", "## Completed stories"]
    if stories:
        lines.extend(f"- #{story.id} {story.title}" for story in stories)
    else:
        lines.append("- No completed stories in this release.")
    return "\n".join(lines) + "\n"


class DevOpsAgent(BaseAgent):
    role = "devops"
    system_prompt = SYSTEM_PROMPT
    output_schema = CodeOutput

    def __init__(self, llm=None, workspaces_dir: str | Path | None = None,
                 docker_timeout: int = DOCKER_TIMEOUT_SECONDS):
        super().__init__(llm)
        self.workspaces_dir = workspaces_dir
        self.docker_timeout = docker_timeout

    def workspace(self, project_id: int) -> Workspace:
        return Workspace(project_id, self.workspaces_dir)

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        stories = _completed_stories(db, project_id)
        workspace = self.workspace(project_id)
        files = workspace.files()

        lines = [
            f"Project: {project.name}",
            f"Idea: {project.idea}",
            "",
            "Completed stories:",
        ]
        lines.extend(f"- [{story.id}] {story.title}" for story in stories)
        if not stories:
            lines.append("- (none)")
        lines += ["", "Current workspace files:"]
        lines.extend(f"- {path}" for path in files)
        if not files:
            lines.append("- (empty workspace)")

        for dependency_file in ("requirements.txt", "pyproject.toml"):
            path = workspace.resolve(dependency_file)
            if path.is_file():
                lines += ["", f"=== {dependency_file} ===", path.read_text(encoding="utf-8")]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        project = repo.get(db, m.Project, project_id)
        stories = _completed_stories(db, project_id)
        return {
            "summary": "Prepared Docker, CI, and release-note files",
            "files": [
                {"path": "Dockerfile", "content": _DOCKERFILE},
                {"path": ".github/workflows/ci.yml", "content": _CI_WORKFLOW},
                {"path": "RELEASE_NOTES.md", "content": _release_notes(project, stories)},
            ],
        }

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, CodeOutput)
        workspace = self.workspace(tools.project_id).init()

        supplied = {file.path: file.content for file in out.files}
        for path in sorted(set(supplied) - ALLOWED_FILES):
            tools.log("release_file_rejected", path)

        changed = []
        for path in sorted(ALLOWED_FILES):
            if path not in supplied:
                tools.log("release_file_missing", path)
                continue
            content = supplied[path]
            if not workspace.write(path, content):
                tools.log("release_file_unchanged", path)
                continue
            changed.append(path)
            tools.write_artifact("release", path, content, path=path)

        sha = workspace.commit("Prepare release")
        if sha:
            tools.log("release_committed", "Prepared release files", sha=sha,
                      files=changed)
        self._build_image(tools, workspace.path)

    def _build_image(self, tools: Tools, workspace: Path) -> None:
        if config.MOCK_LLM:
            tools.log("docker_build_skipped", "Docker build disabled in mock mode")
            return
        if not (workspace / "Dockerfile").is_file():
            tools.log("docker_build_skipped", "No Dockerfile was generated")
            return
        docker = shutil.which("docker")
        if docker is None:
            tools.log("docker_build_skipped", "Docker is not available")
            return

        project = repo.get(tools.db, m.Project, tools.project_id)
        name = re.sub(r"[^a-z0-9._-]+", "-", project.name.lower()).strip("-._")
        image = f"{name or f'project-{project.id}'}:latest"
        try:
            result = subprocess.run(
                [docker, "build", "-t", image, "."],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.docker_timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            tools.log("docker_build_failed", str(exc), image=image)
            return

        output = (result.stdout + result.stderr)[-1000:]
        if result.returncode == 0:
            tools.log("docker_build_succeeded", image, image=image)
        else:
            tools.log("docker_build_failed", output, image=image, returncode=result.returncode)


_DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

_CI_WORKFLOW = """name: CI
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pytest -q
"""
