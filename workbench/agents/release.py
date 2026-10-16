"""Release step: one versioned, tagged and traceable release per sprint.

`ReleaseAgent` is registered as the `devops` agent. It does not call an LLM itself. It runs a
builder first (the DevOps agent from #12: Dockerfile, CI workflow, RELEASE_NOTES.md) and then adds
what makes the release a versioned increment of the process:

  1. version `v0.<sprint number>.0`
  2. deterministic release notes built from the database (`release_notes`), committed as
     `releases/<version>.md`
  3. an annotated git tag with the version in the sandbox repository
  4. a `release` artifact traced to every story that was completed, and a `release_created` event

Running it again for the same sprint logs `release_exists` and changes nothing."""

import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench import config, metrics
from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.schemas import CodeOutput
from workbench.workspace import Workspace


def _pct(ratio: float | None) -> str:
    return "n/a" if ratio is None else f"{ratio * 100:.1f}%"


def release_notes(db: Session, project_id: int, sprint: m.Sprint, version: str,
                  ws: Workspace) -> str:
    """Markdown release notes for one sprint. Pure: everything comes from the database and the
    sandbox repository's history."""
    project = repo.get(db, m.Project, project_id)
    plan = metrics.sprint_plan(db, sprint)
    stories = [s for s in (repo.get(db, m.UserStory, sid) for sid in plan["story_ids"]) if s]
    planned = {s.id for s in stories}
    done = [s for s in stories if repo.story_is_done(s)]
    window = next((w for w in metrics.sprint_windows(db, project_id) if w.sprint_id == sprint.id),
                  None)
    verified = [e for e in repo.events_since(db, project_id)
                if e.kind == "bug_verified" and e.payload.get("story_id") in planned
                and (window is None or window.start_id <= e.id <= window.end_id)]
    fixed = {e.payload.get("bug_id"): e for e in verified}
    open_bugs = [b for b in repo.bugs(db, project_id, "open") if b.story_id in planned]
    sm = metrics.sprint_metrics(db, sprint)
    process = plan["process"] or {}
    previous = f"v0.{sprint.number - 1}.0" if sprint.number > 1 else None

    lines = [f"# Release {version} — {project.name}", "",
             f"Date: {datetime.now(UTC).date().isoformat()}",
             f"Sprint {sprint.number} goal: {sprint.goal}", "", "## Completed stories"]
    lines += [f"- #{s.id} {s.title} ({len(s.acceptance_criteria or [])} acceptance criteria)"
              for s in done] or ["- None"]
    lines += ["", "## Fixed bugs"]
    lines += [f"- #{bid} {e.message}" for bid, e in fixed.items()] or ["- None"]
    lines += ["", "## Known issues"]
    lines += [f"- #{b.id} (story #{b.story_id}) {b.description}" for b in open_bugs] or ["- None"]
    lines += ["", "## Carried over"]
    lines += [f"- #{s.id} {s.title}" for s in stories if s not in done] or ["- None"]
    retries = process.get("max_fix_retries", config.DEFAULT_MAX_FIX_RETRIES)
    lines += ["", "## Process used",
              f"- Capacity: {process.get('capacity', plan['capacity'])} points",
              f"- Max fix retries: {retries}",
              f"- Test-first: {'on' if process.get('test_first') else 'off'}"]
    lines += [f"- Working agreement: {g}" for g in process.get("guidelines") or []]
    lines += ["", "## Metrics",
              f"- Velocity: {sm['completed_points']} of {sm['committed_points']} points",
              f"- Commitment reliability: {_pct(sm['commitment_reliability'])}",
              f"- First-pass yield: {_pct(sm['first_pass_yield'])}",
              f"- Test pass rate: {_pct(sm['test_pass_rate'])}",
              "", "## Commits"]
    lines += [f"- {subject}" for subject in ws.log_since(previous)] or ["- None"]
    return "\n".join(lines) + "\n"


class ReleaseAgent(BaseAgent):
    role = "devops"

    def __init__(self, builder: BaseAgent | None = None,
                 workspaces_dir: str | Path | None = None):
        super().__init__(LLMClient(mock=True))  # never calls the LLM itself
        self.builder = builder  # the DevOps agent: Dockerfile, CI workflow, RELEASE_NOTES.md
        self.workspaces_dir = workspaces_dir or getattr(builder, "workspaces_dir", None)

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        return ""

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        pass

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        task = task or {}
        tools = Tools(db, project_id, self.role)
        started = time.perf_counter()
        tools.log("agent_started", task.get("name", ""))
        summary = self._release(db, project_id, tools, task)
        tools.log("agent_finished", summary, calls=0, input_tokens=0, output_tokens=0,
                  cache_hits=0, invalid_outputs=0, duration_ms=int((time.perf_counter() - started)
                                                                   * 1000),
                  model="", llm_mode="none", story_id=None)
        return CodeOutput(summary=summary)

    def _release(self, db: Session, project_id: int, tools: Tools, task: dict) -> str:
        sprint = repo.current_sprint(db, project_id)
        if sprint is None:
            tools.log("release_skipped", "No sprint to release", reason="no sprint")
            return "No sprint to release"
        version = f"v0.{sprint.number}.0"
        if any(a.name == f"Release {version}" for a in repo.artifacts(db, project_id, "release")):
            tools.log("release_exists", version, version=version)
            return f"Release {version} already exists"

        if self.builder is not None:
            self.builder.run(db, project_id, {**task, "version": version, "sprint_id": sprint.id})
        ws = Workspace(project_id, self.workspaces_dir).init()
        notes = release_notes(db, project_id, sprint, version, ws)
        ws.write(f"releases/{version}.md", notes)
        sha = ws.commit(f"Release {version}") or ws.head()
        ws.tag(version, f"Release {version}")

        plan = metrics.sprint_plan(db, sprint)
        done_ids = [sid for sid in plan["story_ids"]
                    if (s := repo.get(db, m.UserStory, sid)) and repo.story_is_done(s)]
        art = tools.write_artifact("release", f"Release {version}", notes,
                                   path=f"releases/{version}.md")
        if done_ids:
            tools.link_artifact(art.id, done_ids, "release")
        tools.log("release_created", version, version=version, sha=sha, story_ids=done_ids,
                  artifact_id=art.id, sprint_id=sprint.id)
        return f"Released {version} with {len(done_ids)} stories"
