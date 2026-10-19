"""The Scrum process as an explicit model: one `Activity` per phase.

Each activity names its purpose, the responsible and participating roles, the work products it
consumes and produces (product flow), entry and exit criteria (as in MVP-L's `entry_criteria` /
`exit_criteria`), whether a human gate follows it, and a RACI row. This is the "process model"
of lectures 4 and 11, kept as data so that one definition serves three readers:

- the orchestrator takes its phase -> agents map and its gates from `MODEL`;
- `GET /process/model` serves it to the UI and to anyone writing about the process;
- `docs/process-handbook.md` is generated from it (`handbook_tables`), as lecture 8 recommends:
  keep one model and generate handbooks from it.

Criteria are checked at every phase and logged (`entry_criteria_checked`,
`exit_criteria_checked`). They are advisory (a proscriptive model, lecture 11): unmet criteria are
reported for the human at the gate, not enforced, so a run never stops on a rule.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from workbench.db import models as m
from workbench.db import repo

Check = Callable[[Session, int], bool]
RACI_ROLES = ["human", "product_owner", "scrum_master", "architect", "developer", "qa", "devops"]


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    check: Check


@dataclass(frozen=True)
class Activity:
    phase: str
    name: str
    purpose: str
    responsible: str
    agents: list[str]  # run in this order by the orchestrator
    consumes: list[str]
    produces: list[str]
    entry: list[Criterion]
    exit: list[Criterion]
    gate: bool = False
    raci: dict[str, str] = field(default_factory=dict)


# --- criteria checks ----------------------------------------------------------------------------


def _sprint_stories(db: Session, project_id: int) -> list[m.UserStory]:
    sprint = repo.current_sprint(db, project_id)
    return list(sprint.stories) if sprint else []


def _has_idea(db: Session, project_id: int) -> bool:
    return bool(repo.get(db, m.Project, project_id).idea.strip())


def _has_stories(db: Session, project_id: int) -> bool:
    return bool(repo.backlog(db, project_id))


def _stories_have_criteria(db: Session, project_id: int) -> bool:
    stories = repo.backlog(db, project_id)
    return bool(stories) and all(s.acceptance_criteria for s in stories)


def _has_architecture(db: Session, project_id: int) -> bool:
    return bool(repo.artifacts(db, project_id, "architecture"))


def _has_unplanned(db: Session, project_id: int) -> bool:
    return bool(repo.unplanned_stories(db, project_id))


def _sprint_active(db: Session, project_id: int) -> bool:
    sprint = repo.current_sprint(db, project_id)
    return sprint is not None and sprint.status == "active" and bool(sprint.stories)


def _stories_have_tasks(db: Session, project_id: int) -> bool:
    stories = _sprint_stories(db, project_id)
    return bool(stories) and all(s.tasks for s in stories)


def _within_capacity(db: Session, project_id: int) -> bool:
    sprint = repo.current_sprint(db, project_id)
    return sprint is not None and sum(s.points for s in sprint.stories) <= sprint.capacity


def _stories_tested(db: Session, project_id: int) -> bool:
    stories = _sprint_stories(db, project_id)
    tested = {link.story_id for link, art in repo.trace_links(db, project_id)
              if art.kind == "test"}
    return bool(stories) and all(s.id in tested for s in stories)


def _no_open_bugs(db: Session, project_id: int) -> bool:
    ids = {s.id for s in _sprint_stories(db, project_id)}
    return not any(b.story_id in ids for b in repo.bugs(db, project_id, "open"))


def _all_done(db: Session, project_id: int) -> bool:
    stories = _sprint_stories(db, project_id)
    return bool(stories) and all(repo.story_is_done(s) for s in stories)


def _sprint_exists(db: Session, project_id: int) -> bool:
    return repo.current_sprint(db, project_id) is not None


def _sprint_event(kind: str) -> Check:
    def check(db: Session, project_id: int) -> bool:
        sprint = repo.current_sprint(db, project_id)
        return sprint is not None and any(
            e.kind == kind and (e.payload or {}).get("sprint_id") == sprint.id
            for e in repo.events_since(db, project_id))
    return check


def _retro_saved(db: Session, project_id: int) -> bool:
    sprint = repo.current_sprint(db, project_id)
    return sprint is not None and bool(sprint.retro)


# --- the model ----------------------------------------------------------------------------------

MODEL: list[Activity] = [
    Activity(
        phase="backlog", name="Requirements and sprint-0 design",
        purpose="Turn the product idea into a validated product backlog and a first architecture.",
        responsible="product_owner", agents=["product_owner", "architect"],
        consumes=["Product idea"],
        produces=["Product vision", "Epics and user stories", "Non-functional requirements",
                  "Backlog quality report", "Architecture overview", "Diagrams", "API spec"],
        entry=[Criterion("idea_written", "The project has a product idea", _has_idea)],
        exit=[Criterion("stories_exist", "The backlog has at least one story", _has_stories),
              Criterion("stories_have_criteria", "Every story has acceptance criteria",
                        _stories_have_criteria),
              Criterion("architecture_exists", "A sprint-0 architecture exists",
                        _has_architecture)],
        raci={"human": "C", "product_owner": "R/A", "scrum_master": "I", "architect": "R",
              "developer": "I", "qa": "I", "devops": "I"},
    ),
    Activity(
        phase="sprint_planning", name="Sprint planning",
        purpose="Choose the stories for the sprint within capacity and split them into tasks.",
        responsible="scrum_master", agents=["scrum_master"],
        consumes=["Epics and user stories", "Process levers", "Retrospective actions",
                  "Rejection reason (when re-planning)"],
        produces=["Sprint goal", "Sprint backlog", "Tasks"],
        entry=[Criterion("stories_to_plan", "The backlog has stories not yet in a sprint",
                         _has_unplanned)],
        exit=[Criterion("sprint_has_stories", "The sprint has at least one story",
                        _sprint_active),
              Criterion("stories_have_tasks", "Every sprint story has tasks",
                        _stories_have_tasks),
              Criterion("within_capacity", "Committed points do not exceed the capacity",
                        _within_capacity)],
        gate=True,
        raci={"human": "A", "product_owner": "C", "scrum_master": "R", "architect": "I",
              "developer": "C", "qa": "C", "devops": "I"},
    ),
    Activity(
        phase="execution", name="Sprint execution",
        purpose="Design, build and test each sprint story until it meets the Definition of Done.",
        responsible="developer", agents=["architect", "developer", "qa"],
        consumes=["Sprint backlog", "Tasks", "Architecture overview", "Acceptance criteria",
                  "Non-functional requirements"],
        produces=["Story designs", "Code", "Tests", "Bug reports"],
        entry=[Criterion("sprint_active", "An active sprint has at least one story",
                         _sprint_active)],
        exit=[Criterion("stories_tested", "Every sprint story has tests", _stories_tested),
              Criterion("no_open_bugs", "No sprint story has an open bug", _no_open_bugs),
              Criterion("stories_done", "Every sprint story is done (all tasks done)",
                        _all_done)],
        raci={"human": "I", "product_owner": "C", "scrum_master": "C", "architect": "R",
              "developer": "R/A", "qa": "R", "devops": "I"},
    ),
    Activity(
        phase="review", name="Sprint review",
        purpose="Show the increment and its progress so the human can accept or reject it.",
        responsible="scrum_master", agents=["scrum_master"],
        consumes=["Code", "Tests", "Tasks", "Bug reports"],
        produces=["Stand-up summary", "Burndown snapshot"],
        entry=[Criterion("sprint_exists", "A sprint has been planned", _sprint_exists)],
        exit=[Criterion("burndown_recorded", "A burndown snapshot is recorded for the sprint",
                        _sprint_event("burndown_snapshot"))],
        gate=True,
        raci={"human": "A", "product_owner": "C", "scrum_master": "R", "architect": "I",
              "developer": "I", "qa": "I", "devops": "I"},
    ),
    Activity(
        phase="retro", name="Sprint retrospective",
        purpose="Inspect the sprint's measured results and adapt the process for the next one.",
        responsible="scrum_master", agents=["scrum_master"],
        consumes=["Sprint metrics", "Review feedback", "Process levers"],
        produces=["Retrospective", "Process changes"],
        entry=[Criterion("sprint_exists", "A sprint has been planned", _sprint_exists)],
        exit=[Criterion("retro_saved", "The retrospective is saved", _retro_saved)],
        raci={"human": "I", "product_owner": "C", "scrum_master": "R/A", "architect": "C",
              "developer": "C", "qa": "C", "devops": "C"},
    ),
    Activity(
        phase="release", name="Release",
        purpose="Package the increment: container, CI workflow, release notes and a version tag.",
        responsible="devops", agents=["devops"],
        consumes=["Code", "Tests", "Retrospective"],
        produces=["Dockerfile", "CI workflow", "Release notes", "Version tag"],
        entry=[Criterion("retro_saved", "The sprint's retrospective is saved", _retro_saved)],
        exit=[Criterion("release_created", "A release is recorded for the sprint",
                        _sprint_event("release_created"))],
        raci={"human": "I", "product_owner": "I", "scrum_master": "I", "architect": "I",
              "developer": "C", "qa": "C", "devops": "R/A"},
    ),
]
BY_PHASE: dict[str, Activity] = {a.phase: a for a in MODEL}


def check(db: Session, project_id: int, phase: str, which: str) -> list[dict]:
    """Evaluate the `entry` or `exit` criteria of a phase: `[{id, text, met}]`."""
    activity = BY_PHASE.get(phase)
    if activity is None:
        return []
    return [{"id": c.id, "text": c.text, "met": bool(c.check(db, project_id))}
            for c in getattr(activity, which)]


def log_check(db: Session, project_id: int, phase: str, which: str) -> list[dict]:
    """Check the criteria and log an `entry_criteria_checked` / `exit_criteria_checked` event."""
    results = check(db, project_id, phase, which)
    if results:
        unmet = [r["id"] for r in results if not r["met"]]
        repo.log_event(db, project_id, "orchestrator", f"{which}_criteria_checked",
                       f"{len(results) - len(unmet)} of {len(results)} {which} criteria met",
                       phase=phase, results=results, unmet=unmet)
    return results


def as_dict() -> list[dict]:
    """The model without the check functions, for the API."""
    return [{"phase": a.phase, "name": a.name, "purpose": a.purpose,
             "responsible": a.responsible, "agents": a.agents, "consumes": a.consumes,
             "produces": a.produces, "gate": a.gate, "raci": a.raci,
             "entry": [{"id": c.id, "text": c.text} for c in a.entry],
             "exit": [{"id": c.id, "text": c.text} for c in a.exit]} for a in MODEL]


# --- handbook -----------------------------------------------------------------------------------

ROLE_NAMES = {"human": "Human (stakeholder)", "product_owner": "Product Owner",
              "scrum_master": "Scrum Master", "architect": "Architect",
              "developer": "Developer", "qa": "QA", "devops": "DevOps"}


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def handbook_tables() -> str:
    """The generated part of docs/process-handbook.md."""
    out = ["### Activities", "",
           _row(["#", "Phase", "Activity", "Purpose", "Responsible", "Agents", "Gate"]),
           _row(["---"] * 7)]
    for i, a in enumerate(MODEL, 1):
        out.append(_row([str(i), f"`{a.phase}`", a.name, a.purpose, ROLE_NAMES[a.responsible],
                         ", ".join(ROLE_NAMES[r] for r in a.agents),
                         "Human approval" if a.gate else "-"]))
    out += ["", "### Product flow", "", _row(["Activity", "Consumes", "Produces"]),
            _row(["---"] * 3)]
    out += [_row([a.name, ", ".join(a.consumes), ", ".join(a.produces)]) for a in MODEL]
    out += ["", "### Responsibility assignment matrix (RACI)", "",
            "R = responsible (does the work), A = accountable (decides), C = consulted, "
            "I = informed.", "",
            _row(["Activity", *(ROLE_NAMES[r] for r in RACI_ROLES)]),
            _row(["---"] * (len(RACI_ROLES) + 1))]
    out += [_row([a.name, *(a.raci.get(r, "") for r in RACI_ROLES)]) for a in MODEL]
    out += ["", "### Entry and exit criteria", "",
            _row(["Activity", "Entry criteria", "Exit criteria"]), _row(["---"] * 3)]
    for a in MODEL:
        out.append(_row([a.name, "<br>".join(c.text for c in a.entry),
                         "<br>".join(c.text for c in a.exit)]))
    return "\n".join(out) + "\n"
