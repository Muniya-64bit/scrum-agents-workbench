"""Export a project: a Markdown report of what the team did and a zip of what it built.

Both come from the database and the project's sandbox repository, so an export shows the same
numbers as the Results page. The report is plain Markdown: it can be read, attached or converted."""

import io
import re
import zipfile
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from workbench import metrics, requirements
from workbench.db import models as m
from workbench.db import repo
from workbench.runner import DB_SUFFIXES
from workbench.workspace import Workspace

REPORT_NAME = "PROJECT_REPORT.md"
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


def _pct(ratio: float | None) -> str:
    return "n/a" if ratio is None else f"{ratio * 100:.0f}%"


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def filename(project: m.Project) -> str:
    """A safe file name stem for the project: `Todo app` -> `todo-app`."""
    return re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-") or f"project-{project.id}"


def report(db: Session, project_id: int) -> str:
    """The project report: idea, requirements, backlog, every sprint, releases, checks, bugs."""
    project = repo.get(db, m.Project, project_id)
    data = metrics.project_metrics(db, project_id)
    totals = data["project"]
    lines = [f"# {project.name}: project report", "",
             f"Generated {datetime.now(UTC).date().isoformat()} · phase: {project.phase}", "",
             "## Idea", "", project.idea, ""]
    if project.vision:
        lines += ["## Vision", "", project.vision, ""]

    lines += ["## Outcome", "",
              f"- Stories done: {totals['stories_done']} of {totals['stories_total']}",
              f"- Points delivered: {totals['points_done']} of {totals['points_total']}",
              f"- Sprints: {totals['sprint_count']}",
              f"- Lines of code generated: {totals['loc']}",
              f"- Model calls: {totals['total_llm_calls']} "
              f"({totals['total_input_tokens'] + totals['total_output_tokens']:,} tokens)", ""]

    items = requirements.nfrs(db, project_id)
    if items:
        lines += ["## Non-functional requirements", "", "| # | Category | Requirement | Measure |",
                  "|---|---|---|---|"]
        lines += [f"| NFR-{i} | {_cell(n.get('category', ''))} | {_cell(n.get('requirement', ''))} "
                  f"| {_cell(n.get('measure', ''))} |" for i, n in enumerate(items, 1)]
        lines.append("")

    lines += ["## Backlog", ""]
    for epic in repo.epics(db, project_id):
        lines += [f"### {epic.title}", ""] + ([epic.description, ""] if epic.description else [])
        for s in sorted(epic.stories, key=lambda s: (s.priority, s.id)):
            status = "done" if repo.story_is_done(s) else s.status
            lines.append(f"- **#{s.id} {s.title}** (P{s.priority}, {s.points} pt, {status})")
            if s.as_a or s.i_want:
                lines.append(f"  - As a {s.as_a}, I want {s.i_want}, so that {s.so_that}.")
            lines += [f"  - {c}" for c in s.acceptance_criteria or []]
        lines.append("")

    if data["sprints"]:
        lines += ["## Sprints", "",
                  "| Sprint | Goal | Planned | Completed | Carried over | Test pass rate "
                  "| Open bugs |", "|---|---|---|---|---|---|---|"]
        for s in data["sprints"]:
            lines.append(
                f"| {s['sprint_number']} | {_cell(s['goal'])} | {s['committed_stories']} stories, "
                f"{s['committed_points']} pt | {s['completed_stories']} stories, "
                f"{s['completed_points']} pt | {s['carried_over_stories']} | "
                f"{_pct(s['test_pass_rate'])} | {s['bugs_open_at_end']} |")
        lines.append("")
        for sprint in repo.sprints(db, project_id):
            retro = sprint.retro or {}
            if retro:
                lines += [f"### Retrospective of sprint {sprint.number}", ""]
                for title, key in (("Went well", "went_well"), ("Went wrong", "went_wrong"),
                                   ("Actions", "actions")):
                    lines += [f"- {title}: {_cell(x)}" for x in retro.get(key) or []]
                lines.append("")

    events = repo.events_since(db, project_id)
    releases = [e for e in events if e.kind == "release_created"]
    if releases:
        lines += ["## Releases", ""]
        lines += [f"- {e.payload.get('version')}: {len(e.payload.get('story_ids') or [])} "
                  f"stories completed" for e in releases]
        lines.append("")
    checks = [e for e in events if e.kind == "release_check"]
    if checks:
        lines += ["## Release checks", ""]
        lines += [f"- {e.payload.get('version')} · {e.payload.get('name')}: "
                  f"{e.payload.get('status')}" + (f" ({e.payload['detail']})"
                                                  if e.payload.get("detail") else "")
                  for e in checks]
        lines.append("")

    bugs = repo.bugs(db, project_id, "open")
    lines += ["## Open bugs", ""]
    lines += [f"- #{b.id} (story #{b.story_id}): {_cell(b.description)}"
              for b in bugs] or ["- None"]
    return "\n".join(lines) + "\n"


def archive(db: Session, project_id: int) -> bytes:
    """A zip with the report and the generated project (`project/...`, without git history,
    caches or database files)."""
    ws = Workspace(project_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(REPORT_NAME, report(db, project_id))
        for rel in ws.files():
            parts = rel.split("/")
            if _SKIP_DIRS & set(parts) or rel.endswith((".pyc",) + DB_SUFFIXES):
                continue
            z.write(ws.path / rel, f"project/{rel}")
    return buffer.getvalue()
