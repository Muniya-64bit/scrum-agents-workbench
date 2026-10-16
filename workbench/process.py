"""The sprint process as data, and how a retrospective changes it.

A sprint runs with a `ProcessConfig` (the levers). The configuration actually used is recorded in
the `sprint_planned` event (`process`), which makes it a descriptive record of the process. The
retrospective proposes `ProcessChanges`; they are clamped to safe bounds here and stored in
`Sprint.retro["process_changes"]`. The next sprint is planned with the result (`next_process`).
This is the Check -> Act step of a PDCA cycle (see docs/architecture.md, "Process improvement
loop"). No database column is involved: levers live in event payloads and the retro JSON.
"""

import re

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from workbench import config, metrics
from workbench.db import repo
from workbench.schemas import ProcessChanges

CAPACITY_BOUNDS = (3, 40)
RETRY_BOUNDS = (1, 5)
MAX_GUIDELINES = 5
GUIDELINE_CHARS = 200
TEST_FIRST_GUIDELINE = "Write the acceptance tests first and make them pass before committing"


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], int(value)))


def _clean_guideline(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()[:GUIDELINE_CHARS].strip()


class ProcessConfig(BaseModel):
    capacity: int = 10  # story points per sprint, bounds 3..40
    max_fix_retries: int = 3  # developer attempts per bug, bounds 1..5
    test_first: bool = False  # QA writes the tests before the developer codes
    guidelines: list[str] = []  # working agreements, at most 5, each at most 200 chars

    @classmethod
    def defaults(cls) -> "ProcessConfig":
        return cls(capacity=config.DEFAULT_CAPACITY,
                   max_fix_retries=config.DEFAULT_MAX_FIX_RETRIES)

    def apply(self, ch: ProcessChanges) -> tuple["ProcessConfig", dict]:
        """Return the new configuration and the diff `{lever: [old, new]}` of changed levers."""
        new = self.model_copy(deep=True)
        if ch.capacity is not None:
            new.capacity = _clamp(ch.capacity, CAPACITY_BOUNDS)
        if ch.max_fix_retries is not None:
            new.max_fix_retries = _clamp(ch.max_fix_retries, RETRY_BOUNDS)
        if ch.test_first is not None:
            new.test_first = bool(ch.test_first)
        guidelines = list(new.guidelines)
        for raw in ch.add_guidelines:
            text = _clean_guideline(raw)
            if text and text.lower() not in {g.lower() for g in guidelines}:
                guidelines.append(text)
        new.guidelines = guidelines[-MAX_GUIDELINES:]
        diff = {lever: [getattr(self, lever), getattr(new, lever)]
                for lever in ("capacity", "max_fix_retries", "test_first", "guidelines")
                if getattr(self, lever) != getattr(new, lever)}
        return new, diff


def _from_plan(process: dict) -> ProcessConfig:
    if not process:
        return ProcessConfig.defaults()
    try:
        return ProcessConfig(**{**ProcessConfig.defaults().model_dump(), **process})
    except ValidationError:
        return ProcessConfig.defaults()


def current_process(db: Session, project_id: int) -> ProcessConfig:
    """The process of the latest sprint, as recorded when it was planned."""
    sprint = repo.current_sprint(db, project_id)
    if sprint is None:
        return ProcessConfig.defaults()
    return _from_plan(metrics.sprint_plan(db, sprint)["process"])


def next_process(db: Session, project_id: int) -> tuple[ProcessConfig, dict, str]:
    """The process for the next sprint: the current one plus the retro's changes, if any.

    Returns (config, diff, reason)."""
    base = current_process(db, project_id)
    sprint = repo.current_sprint(db, project_id)
    raw = (sprint.retro or {}).get("process_changes") if sprint else None
    if not raw:
        return base, {}, ""
    changes = ProcessChanges(**raw)
    new, diff = base.apply(changes)
    return new, diff, changes.reason


def effective_process(db: Session, project_id: int, phase: str) -> ProcessConfig:
    """The levers in force for an agent working in `phase`."""
    if phase == "sprint_planning":
        return next_process(db, project_id)[0]
    return current_process(db, project_id)


def suggest_process_changes(m: dict, cfg: ProcessConfig) -> ProcessChanges:
    """Rule-based advisor: sprint metrics -> proposed levers. Used by the mock retro and shown
    to the live model as a suggestion."""
    changes, reasons = ProcessChanges(), []
    committed, completed = m.get("committed_points") or 0, m.get("completed_points") or 0
    if committed > 0 and 0 < completed < committed:
        changes.capacity = max(CAPACITY_BOUNDS[0], completed)
        reasons.append("Commit to last sprint's velocity (yesterday's weather)")
    yield_ = m.get("first_pass_yield")
    if not cfg.test_first and ((m.get("bugs_reported") or 0) > 0
                               or (yield_ is not None and yield_ < 1)):
        changes.test_first = True
        changes.add_guidelines = [TEST_FIRST_GUIDELINE]
        reasons.append("Defects escaped into testing; prevent them instead (test-first)")
    if (m.get("retry_limit_hits") or 0) > 0:
        changes.max_fix_retries = min(RETRY_BOUNDS[1], cfg.max_fix_retries + 1)
        reasons.append("A bug hit the fix-retry limit")
    changes.reason = "; ".join(reasons) if reasons else "The process worked; keep it"
    return changes
