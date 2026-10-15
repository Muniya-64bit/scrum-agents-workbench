# REST API reference

Base URL: `http://localhost:8000`. Interactive docs are served at `/docs` (Swagger UI).
All bodies are JSON. There is no authentication; run locally only.

## Endpoints
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/projects` | Create a project |
| GET | `/projects/{id}` | Get phase and approval state |
| POST | `/projects/{id}/advance` | Move to the next phase and run its agents |
| POST | `/projects/{id}/approve` | Approve (or reject) the pending gate |
| GET | `/projects/{id}/events` | List activity events |

Backlog, sprint, task, artifact and traceability endpoints, plus an event stream, are planned
under issue #13.

## Create a project
```bash
curl -X POST localhost:8000/projects -H 'content-type: application/json' \
  -d '{"name":"Todo","idea":"A simple to-do app"}'
```
```json
{"id": 1, "name": "Todo", "idea": "A simple to-do app", "phase": "idea", "awaiting_approval": false}
```

## Advance
`POST /projects/1/advance` runs the next phase and returns the project. When the new phase is a
gate, `awaiting_approval` is `true`.

| Status | Meaning |
|---|---|
| 200 | Phase ran |
| 404 | Unknown project |
| 409 | Awaiting approval; call approve first |

## Approve
`POST /projects/1/approve?approved=true`

| Status | Meaning |
|---|---|
| 200 | Gate cleared |
| 404 | Unknown project |
| 409 | Nothing to approve |

## Events
`GET /projects/1/events?after=12` returns events with `id` greater than `after`, oldest first.
Poll with the last `id` you saw.

```json
[{"id": 13, "agent": "orchestrator", "kind": "phase_started", "message": "backlog",
  "payload": {}, "at": "2026-10-14T09:30:00"}]
```

Event kinds: `phase_started`, `approval_requested`, `approved`, `rejected`, `agent_started`,
`agent_finished`, `epic_created`, `story_created`, `task_created`, `task_updated`,
`artifact_created`, `bug_reported`.
