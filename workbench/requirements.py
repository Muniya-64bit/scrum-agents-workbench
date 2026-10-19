"""Requirements engineering support: non-functional requirements and the backlog quality check.

Non-functional requirements (NFRs) constrain the whole system rather than one story, so they are
not stories. The Product Owner writes them; they are stored as a `requirements` artifact (for
people) and in the payload of an `nfrs_set` event (for code). No database column is involved.

The backlog quality check is requirements validation done by rules, not by the LLM: it looks
for incomplete, ambiguous and inconsistent requirements (lecture 2) the way a process model is
analysed for completeness and consistency (lecture 10). It is advisory. Warnings are logged in a
`backlog_validated` event and shown on the Backlog page; nothing is blocked.
"""

import re

from sqlalchemy.orm import Session

from workbench.db import models as m
from workbench.db import repo

FIBONACCI = (1, 2, 3, 5, 8, 13)
MAX_POINTS = 8  # the Product Owner is told to split anything larger
VAGUE_WORDS = ("fast", "quick", "quickly", "easy", "easily", "user-friendly", "intuitive",
               "simple", "efficient", "flexible", "robust", "seamless", "nice", "good",
               "appropriate", "etc")
_VAGUE = re.compile(r"\b(" + "|".join(re.escape(w) for w in VAGUE_WORDS) + r")\b", re.IGNORECASE)
_GWT = re.compile(r"\bgiven\b.*\bwhen\b.*\bthen\b", re.IGNORECASE | re.DOTALL)
NFR_PATH = "docs/requirements/non-functional.md"

RULES = {
    "no_acceptance_criteria": "Story has no acceptance criteria, so it cannot be tested",
    "criterion_not_gwt": "Acceptance criterion is not in Given/When/Then form",
    "incomplete_story": "Story is missing its role, goal or benefit (As a / I want / so that)",
    "duplicate_title": "Two stories have the same title",
    "points_not_fibonacci": "Story points are not on the 1, 2, 3, 5, 8, 13 scale",
    "story_too_big": f"Story is larger than {MAX_POINTS} points; split it",
    "vague_wording": "Wording is vague and cannot be verified",
    "nfr_not_measurable": "Non-functional requirement has no measurable target",
}


def _warning(rule: str, detail: str, story_id: int | None = None) -> dict:
    return {"rule": rule, "story_id": story_id, "message": RULES[rule], "detail": detail}


def check_backlog(stories: list[m.UserStory], nfrs: list[dict]) -> list[dict]:
    """Warnings for the stories and NFRs, in story order. Each warning is
    `{rule, story_id, message, detail}`; `story_id` is None for NFR warnings."""
    warnings: list[dict] = []
    seen: dict[str, int] = {}
    for s in stories:
        criteria = list(s.acceptance_criteria or [])
        if not criteria:
            warnings.append(_warning("no_acceptance_criteria", s.title, s.id))
        for c in criteria:
            if not _GWT.search(c):
                warnings.append(_warning("criterion_not_gwt", c, s.id))
        if not (s.as_a or "").strip() or not (s.i_want or "").strip() \
                or not (s.so_that or "").strip():
            warnings.append(_warning("incomplete_story", s.title, s.id))
        key = s.title.strip().lower()
        if key in seen:
            warnings.append(_warning("duplicate_title", f"{s.title} (same as #{seen[key]})", s.id))
        else:
            seen[key] = s.id
        if s.points not in FIBONACCI:
            warnings.append(_warning("points_not_fibonacci", f"{s.points} points", s.id))
        if s.points > MAX_POINTS:
            warnings.append(_warning("story_too_big", f"{s.points} points", s.id))
        words = sorted({w.lower() for text in (s.title, s.i_want, *criteria)
                        for w in _VAGUE.findall(text or "")})
        if words:
            warnings.append(_warning("vague_wording", ", ".join(words), s.id))
    for n in nfrs:
        if not re.search(r"\d", n.get("measure") or ""):
            warnings.append(_warning("nfr_not_measurable", n.get("requirement", "")))
    return warnings


def validate_backlog(db: Session, project_id: int, agent: str = "product_owner") -> list[dict]:
    """Run the check on the current backlog and log the `backlog_validated` event."""
    stories = repo.backlog(db, project_id)
    warnings = check_backlog(stories, nfrs(db, project_id))
    flagged = len({w["story_id"] for w in warnings if w["story_id"] is not None})
    repo.log_event(db, project_id, agent, "backlog_validated",
                   f"{len(warnings)} warning(s) on {flagged} of {len(stories)} stories",
                   stories=len(stories), flagged_stories=flagged, warnings=warnings)
    return warnings


def _latest_payload(db: Session, project_id: int, kind: str) -> dict | None:
    found = None
    for e in repo.events_since(db, project_id):
        if e.kind == kind:
            found = e.payload or {}
    return found


def nfrs(db: Session, project_id: int) -> list[dict]:
    """The latest non-functional requirements, or [] if the Product Owner wrote none."""
    payload = _latest_payload(db, project_id, "nfrs_set")
    return list(payload.get("nfrs") or []) if payload else []


def latest_check(db: Session, project_id: int) -> dict | None:
    """The payload of the latest `backlog_validated` event, or None before the first check."""
    return _latest_payload(db, project_id, "backlog_validated")


def nfr_markdown(items: list[dict]) -> str:
    lines = ["# Non-functional requirements", "",
             "| # | Category | Requirement | Measure |", "|---|---|---|---|"]
    for i, n in enumerate(items, 1):
        cells = [n.get("category", ""), n.get("requirement", ""), n.get("measure", "")]
        lines.append(f"| NFR-{i} | " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"
