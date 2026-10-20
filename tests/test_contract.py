"""The API contract: render, parse, and check the code against it."""

from sqlalchemy.orm import Session

from workbench import contract
from workbench.agents.tools import Tools
from workbench.contract import Endpoint
from workbench.db import repo
from workbench.schemas import EndpointOut
from workbench.workspace import Workspace

CREATE = EndpointOut(method="POST", path="/books", purpose="Add a book",
                     request_fields=["title: str", "copies: int"], success_status=201,
                     error_statuses=[422])
GET = EndpointOut(method="GET", path="/books/{book_id}", purpose="Get a book",
                  error_statuses=[404])
DELETE = EndpointOut(method="DELETE", path="/books/{book_id}", purpose="Remove a book",
                     success_status=204, error_statuses=[404])


def test_render_then_parse_gives_the_same_endpoints():
    text = contract.render([CREATE, GET, DELETE])
    assert contract.parse(text) == [Endpoint("POST", "/books", 201),
                                    Endpoint("GET", "/books/{book_id}", 200),
                                    Endpoint("DELETE", "/books/{book_id}", 204)]
    assert "copies: {type: integer}" in text and "'422':" in text
    assert 'example: {"title": "text", "copies": 1}' in text


def test_two_methods_on_one_path_share_a_path_entry():
    text = contract.render([GET, DELETE])
    assert text.count("  /books/{book_id}:") == 1


def _code(tmp_path, source: str) -> Workspace:
    ws = Workspace(1, tmp_path).init()
    ws.write("app/main.py", source)
    return ws


def test_implemented_reads_fastapi_routes_and_status_codes(tmp_path):
    ws = _code(tmp_path, (
        "from fastapi import FastAPI, status\n"
        "app = FastAPI()\n"
        "@app.post('/books', status_code=201)\n"
        "def add(): ...\n"
        "@app.get(\"/books/{book_id}\")\n"
        "def get(): ...\n"
        "@router.delete('/books/{id}/', status_code=status.HTTP_204_NO_CONTENT)\n"
        "def rm(): ...\n"))
    assert contract.implemented(ws) == [Endpoint("POST", "/books", 201),
                                        Endpoint("GET", "/books/{}", 200),
                                        Endpoint("DELETE", "/books/{}", 204)]


def test_a_complete_implementation_has_no_violations():
    wanted = [Endpoint("POST", "/books", 201), Endpoint("GET", "/books/{book_id}", 200)]
    code = [Endpoint("POST", "/books", 201), Endpoint("GET", "/books/{}", 200)]
    assert contract.violations(wanted, code) == []


def test_missing_endpoint_and_wrong_status_are_reported():
    wanted = [Endpoint("POST", "/books", 201), Endpoint("GET", "/books/{book_id}", 200),
              Endpoint("DELETE", "/books/{book_id}", 204)]
    code = [Endpoint("POST", "/books", 200), Endpoint("GET", "/books/{}", 200)]
    problems = {str(e): why for e, why in contract.violations(wanted, code)}
    assert problems["POST /books"].startswith("must return status 201")
    assert problems["DELETE /books/{book_id}"] == "endpoint is missing"
    assert "GET /books/{book_id}" not in problems


def test_a_router_prefix_is_tolerated():
    wanted = [Endpoint("GET", "/books/{book_id}", 200)]
    assert contract.violations(wanted, [Endpoint("GET", "/{}", 200)]) == []
    assert contract.violations(wanted, [Endpoint("POST", "/{}", 200)])  # wrong method


def test_for_story_returns_the_newest_contract(db: Session):
    p = repo.create_project(db, "Library", "A library")
    t = Tools(db, p.id, "architect")
    story = t.create_story(t.create_epic("Core").id, title="Add a book")
    assert contract.for_story(db, p.id, story.id) == ("", [])
    t.write_artifact("api_spec", "openapi.yaml", "paths: {}")  # sprint-0 spec: not a contract
    t.write_artifact("api_spec", "API: Add a book", contract.render([GET]), story_id=story.id)
    t.write_artifact("api_spec", "API: Add a book", contract.render([CREATE]), story_id=story.id)
    text, endpoints = contract.for_story(db, p.id, story.id)
    assert endpoints == [Endpoint("POST", "/books", 201)] and "title" in text


def test_routes_in_reads_one_source_text():
    source = ("@app.post('/a/{x}', status_code=201)\ndef f(): ...\n"
              "@router.get(\"/b/\")\ndef g(): ...\n")
    assert contract.routes_in(source) == [Endpoint("POST", "/a/{}", 201),
                                          Endpoint("GET", "/b", 200)]
    assert contract.routes_in("x = 1") == []


def test_lost_lists_routes_that_disappeared():
    before = [Endpoint("POST", "/books", 201), Endpoint("GET", "/books/{}", 200),
              Endpoint("POST", "/books", 201)]
    assert contract.lost(before, before) == []
    after = [Endpoint("GET", "/books/{}", 200)]
    assert contract.lost(before, after) == [Endpoint("POST", "/books", 201)]  # once, not twice


def test_lost_tolerates_a_router_prefix_in_either_direction():
    get_item, get_book = Endpoint("GET", "/{}", 200), Endpoint("GET", "/books/{}", 200)
    assert contract.lost([get_book], [get_item]) == []
    assert contract.lost([get_item], [get_book]) == []
    assert contract.lost([Endpoint("GET", "/books", 200)], [Endpoint("POST", "/books", 200)])


def test_a_root_route_stands_for_a_router_collection_route():
    after = [Endpoint("POST", "/", 201)]  # `@router.post("/")` under prefix="/books"
    assert contract.lost([Endpoint("POST", "/books", 201)], after) == []


def test_example_body_has_one_value_per_field_by_type():
    assert contract.example_body(["title: str", "copies: int", "price: float", "paid: bool",
                                  "tags: list"]) == {
        "title": "text", "copies": 1, "price": 1.5, "paid": True, "tags": "text"}
    assert contract.example_body([]) == {}


def test_an_endpoint_without_a_body_has_no_example():
    assert "example:" not in contract.render([GET])


def test_the_example_does_not_disturb_parsing():
    assert contract.parse(contract.render([CREATE]))[0] == Endpoint("POST", "/books", 201)
