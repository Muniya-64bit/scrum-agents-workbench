"""Writes `calls/*.json` of the todo-app scenario from readable sources.

    python demo/scenarios/todo-app/author.py

Scripted scenario: every answer below is hand-written, none comes from a model. The code is real
(FastAPI), the tests are real (pytest), and the two defects are real: the runner executes them and
they fail or pass for real. Edit this file, run it, commit the changed JSON. The story ids in the
answers match the ids of a fresh database (see README.md)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent))

from workbench.agents.devops import _CI_WORKFLOW, _DOCKERFILE  # noqa: E402
from workbench.process import TEST_FIRST_GUIDELINE  # noqa: E402

PROJECT = "Todo app"

# --- the generated application, built up story by story -----------------------------------------

REQUIREMENTS = "fastapi\nuvicorn\nhttpx\npytest\n"


def main_py(*, validate=False, listing=False, complete=False, delete=None, edit=False,
            filtering=False) -> str:
    """app/main.py for a given set of features. `delete` is None, "unknown-ok" (the defect),
    "wrong-guard" (a fix that does not work) or "ok"."""
    needs_http = validate or complete or delete in ("wrong-guard", "ok") or edit or filtering
    lines = ['"""Todo API: an in-memory list of to-do items."""', "", "import itertools", "",
             "from fastapi import FastAPI" + (", HTTPException" if needs_http else ""),
             "from pydantic import BaseModel", "",
             f'app = FastAPI(title="{PROJECT}")', "items: dict[int, dict] = {}",
             "_ids = itertools.count(1)", "", "", "class NewItem(BaseModel):",
             "    title: str", "", "", '@app.post("/items", status_code=201)',
             "def create_item(body: NewItem) -> dict:"]
    if validate:
        lines += ["    if not body.title.strip():",
                  '        raise HTTPException(422, "title must not be empty")']
    title = "body.title.strip()" if validate else "body.title"
    lines += [f'    item = {{"id": next(_ids), "title": {title}, "done": False}}',
              '    items[item["id"]] = item', "    return item"]
    if listing and filtering:
        lines += ["", "", '@app.get("/items")',
                  "def list_items(status: str | None = None) -> list[dict]:",
                  "    if status is None:", "        return list(items.values())",
                  '    if status not in ("open", "done"):',
                  '        raise HTTPException(422, "status must be open or done")',
                  '    return [i for i in items.values() if i["done"] == (status == "done")]']
    elif listing:
        lines += ["", "", '@app.get("/items")', "def list_items() -> list[dict]:",
                  "    return list(items.values())"]
    if complete:
        lines += ["", "", '@app.post("/items/{item_id}/complete")',
                  "def complete_item(item_id: int) -> dict:", "    item = items.get(item_id)",
                  "    if item is None:", '        raise HTTPException(404, "item not found")',
                  '    item["done"] = True', "    return item"]
    if delete:
        lines += ["", "", '@app.delete("/items/{item_id}")',
                  "def delete_item(item_id: int) -> dict:"]
        if delete == "unknown-ok":  # the defect: an unknown id is silently accepted
            lines += ["    items.pop(item_id, None)"]
        elif delete == "wrong-guard":  # a fix that only works while the list is empty
            lines += ["    if not items:", '        raise HTTPException(404, "item not found")',
                      "    items.pop(item_id, None)"]
        else:
            lines += ["    if item_id not in items:",
                      '        raise HTTPException(404, "item not found")',
                      "    del items[item_id]"]
        lines += ['    return {"deleted": item_id}']
    if edit:
        lines += ["", "", "class ItemUpdate(BaseModel):", "    title: str", "", "",
                  '@app.patch("/items/{item_id}")',
                  "def edit_item(item_id: int, body: ItemUpdate) -> dict:",
                  "    item = items.get(item_id)", "    if item is None:",
                  '        raise HTTPException(404, "item not found")',
                  "    if not body.title.strip():",
                  '        raise HTTPException(422, "title must not be empty")',
                  '    item["title"] = body.title.strip()', "    return item"]
    return "\n".join(lines) + "\n"


TEST_HEAD = '''"""Tests for story {n}: {title} (acceptance criteria as Given/When/Then comments)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, items

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    items.clear()
    yield
    items.clear()


def add(title):
    return client.post("/items", json={{"title": title}}).json()
