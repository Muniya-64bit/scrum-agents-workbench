"""Product Owner agent: product idea -> vision, epics, user stories with acceptance criteria."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.llm.client import LLMClient
from workbench.requirements import check_backlog, nfrs, validate_backlog
from workbench.schemas import BacklogOutput, RefinementOutput

SYSTEM_PROMPT = """You are an experienced Scrum Product Owner.
Turn the product idea into a small, realistic product backlog.

Rules:
- Write a one or two sentence product vision.
- Group work into 2 to 4 epics, each with a one-sentence description and 2 to 4 user stories
  (6 to 10 stories in total).
- Each story has as_a, i_want and so_that fields, which together read as
  "As a <role>, I want <goal>, so that <benefit>".
- Each story has 2 to 4 acceptance criteria, never just one: the main flow, and at least one
  error or edge case (invalid input, missing item, limit reached). Every criterion is ONE string
  in the form "Given <context> When <action> Then <observable result>" and is testable.
- Name the data a story uses (fields, limits, status codes where they matter), so a developer
  can build it and a tester can check it without asking.
- priority is 1 (highest) to 5 (lowest). Put the stories needed for a first working version at
  priority 1 or 2.
- points is a relative size estimate (1, 2, 3, 5, 8 or 13). Split anything larger than 8.
- Avoid vague words such as fast, easy, simple or user-friendly; say what can be checked.
- nfrs: 2 to 4 non-functional requirements for the whole system. category is product (speed,
  reliability, usability, security of the software), organizational (standards, policies) or
  external (laws, privacy, interoperability). requirement is one sentence using "shall";
  measure is how it is verified and contains a number.
- Keep the scope small enough for a team to build in a few days.
- summary is one sentence describing what you produced."""


REFINE_PROMPT = """You are a Scrum Product Owner refining the backlog before sprint planning.
You are given the stories that are not in a sprint yet, each with the problems a quality check
found in it.

Rules:
- Return one entry for each story you change, with its story_id from the list. Do not invent
  stories.
- acceptance_criteria: 2 to 4 strings, each "Given <context> When <action> Then <observable
  result>" and testable. Keep the good ones, fix or replace the bad ones, and include an error or
  edge case.
