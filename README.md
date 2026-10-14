# Scrum Agents Workbench

A multi-agent CASE workbench for Scrum: LLM agents (Product Owner, Scrum Master, Architect,
Developer, QA, DevOps) take a product idea through the SDLC in sprints, with human approval at
the ceremonies. Design details: [docs/architecture.md](docs/architecture.md).

## Quickstart (Python 3.12)
```
make setup    # venv, dependencies, .env (MOCK_LLM=1 by default, no API key needed)
make test     # should print: 6 passed
make run      # http://localhost:8000/docs
```
Try it: `POST /projects` → `POST /projects/{id}/advance` (repeat; approve gates with
`POST /projects/{id}/approve`) → `GET /projects/{id}/events`.

To use the real model, set `ANTHROPIC_API_KEY` and `MOCK_LLM=0` in `.env`.

## Team workflow
Issues are labelled by day and workstream (`ws1`…`ws6`). See [CONTRIBUTING.md](CONTRIBUTING.md)
and our process evidence in [docs/scrum](docs/scrum).
