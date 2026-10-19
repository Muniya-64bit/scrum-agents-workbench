"""The API contract: the Architect's endpoints for a story, and a rule-based check that the
Developer's code implements them.

The Architect returns structured endpoints (`EndpointOut`). `render` turns them into an OpenAPI
`paths` document, so the spec artifact is never empty or free-form. The Developer builds exactly
these endpoints and QA tests exactly these, so the three agents agree on paths, field names and
status codes. `violations` then checks the code by rules (no LLM): a missing endpoint or a wrong
success status becomes a bug for the Developer."""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from workbench.db import repo
from workbench.workspace import Workspace

_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
_ROUTE = re.compile(
    r"@\s*[\w.]+\.(get|post|put|patch|delete)\(\s*(?:path\s*=\s*)?[\"']([^\"']*)[\"']([^)]*)\)",
    re.IGNORECASE)
_STATUS = re.compile(r"status_code\s*=\s*(?:[\w.]*HTTP_)?(\d{3})")


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    success_status: int = 200

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


def render(endpoints: list) -> str:
    """OpenAPI `paths` YAML for these endpoints (objects with the `EndpointOut` fields)."""
    by_path: dict[str, list] = {}
    for e in endpoints:
        by_path.setdefault(e.path, []).append(e)
    lines = ["paths:"]
    for path, items in by_path.items():
        lines.append(f"  {path}:")
        for e in items:
            lines += [f"    {e.method.lower()}:", f"      summary: {e.purpose}"]
            if e.request_fields:
                lines += ["      requestBody:", "        required: true", "        content:",
                          "          application/json:", "            schema:",
                          "              type: object", "              properties:"]
                for field in e.request_fields:
                    name, _, kind = field.partition(":")
                    lines.append(f"                {name.strip()}: "
                                 f"{{type: {_TYPES.get(kind.strip(), 'string')}}}")
            lines.append("      responses:")
            lines += [f"        '{e.success_status}':", "          description: Success"]
            for code in e.error_statuses:
                lines += [f"        '{code}':", "          description: Error"]
    return "\n".join(lines) + "\n"


def parse(text: str) -> list[Endpoint]:
    """The endpoints of a document made by `render` (method, path, first 2xx status)."""
    found: list[Endpoint] = []
    path = method = None
    status: int | None = None

    def close():
        if path and method:
            found.append(Endpoint(method, path, status or 200))

    for line in text.splitlines():
        if m := re.match(r"^  (/\S*):\s*$", line):
            close()
            path, method, status = m.group(1), None, None
        elif m := re.match(r"^    (get|post|put|patch|delete):\s*$", line):
            close()
            method, status = m.group(1).upper(), None
        elif (m := re.match(r"^        '(\d{3})':\s*$", line)) and status is None \
                and m.group(1).startswith("2"):
            status = int(m.group(1))
    close()
    return found


def for_story(db: Session, project_id: int, story_id: int) -> tuple[str, list[Endpoint]]:
    """The newest contract written for a story: its text and parsed endpoints, or ("", [])."""
    specs = [a for link, a in repo.trace_links(db, project_id)
             if link.story_id == story_id and link.relation == "api_spec"
             and a.name.startswith("API:")]
    return (specs[-1].content, parse(specs[-1].content)) if specs else ("", [])


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/") or "/")


def implemented(ws: Workspace) -> list[Endpoint]:
    """The routes declared in the workspace's `app/` Python files (FastAPI decorators)."""
    found: list[Endpoint] = []
    for rel in ws.text_files():
        if rel.startswith("app/") and rel.endswith(".py"):
            for m in _ROUTE.finditer(ws.read(rel)):
                status = _STATUS.search(m.group(3))
                found.append(Endpoint(m.group(1).upper(), _norm(m.group(2)),
                                      int(status.group(1)) if status else 200))
    return found


def _same_path(contract: str, route: str) -> bool:
    """Equal, or one is the other with a router prefix (`/books` + `/{}` is `/books/{}`)."""
    return contract == route or (route != "/" and contract.endswith(route))


def violations(contract: list[Endpoint], code: list[Endpoint]) -> list[tuple[Endpoint, str]]:
    """(endpoint, what is wrong) for each contract endpoint the code does not satisfy."""
    problems: list[tuple[Endpoint, str]] = []
    for want in contract:
        path = _norm(want.path)
        routes = [c for c in code if c.method == want.method and _same_path(path, c.path)]
        if not routes:
            problems.append((want, "endpoint is missing"))
        elif all(c.success_status != want.success_status for c in routes):
            problems.append((want, f"must return status {want.success_status} on success "
                                   f"(add status_code={want.success_status} to the route)"))
    return problems