- points: 1, 2, 3, 5 or 8 only. A story that was too big gets the largest size it still fits.
- priority: 1 (highest) to 5. Keep it unless the problem is the order.
- Avoid vague words such as fast, easy, simple or user-friendly: say what can be checked.
- summary is one sentence."""

_ALLOWED_POINTS = (1, 2, 3, 5, 8)
_GENERIC_CRITERIA = (
    "Given the app is running When I use '{title}' with invalid input "
    "Then I get a clear error and nothing is changed",
    "Given the app is running When I use '{title}' with valid input "
    "Then the expected result is returned",
)


def story_problems(db: Session, project_id: int) -> dict[int, list[dict]]:
    """The backlog check's warnings for the stories that are not in a sprint yet, by story id.
    NFR warnings belong to no story and are not refined here."""
    pending = repo.unplanned_stories(db, project_id)
    found: dict[int, list[dict]] = {}
    for w in check_backlog(pending, nfrs(db, project_id)):
        if w["story_id"] is not None:
            found.setdefault(w["story_id"], []).append(w)
    return found


class BacklogRefiner(BaseAgent):
    """Backlog refinement: before each sprint is planned, the Product Owner fixes the stories
    that the rule-based backlog check flagged. Without problems there is nothing to do, and no
    model call is made."""

    role = "product_owner"
    system_prompt = REFINE_PROMPT
    output_schema = RefinementOutput

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        if not story_problems(db, project_id):
            Tools(db, project_id, self.role).log(
                "refinement_skipped", "Nothing to refine: the backlog check found no problems")
            return RefinementOutput(summary="Nothing to refine")
        return super().run(db, project_id, task)

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        problems = story_problems(db, project_id)
        lines = ["Stories that are not in a sprint yet and the problems found in them "
                 "(id | priority | points | title):"]
        for s in repo.unplanned_stories(db, project_id):
            if s.id not in problems:
                continue
            lines.append(f"{s.id} | {s.priority} | {s.points} | {s.title}")
            lines += ([f"  criterion: {c}" for c in s.acceptance_criteria or []]
                      or ["  (no criteria)"])
            lines += [f"  PROBLEM: {w['message']}" + (f" ({w['detail']})" if w["detail"] else "")
                      for w in problems[s.id]]
        return "\n".join(lines)

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        """A deterministic fix: keep the criteria in Given/When/Then form, add a generic pair if
        fewer than two are left, and round the points to the scale (at most 8)."""
        problems = story_problems(db, project_id)
        refined = []
        for s in repo.unplanned_stories(db, project_id):
            if s.id not in problems:
                continue
            criteria = [c for c in s.acceptance_criteria or []
                        if "given" in c.lower() and "when" in c.lower() and "then" in c.lower()]
            missing = max(0, 2 - len(criteria))
            criteria += [c.format(title=s.title) for c in _GENERIC_CRITERIA][:missing]
            points = min((p for p in _ALLOWED_POINTS if p >= min(s.points, 8)), default=8)
            refined.append({"story_id": s.id, "acceptance_criteria": criteria[:4],
                            "points": points, "priority": s.priority})
        return {"summary": f"Refined {len(refined)} stories", "stories": refined}

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, RefinementOutput)
        before = story_problems(tools.db, tools.project_id)
        changed = 0
        for r in out.stories:
            # only the stories the check flagged: a good story or a planned one is left alone
            if r.story_id in before and tools.refine_story(
                    r.story_id, acceptance_criteria=r.acceptance_criteria, points=r.points,
                    priority=r.priority):
                changed += 1
        after = story_problems(tools.db, tools.project_id)
        n_before = sum(len(v) for v in before.values())
        n_after = sum(len(v) for v in after.values())
        tools.log("backlog_refined", f"{changed} stories refined: {n_before} problem(s) before, "
                  f"{n_after} after", refined=changed, before=n_before, after=n_after)
        validate_backlog(tools.db, tools.project_id, self.role)


class ProductOwnerAgent(BaseAgent):
    role = "product_owner"
    system_prompt = SYSTEM_PROMPT
    output_schema = BacklogOutput

    def __init__(self, llm: LLMClient | None = None):
        super().__init__(llm)
        self.refiner = BacklogRefiner(self.llm)

    def run(self, db: Session, project_id: int, task: dict | None = None) -> BaseModel:
        """Writes the backlog; in the sprint planning phase it refines it instead."""
        if (task or {}).get("phase") == "sprint_planning":
            return self.refiner.run(db, project_id, task)
        return super().run(db, project_id, task)

    def build_prompt(self, db: Session, project_id: int, task: dict) -> str:
        project = repo.get(db, m.Project, project_id)
        return f"Project name: {project.name}\nProduct idea: {project.idea}"

    def mock_output(self, db: Session, project_id: int, task: dict) -> dict:
        project = repo.get(db, m.Project, project_id)
        return {
            "summary": "Created a mock backlog with 1 epic and 2 stories",
            "vision": f"Deliver a simple, usable version of: {project.idea}",
            "epics": [
                {
                    "title": "Core features",
                    "description": "The minimum features needed for a first working version.",
                    "stories": [
                        {
                            "title": "Create an item",
                            "as_a": "user",
                            "i_want": "to create a new item",
                            "so_that": "I can start tracking my work",
                            "acceptance_criteria": [
                                "Given the app is open When I submit a title "
                                "Then a new item appears in the list",
                                "Given the app is open When I submit an empty title "
                                "Then I see a validation error",
                            ],
                            "priority": 1,
                            "points": 3,
                        },
                        {
                            "title": "Complete an item",
                            "as_a": "user",
                            "i_want": "to mark an item as done",
                            "so_that": "I can see what is left to do",
                            "acceptance_criteria": [
                                "Given an open item When I mark it done "
                                "Then it is shown as completed",
                                "Given an item that does not exist When I mark it done "
                                "Then I see a not-found error",
                            ],
                            "priority": 2,
                            "points": 2,
                        },
                    ],
                }
            ],
            "nfrs": [
                {"category": "product",
                 "requirement": "The API shall answer list and create requests in fixed time.",
                 "measure": "95% of requests answered in under 300 ms with 1,000 items"},
                {"category": "organizational",
                 "requirement": "Every story shall be covered by automated tests.",
                 "measure": "Each acceptance criterion has at least 1 passing pytest test"},
            ],
        }

    def apply(self, tools: Tools, out: BaseModel, task: dict) -> None:
        assert isinstance(out, BacklogOutput)
        tools.set_vision(out.vision)
        for epic in out.epics:
            e = tools.create_epic(epic.title, epic.description)
            for story in epic.stories:
                tools.create_story(e.id, **story.model_dump())
        if out.nfrs:
            tools.set_nfrs([n.model_dump() for n in out.nfrs])
        validate_backlog(tools.db, tools.project_id, self.role)
