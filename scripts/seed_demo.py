"""Create a demo project with a backlog, a sprint and tasks in every board column.

    python scripts/seed_demo.py

Useful for working on the UI before the real agents are merged, and for demos. Writes to the
database in DATABASE_URL (default ./workbench.db) through the Tools API, so the events are logged
like a real run."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workbench.agents.tools import Tools  # noqa: E402
from workbench.db import models as m  # noqa: E402
from workbench.db import repo  # noqa: E402
from workbench.db.session import SessionLocal, init_db  # noqa: E402

EPICS = [
    ("Task management", "Create, complete and organise to-do items.", [
        ("Create an item", "user", "to add a to-do with a title",
         "I can keep track of what I need to do", 1, 3,
         ["Given the app is open When I submit a title Then the item appears in the list",
          "Given the app is open When I submit an empty title Then I see a validation error"]),
        ("Complete an item", "user", "to mark an item as done",
         "I can see what is left", 1, 2,
         ["Given an open item When I mark it done Then it is shown as completed"]),
        ("Delete an item", "user", "to remove an item I no longer need",
         "my list stays short", 2, 2,
         ["Given an item When I delete it Then it no longer appears in the list"]),
    ]),
    ("Organisation", "Help users focus on what matters.", [
        ("Filter by status", "user", "to show only open or only completed items",
         "I can focus on the work left", 3, 3,
         ["Given open and completed items When I choose Open Then only open items are shown"]),
        ("Set a due date", "user", "to give an item a due date",
         "I do not miss deadlines", 4, 5,
         ["Given an item When I set a due date Then the date is shown next to it",
          "Given an overdue item When I open the list Then it is highlighted"]),
    ]),
]

# (story index, task title, assignee, status) for the stories planned into sprint 1
TASKS = [
    (0, "Implement POST /items with validation", "developer", "done"),
    (0, "Test: create item and empty title", "qa", "testing"),
    (1, "Implement PATCH /items/{id}", "developer", "doing"),
    (1, "Test: complete an item", "qa", "todo"),
    (2, "Implement DELETE /items/{id}", "developer", "todo"),
    (2, "Test: delete an item", "qa", "todo"),
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        p = repo.create_project(db, "Todo app", "A simple to-do app where users add, complete "
                                                "and delete tasks.")
        repo.update(db, p, vision="Help people get small things done with a fast, simple to-do "
                                  "list.")
        po = Tools(db, p.id, "product_owner")
        stories = []
        for title, description, items in EPICS:
            e = po.create_epic(title, description)
            for s_title, as_a, i_want, so_that, priority, points, criteria in items:
                stories.append(po.create_story(
                    e.id, title=s_title, as_a=as_a, i_want=i_want, so_that=so_that,
                    priority=priority, points=points, acceptance_criteria=criteria))

        sm = Tools(db, p.id, "scrum_master")
        sprint = repo.add(db, m.Sprint(project_id=p.id, number=1, capacity=10, status="active",
                                       goal="Users can add, complete and delete items"))
        for s in stories[:3]:
            repo.update(db, s, sprint_id=sprint.id, status="sprint")
        for idx, title, assignee, status in TASKS:
            t = sm.create_task(stories[idx].id, title, assignee)
            if status != "todo":
                Tools(db, p.id, assignee).update_task(t.id, status)

        repo.update(db, p, phase="execution")
        print(f"Created demo project {p.id}: open http://localhost:5173/projects/{p.id}/board")


if __name__ == "__main__":
    main()
