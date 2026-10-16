# Scrum Agents Workbench

[![CI](https://github.com/Muniya-64bit/scrum-agents-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/Muniya-64bit/scrum-agents-workbench/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Status](https://img.shields.io/badge/status-in%20development-orange)

A multi-agent **CASE workbench for Scrum**. You give it a product idea; a team of LLM agents,
each playing a Scrum role, takes it through the software development life cycle in sprints and
produces real artifacts: backlog, design, code, tests and a release. A human approves the key
ceremonies.

> **Status:** Day 1 foundation is in place (data model, LLM wrapper, agent base class,
> orchestrator, REST API). All six agents currently run as stubs; real agents are tracked in the
> [issues](https://github.com/Muniya-64bit/scrum-agents-workbench/issues).

## Contents
- [Features](#features)
- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [API](#api)
- [Project structure](#project-structure)
- [Developing an agent](#developing-an-agent)
- [Testing and linting](#testing-and-linting)
- [Roadmap](#roadmap)
- [Team and workflow](#team-and-workflow)
- [Documentation](#documentation)

## Features
- Six role-based agents: Product Owner, Scrum Master, Architect, Developer, QA and  DevOps
- Scrum state machine with human approval gates at sprint planning and sprint review
- Traceability from user story to design, code and tests
- Schema-validated agent output with retries, response caching and token usage logging
- Mock mode (`MOCK_LLM=1`) so development and tests cost no tokens
- Append-only event log that feeds the activity feed

## How it works

### System architecture
```mermaid
flowchart LR
  UI[Web UI<br/>board, backlog, feed] -->|REST / events| API[FastAPI]
  API --> ORCH[Orchestrator<br/>Scrum state machine]
  ORCH --> AG[Agents<br/>PO, SM, Architect,<br/>Developer, QA, DevOps]
  AG -->|Tools API| DB[(SQLite)]
  AG --> LLM[LLMClient]
  LLM --> CLAUDE[Claude API]
  AG --> WS[Sandbox workspace + git]
  API --> DB
```

### Agents and the SDLC
| Agent | Scrum role | SDLC phase | Outputs |
|---|---|---|---|
| Product Owner | PO | Requirements | Vision, epics, user stories, acceptance criteria |
| Scrum Master | SM | Planning, process | Sprint plan, stand-ups, burndown, retrospective |
| Architect | Dev team | Design | Architecture, API spec, Mermaid/UML diagrams |
| Developer | Dev team | Implementation | Code committed per story |
| QA | Dev team | Testing | Tests from acceptance criteria, bug reports |
| DevOps | Dev team | Deploy | Dockerfile, CI workflow, release notes |

### Scrum state machine
Phases marked with a gate pause until a human approves.
```mermaid
stateDiagram-v2
  [*] --> idea
  idea --> backlog
  backlog --> sprint_planning
  sprint_planning --> execution: human approves
  execution --> review
  review --> retro: human approves
  retro --> release
  release --> done
  done --> [*]
```

### One sprint, step by step
```mermaid
sequenceDiagram
  actor H as Human
  participant O as Orchestrator
  participant SM as Scrum Master
  participant D as Developer
  participant Q as QA
  O->>SM: plan sprint from backlog
  SM-->>O: sprint backlog and tasks
  O->>H: request approval
  H-->>O: approve
  loop each story
    O->>D: implement story
    D-->>O: code committed
    O->>Q: test story
    alt tests fail
      Q-->>D: bug report (max 3 retries)
    else tests pass
      Q-->>O: story done
    end
  end
  O->>SM: sprint review and retro
  SM-->>H: increment summary
```

### Data model
```mermaid
erDiagram
  PROJECT ||--o{ EPIC : has
  PROJECT ||--o{ SPRINT : has
  PROJECT ||--o{ ARTIFACT : has
  PROJECT ||--o{ EVENT : logs
  EPIC ||--o{ USER_STORY : contains
  SPRINT ||--o{ USER_STORY : includes
  USER_STORY ||--o{ TASK : splits_into
  USER_STORY ||--o{ BUG : has
  USER_STORY ||--o{ TRACE_LINK : traced_by
  ARTIFACT ||--o{ TRACE_LINK : linked_in
```

## Quickstart
Requires Python 3.12 and `make`.

```bash
git clone https://github.com/Muniya-64bit/scrum-agents-workbench.git
cd scrum-agents-workbench
make setup    # virtualenv, dependencies, .env (mock mode, no API key needed)
make test     # all tests should pass
make run      # API at http://localhost:8000, interactive docs at /docs
```

Try the flow with curl:
```bash
curl -X POST localhost:8000/projects -H 'content-type: application/json' \
  -d '{"name":"Todo","idea":"A simple to-do app"}'
curl -X POST localhost:8000/projects/1/advance      # repeat to move through phases
curl -X POST localhost:8000/projects/1/approve      # at a gate
curl localhost:8000/projects/1/events
```

To use the real model, set `ANTHROPIC_API_KEY` and `MOCK_LLM=0` in `.env`.

## Configuration
Set in `.env` (copy from `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Claude API key, needed when `MOCK_LLM=0` |
| `WORKBENCH_MODEL` | `claude-sonnet-5-5` | Model used by all agents |
| `MOCK_LLM` | `1` | `1` returns canned output with no API calls |
| `DATABASE_URL` | `sqlite:///./workbench.db` | Database connection string |
| `WORKSPACES_DIR` | `./workspaces` | Where generated project code is written |

## API
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/projects` | Create a project from `{name, idea}` |
| GET | `/projects/{id}` | Current phase and approval state |
| POST | `/projects/{id}/advance` | Run the next phase (409 while awaiting approval) |
| POST | `/projects/{id}/approve` | Clear a human gate |
| GET | `/projects/{id}/events?after=<id>` | Activity feed |

Full reference with examples: [docs/api.md](docs/api.md). Backlog, sprint, task, artifact and
traceability endpoints are planned (issue #13).

## Project structure
```
workbench/
  api/            FastAPI app
  agents/         BaseAgent, Tools API, registry (one module per real agent)
  db/             SQLAlchemy models, session, repository helpers
  llm/            LLMClient: validation, retries, cache, mock mode
  orchestrator/   Scrum state machine
  schemas.py      Shared agent output contracts
tests/            pytest suite
docs/             Architecture and Scrum process evidence
frontend/         Web UI (planned)
```

## Developing an agent
Subclass `BaseAgent`, register it in `workbench/agents/registry.py`, and test it in mock mode.
The full guide with a worked example is in [docs/agents.md](docs/agents.md).

## Testing and linting
```bash
make test    # pytest
make lint    # ruff
```
CI runs both on every pull request.

## Roadmap
Three one-day sprints. See the issue labels `day-1`, `day-2` and `day-3`.

```mermaid
gantt
  dateFormat X
  axisFormat Day %s
  section Day 1: foundation
  Tooling, schema, LLM wrapper, orchestrator :0, 1
  section Day 2: build
  Agents, API, UI                            :1, 2
  section Day 3: finish
  Integration, metrics, tests, report        :2, 3
```

## Team and workflow
Work is split into six workstreams, labelled `ws1` to `ws6` on each issue: orchestrator,
PO and SM agents, Architect and Developer agents, QA and DevOps agents, backend and data,
and frontend. Branch from `main` as `feat/<issue>-name`, open a pull request that references
the issue, and get one review. See [CONTRIBUTING.md](CONTRIBUTING.md). Our own stand-ups and
retrospectives are in [docs/scrum](docs/scrum).

## Documentation
| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Components, state machine, data model, design decisions |
| [docs/development.md](docs/development.md) | Setup, workflow, conventions, troubleshooting |
| [docs/agents.md](docs/agents.md) | How to build an agent |
| [docs/api.md](docs/api.md) | REST API reference |
| [docs/scrum](docs/scrum/README.md) | Our stand-ups and retrospectives |

## License
No license has been chosen yet. Until one is added, all rights are reserved by the authors.
