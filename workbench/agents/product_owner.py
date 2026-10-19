"""Product Owner agent: product idea -> vision, epics, user stories with acceptance criteria."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from workbench.agents.base import BaseAgent
from workbench.agents.tools import Tools
from workbench.db import models as m
from workbench.db import repo
from workbench.requirements import validate_backlog
from workbench.schemas import BacklogOutput

SYSTEM_PROMPT = """You are an experienced Scrum Product Owner.
Turn the product idea into a small, realistic product backlog.

Rules:
- Write a one or two sentence product vision.
- Group work into 2 to 4 epics, each with 2 to 4 user stories (6 to 10 stories in total).
- Each story has as_a, i_want and so_that fields, which together read as
  "As a <role>, I want <goal>, so that <benefit>".
- Each story has 2 to 4 acceptance criteria. Every criterion is ONE string in the form
  "Given <context> When <action> Then <observable result>" and is testable.
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


class ProductOwnerAgent(BaseAgent):
    role = "product_owner"
    system_prompt = SYSTEM_PROMPT
    output_schema = BacklogOutput

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