'''


def test_file(n: int, title: str, body: str) -> str:
    return TEST_HEAD.format(n=n, title=title) + body


TESTS = {
    1: test_file(1, "Create item", '''

def test_submitting_a_title_creates_an_open_item():
    # Given an empty list When I submit the title 'Buy milk'
    # Then a new open item is returned with status 201
    response = client.post("/items", json={"title": "Buy milk"})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Buy milk" and body["done"] is False
    assert body["id"] in items


def test_an_empty_title_is_rejected():
    # Given an empty list When I submit an empty title
    # Then the API answers 422 and creates no item
    response = client.post("/items", json={"title": ""})
    assert response.status_code == 422
    assert items == {}
'''),
    2: test_file(2, "List items", '''

def test_items_are_listed_in_creation_order():
    # Given three items When I list the items Then all three are returned in creation order
    for title in ("First", "Second", "Third"):
        add(title)
    response = client.get("/items")
    assert response.status_code == 200
    assert [i["title"] for i in response.json()] == ["First", "Second", "Third"]


def test_an_empty_list_is_returned_when_there_are_no_items():
    # Given no items When I list the items Then an empty list is returned
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == []
'''),
    3: test_file(3, "Complete item", '''

def test_marking_an_open_item_done_returns_it_completed():
    # Given an open item When I mark it done Then it is returned as completed
    item = add("Pay rent")
    response = client.post(f"/items/{item['id']}/complete")
    assert response.status_code == 200
    assert response.json()["done"] is True
    assert items[item["id"]]["done"] is True


def test_completing_an_unknown_item_returns_404():
    # Given an unknown item id When I mark it done Then the API answers 404
    assert client.post("/items/9999/complete").status_code == 404
'''),
    4: test_file(4, "Delete item", '''

def test_a_deleted_item_is_gone_from_the_list():
    # Given an item When I delete it Then it no longer appears in the list
    item = add("Old news")
    assert client.delete(f"/items/{item['id']}").status_code == 200
    assert client.get("/items").json() == []


def test_deleting_an_unknown_item_returns_404():
    # Given an unknown item id When I delete it Then the API answers 404
    add("Keep me")
    assert client.delete("/items/9999").status_code == 404
    assert len(items) == 1
'''),
    5: test_file(5, "Edit title", '''

def test_editing_the_title_returns_and_lists_the_new_title():
    # Given an item When I change its title Then the new title is returned and listed
    item = add("Original")
    response = client.patch(f"/items/{item['id']}", json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert [i["title"] for i in client.get("/items").json()] == ["Renamed"]


def test_an_empty_new_title_is_rejected_and_the_title_stays():
    # Given an item When I change its title to an empty text
    # Then the API answers 422 and the title stays
    item = add("Original")
    assert client.patch(f"/items/{item['id']}", json={"title": "  "}).status_code == 422
    assert items[item["id"]]["title"] == "Original"


def test_editing_an_unknown_item_returns_404():
    # Given an unknown item id When I change its title Then the API answers 404
    assert client.patch("/items/9999", json={"title": "Nope"}).status_code == 404
'''),
    6: test_file(6, "Filter by status", '''

def _mixed():
    done = add("Finished")
    add("Still open")
    client.post(f"/items/{done['id']}/complete")


def test_filtering_by_open_lists_only_open_items():
    # Given open and completed items When I filter by open Then only open items are listed
    _mixed()
    response = client.get("/items", params={"status": "open"})
    assert [i["title"] for i in response.json()] == ["Still open"]


def test_filtering_by_done_lists_only_completed_items():
    # Given open and completed items When I filter by done Then only completed items are listed
    _mixed()
    response = client.get("/items", params={"status": "done"})
    assert [i["title"] for i in response.json()] == ["Finished"]


def test_an_unknown_status_is_rejected():
    # Given any items When I filter by an unknown status Then the API answers 422
    _mixed()
    assert client.get("/items", params={"status": "later"}).status_code == 422
'''),
}

# --- the answers ---------------------------------------------------------------------------------

CALLS: list[tuple[str, int, str, dict]] = []


def call(key: str, n: int, schema: str, output: dict) -> None:
    CALLS.append((key, n, schema, output))


def code(summary: str, entries: list[tuple[str, str]]) -> dict:
    return {"summary": summary, "files": [{"path": p, "content": c} for p, c in entries]}


def story(title, i_want, so_that, criteria, priority, points) -> dict:
    return {"title": title, "as_a": "user", "i_want": i_want, "so_that": so_that,
            "acceptance_criteria": criteria, "priority": priority, "points": points}


def author_backlog() -> None:
    call("product_owner.ProductOwnerAgent.backlog.s0", 1, "BacklogOutput", {
        "summary": "Created a backlog with 2 epics and 6 stories (16 points)",
        "vision": "A tiny to-do web API that lets people add, list, complete, edit, delete and "
                  "filter their to-do items.",
        "epics": [
            {"title": "Manage to-dos", "description": "Create, list, complete, delete and edit.",
             "stories": [
                 story("Create item", "to add a to-do item with a title",
                       "I can keep track of what I need to do",
                       ["Given an empty list When I submit the title 'Buy milk' Then a new open "
                        "item is returned with status 201",
                        "Given an empty list When I submit an empty title Then the API answers "
                        "422 and creates no item"], 1, 3),
                 story("List items", "to see all my items", "I know what is on my list",
                       ["Given three items When I list the items Then all three are returned "
                        "in creation order",
                        "Given no items When I list the items Then an empty list is returned"],
                       1, 2),
                 story("Complete item", "to mark an item as done", "I can see what is left",
                       ["Given an open item When I mark it done Then it is returned as completed",
                        "Given an unknown item id When I mark it done Then the API answers 404"],
                       1, 2),
                 story("Delete item", "to delete an item", "my list stays short",
                       ["Given an item When I delete it Then it no longer appears in the list",
                        "Given an unknown item id When I delete it Then the API answers 404"],
                       2, 3),
                 story("Edit title", "to change the title of an item", "I can fix typos",
                       ["Given an item When I change its title Then the new title is returned "
                        "and listed",
                        "Given an item When I change its title to an empty text Then the API "
                        "answers 422 and the title stays",
                        "Given an unknown item id When I change its title Then the API "
                        "answers 404"], 2, 3),
             ]},
            {"title": "Find to-dos", "description": "Focus on what is left.",
             "stories": [
                 story("Filter by status", "to list only open or only completed items",
                       "I can focus on the work that is left",
                       ["Given open and completed items When I filter by open Then only open "
                        "items are listed",
                        "Given open and completed items When I filter by done Then only "
                        "completed items are listed",
                        "Given any items When I filter by an unknown status Then the API "
                        "answers 422"], 3, 3),
             ]},
        ],
    })


def author_architecture() -> None:
    overview = """# Architecture: Todo app

## Tech stack
- Python 3.12 and FastAPI: a small JSON API with automatic OpenAPI docs.
- State kept in memory (a dict of items): enough for a demo, no database to set up.
- pytest with FastAPI's TestClient for the acceptance tests.

## Components
- `app/main.py`: the FastAPI app, the item store and all routes.
- `tests/`: one test file per story.

## Key decisions
- In-memory store: the goal is the process, not persistence; a database can replace it later.
- One module for the API: five small routes do not need a package structure.
- Errors are HTTP errors: 422 for invalid input, 404 for an unknown item id.
"""
    spec = """openapi: 3.0.3
info:
  title: Todo app API
  version: 0.1.0
paths:
  /items:
    get:
      summary: List items, optionally filtered by status
      parameters:
        - name: status
          in: query
          required: false
          schema: { type: string, enum: [open, done] }
      responses:
        '200': { description: The items in creation order }
        '422': { description: Unknown status }
    post:
      summary: Create an item
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/NewItem' }
      responses:
        '201': { description: The new item }
        '422': { description: Empty title }
  /items/{item_id}:
    patch:
      summary: Change the title of an item
      responses:
        '200': { description: The updated item }
        '404': { description: Unknown item }
        '422': { description: Empty title }
    delete:
      summary: Delete an item
      responses:
        '200': { description: The id of the deleted item }
        '404': { description: Unknown item }
  /items/{item_id}/complete:
    post:
      summary: Mark an item as done
      responses:
        '200': { description: The completed item }
        '404': { description: Unknown item }
components:
  schemas:
    NewItem:
      type: object
      required: [title]
      properties:
        title: { type: string, minLength: 1 }
"""
    call("architect.SystemDesigner.backlog.s0", 1, "ArchitectureOutput", {
        "summary": "Designed a small FastAPI service with an in-memory item store",
        "overview": overview,
        "diagrams": [
            {"name": "components", "mermaid":
                "flowchart LR\n  Client[HTTP client] -->|JSON| API[FastAPI app]\n"
                "  API --> Store[(items dict)]\n  Tests[pytest + TestClient] --> API"},
            {"name": "data-model", "mermaid":
                "erDiagram\n  ITEM {\n    int id\n    string title\n    bool done\n  }"},
            {"name": "main-flow", "mermaid":
                "sequenceDiagram\n  actor U as User\n  U->>API: POST /items {title}\n"
                "  API->>API: validate title\n  API->>Store: add item\n"
                "  API-->>U: 201 item"},
        ],
        "api_spec": spec,
    })


def design(story_id: int, title: str, notes: str, flow: str, path: str, spec: str) -> dict:
    return {"story_id": story_id, "notes": f"## {title}\n{notes}",
            "diagram": flow, "api_spec": f"paths:\n  {path}:\n{spec}"}


def author_designs() -> None:
    call("architect.DesignDelta.execution.s1", 1, "DesignDeltaOutput", {
        "summary": "Designed the 4 stories of sprint 1",
        "designs": [
            design(1, "Create item", "- Route `POST /items` creates `{id, title, done}`.\n"
                   "- An empty or blank title is rejected with 422 and nothing is stored.\n",
                   "sequenceDiagram\n  U->>API: POST /items\n  API-->>U: 201 or 422",
                   "/items",
                   "    post:\n      responses:\n        '201': { description: Created }\n"
                   "        '422': { description: Empty title }\n"),
            design(2, "List items", "- Route `GET /items` returns the items in creation order.\n"
                   "- An empty store returns `[]`, not an error.\n",
                   "sequenceDiagram\n  U->>API: GET /items\n  API-->>U: 200 [items]",
                   "/items", "    get:\n      responses:\n        '200': { description: Items }\n"),
            design(3, "Complete item", "- Route `POST /items/{id}/complete` sets `done` to true.\n"
                   "- An unknown id answers 404.\n",
                   "sequenceDiagram\n  U->>API: POST /items/1/complete\n  API-->>U: 200 or 404",
                   "/items/{item_id}/complete",
                   "    post:\n      responses:\n        '200': { description: Completed }\n"
                   "        '404': { description: Unknown item }\n"),
            design(4, "Delete item", "- Route `DELETE /items/{id}` removes the item.\n"
                   "- An unknown id must answer 404, not succeed silently.\n",
                   "sequenceDiagram\n  U->>API: DELETE /items/1\n  API-->>U: 200 or 404",
                   "/items/{item_id}",
                   "    delete:\n      responses:\n        '200': { description: Deleted }\n"
                   "        '404': { description: Unknown item }\n"),
        ]})
    call("architect.DesignDelta.execution.s2", 1, "DesignDeltaOutput", {
        "summary": "Designed the story added in sprint 2",
        "designs": [design(
            5, "Edit title", "- Route `PATCH /items/{id}` with `{title}` changes the title.\n"
            "- A blank title answers 422 and keeps the old title; an unknown id answers 404.\n",
            "sequenceDiagram\n  U->>API: PATCH /items/1 {title}\n  API-->>U: 200, 404 or 422",
            "/items/{item_id}",
            "    patch:\n      responses:\n        '200': { description: Updated }\n"
            "        '404': { description: Unknown item }\n"
            "        '422': { description: Empty title }\n")]})
    call("architect.DesignDelta.execution.s3", 1, "DesignDeltaOutput", {
        "summary": "Designed the story added in sprint 3",
        "designs": [design(
            6, "Filter by status", "- `GET /items` gets an optional `status` query parameter "
            "(`open` or `done`).\n- Any other value answers 422.\n",
            "sequenceDiagram\n  U->>API: GET /items?status=open\n  API-->>U: 200 [open items]",
            "/items",
            "    get:\n      parameters:\n        - { name: status, in: query, "
            "schema: { type: string } }\n      responses:\n        '200': { description: Items }\n"
            "        '422': { description: Unknown status }\n")]})


def tasks(*story_ids_titles: tuple[int, str]) -> list[dict]:
    out = []
    for sid, title in story_ids_titles:
        out += [{"story_id": sid, "title": f"Implement: {title}", "assignee": "developer"},
                {"story_id": sid, "title": f"Test: {title}", "assignee": "qa"}]
    return out


def author_planning() -> None:
    call("scrum_master.SprintPlanner.sprint_planning.s0", 1, "SprintPlanOutput", {
        "summary": "Planned the 4 most important stories (10 points)",
        "goal": "A user can create, list, complete and delete to-do items",
        "story_ids": [1, 2, 3, 4],
        "tasks": tasks((1, "Create item"), (2, "List items"), (3, "Complete item"),
                       (4, "Delete item"))})
    call("scrum_master.SprintPlanner.sprint_planning.s1", 1, "SprintPlanOutput", {
        "summary": "Planned the carried-over story and one new story (6 points)",
        "goal": "Finish deleting items and let users edit a title",
        "story_ids": [4, 5], "tasks": tasks((5, "Edit title"))})
    call("scrum_master.SprintPlanner.sprint_planning.s2", 1, "SprintPlanOutput", {
        "summary": "Planned the last story (3 points)",
        "goal": "Let users focus on open or completed items",
        "story_ids": [6], "tasks": tasks((6, "Filter by status"))})


def author_code() -> None:
    d = "developer.DeveloperAgent.execution."
    # sprint 1: everything is built first, QA finds the defects afterwards
    call(d + "s1.create-item", 1, "CodeOutput", code(
        "Added POST /items", [("requirements.txt", REQUIREMENTS), ("app/__init__.py", ""),
                              ("app/main.py", main_py())]))
    call(d + "s1.list-items", 1, "CodeOutput", code(
        "Added GET /items", [("app/main.py", main_py(listing=True))]))
    call(d + "s1.complete-item", 1, "CodeOutput", code(
        "Added POST /items/{id}/complete", [("app/main.py", main_py(listing=True, complete=True))]))
    call(d + "s1.delete-item", 1, "CodeOutput", code(
        "Added DELETE /items/{id}",
        [("app/main.py", main_py(listing=True, complete=True, delete="unknown-ok"))]))
    # QA's bug fixes inside sprint 1
    call(d + "s1.create-item", 2, "CodeOutput", code(
        "Reject an empty title with 422",
        [("app/main.py", main_py(validate=True, listing=True, complete=True,
                                 delete="unknown-ok"))]))
    call(d + "s1.delete-item", 2, "CodeOutput", code(
        "Answer 404 when there is nothing to delete",
        [("app/main.py", main_py(validate=True, listing=True, complete=True,
                                 delete="wrong-guard"))]))
    # sprint 2: the carried-over bug gets its second attempt, then the new story
    call(d + "s2.delete-item", 1, "CodeOutput", code(
        "Answer 404 for every unknown id",
        [("app/main.py", main_py(validate=True, listing=True, complete=True, delete="ok"))]))
    call(d + "s2.edit-title", 1, "CodeOutput", code(
        "Added PATCH /items/{id}",
        [("app/main.py", main_py(validate=True, listing=True, complete=True, delete="ok",
                                 edit=True))]))
    call(d + "s3.filter-by-status", 1, "CodeOutput", code(
        "Added the status filter to GET /items",
        [("app/main.py", main_py(validate=True, listing=True, complete=True, delete="ok",
                                 edit=True, filtering=True))]))


def author_tests() -> None:
    q = "qa.QAAgent.execution."
    names = {1: "s1.create-item", 2: "s1.list-items", 3: "s1.complete-item", 4: "s1.delete-item",
             5: "s2.edit-title", 6: "s3.filter-by-status"}
    for n, key in names.items():
        call(q + key, 1, "CodeOutput", code(
            f"Wrote the acceptance tests for story {n}", [(f"tests/test_story_{n}.py", TESTS[n])]))


STORY_TITLES = {1: "Create item", 2: "List items", 3: "Complete item", 4: "Delete item",
                5: "Edit title", 6: "Filter by status"}


def author_review_and_retro() -> None:
    s = "scrum_master."
    call(s + "StandupAgent.review.s1", 1, "StandupOutput", {
        "summary": "7 of 10 points are done; Delete item is blocked",
        "yesterday": ["Implemented and tested Create item, List items and Complete item",
                      "Fixed the missing empty-title check found by QA"],
        "today": ["Delete item still fails its tests"],
        "blockers": ["Delete item answers 200 for an unknown id; the single fix attempt did not "
                     "work"]})
    call(s + "RetroAgent.retro.s1", 1, "RetroOutput", {
        "summary": "Sprint 1 delivered 7 of 10 points; the process changes for sprint 2",
        "went_well": ["QA caught the missing empty-title check before the review",
                      "Create, list and complete work and are covered by tests"],
        "went_wrong": ["Delete item was left open after the one allowed fix attempt",
                       "Defects were found only after the code was written",
                       "We committed 10 points and finished 7"],
        "actions": ["QA writes the acceptance tests before the Developer codes",
                    "Commit to the velocity we measured (7 points)",
                    "Allow two fix attempts per bug"],
        "process_changes": {
            "capacity": 7, "max_fix_retries": 2, "test_first": True,
            "add_guidelines": [TEST_FIRST_GUIDELINE],
            "reason": "Commit to last sprint's velocity (7 of 10 points); defects escaped into "
                      "testing, so write the tests first; a bug stayed open after one attempt, "
                      "so allow two"}})
    call(s + "StandupAgent.review.s2", 1, "StandupOutput", {
        "summary": "All 6 points are done",
        "yesterday": ["Fixed Delete item (404 for every unknown id)",
                      "Wrote the Edit title tests first, then the code"],
        "today": ["Nothing left in the sprint"], "blockers": []})
    call(s + "RetroAgent.retro.s2", 1, "RetroOutput", {
        "summary": "Sprint 2 delivered everything it committed",
        "went_well": ["Tests written first: every story passed on its first run",
                      "Committing 6 of 7 points was met in full",
                      "The carried-over bug was fixed with the extra attempt"],
        "went_wrong": ["Nothing measurable"],
        "actions": ["Keep test-first and the two-attempt limit"],
        "process_changes": {"reason": "The process worked; keep it"}})
    call(s + "StandupAgent.review.s3", 1, "StandupOutput", {
        "summary": "All 3 points are done",
        "yesterday": ["Wrote the Filter by status tests first, then the code"],
        "today": ["Nothing left in the sprint"], "blockers": []})
    call(s + "RetroAgent.retro.s3", 1, "RetroOutput", {
        "summary": "Sprint 3 finished the backlog",
        "went_well": ["Test-first kept the defect count at zero", "The backlog is empty"],
        "went_wrong": ["Nothing measurable"],
        "actions": ["Keep the process for the next project"],
        "process_changes": {"reason": "The process worked; keep it"}})


def release_notes(version: str, done: list[int], issues: list[str]) -> str:
    lines = [f"# Release notes: {PROJECT} {version}", "", "## Completed stories"]
    lines += [f"- #{i} {STORY_TITLES[i]}" for i in done]
    lines += ["", "## Known issues"] + (issues or ["- None"])
    return "\n".join(lines) + "\n"


def author_release() -> None:
    k = "devops.DevOpsAgent.release."
    plans = [
        ("s1", "v0.1.0", [1, 2, 3], ["- Delete item (#4) answers 404 only while the list is "
                                      "empty; carried over to sprint 2"]),
        ("s2", "v0.2.0", [1, 2, 3, 4, 5], []),
        ("s3", "v0.3.0", [1, 2, 3, 4, 5, 6], []),
    ]
    for sprint, version, done, issues in plans:
        call(k + sprint, 1, "CodeOutput", code(
            f"Prepared Docker, CI and release notes for {version}",
            [("Dockerfile", _DOCKERFILE), (".github/workflows/ci.yml", _CI_WORKFLOW),
             ("RELEASE_NOTES.md", release_notes(version, done, issues))]))


def build(out_dir: Path) -> int:
    CALLS.clear()
    author_backlog()
    author_architecture()
    author_designs()
    author_planning()
    author_code()
    author_tests()
    author_review_and_retro()
    author_release()
    calls = out_dir / "calls"
    calls.mkdir(parents=True, exist_ok=True)
    for old in calls.glob("*.json"):
        old.unlink()
    for key, n, schema, output in CALLS:
        data = {"key": key, "n": n, "schema": schema, "output": output,
                "usage": {"input_tokens": 0, "output_tokens": 0}, "source": "scripted"}
        (calls / f"{key}.{n}.json").write_text(
            json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
    return len(CALLS)


if __name__ == "__main__":
    print(f"wrote {build(HERE)} calls to {HERE / 'calls'}")
