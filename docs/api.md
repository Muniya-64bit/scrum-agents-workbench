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
| GET | `/projects/{id}/stream` | Live activity events (Server-Sent Events) |
| GET | `/projects` | List all projects |
| GET | `/projects/{id}/backlog` | Vision, epics and their stories (priority order) |
| GET | `/projects/{id}/sprints` | Sprints with story ids and total points |
| GET | `/sprints/{id}` | One sprint with its stories and tasks |
| GET | `/projects/{id}/tasks?sprint_id=&status=` | Tasks, optionally filtered |
| PATCH | `/tasks/{id}` | Move a task to `todo`, `doing`, `testing` or `done` |
| GET | `/projects/{id}/artifacts?kind=` | Artifact list (without content) |
| GET | `/artifacts/{id}` | One artifact with content and linked story ids |
| GET | `/projects/{id}/bugs?status=` | Bugs filed against the project's stories |
| GET | `/projects/{id}/traceability` | Story -> design -> code -> test table |

Every response has a schema in the OpenAPI docs at `/docs`. Unknown ids return 404.

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

## Event stream
`GET /projects/1/stream` keeps the connection open and sends each new event as it happens.
Every frame carries the event `id` and one event (same shape as above) as JSON in `data`:

```
id: 13
data: {"id": 13, "agent": "orchestrator", "kind": "phase_started", "message": "backlog", ...}
```

Use `?after=<id>` to skip older events. On reconnect, `EventSource` sends `Last-Event-ID`
automatically and the stream resumes after that event. A `: keep-alive` comment is sent after
15 seconds without events.

```js
const es = new EventSource("/projects/1/stream");
es.onmessage = (msg) => console.log(JSON.parse(msg.data));
```

Event kinds: `phase_started`, `approval_requested`, `approved`, `rejected`, `agent_started`,
`agent_finished`, `epic_created`, `story_created`, `task_created`, `task_updated`,
`artifact_created`, `bug_reported`.

## Backlog
`GET /projects/1/backlog`
```json
{"vision": "Get things done",
 "epics": [{"id": 1, "title": "Tasks", "description": "",
            "stories": [{"id": 2, "epic_id": 1, "sprint_id": 1, "title": "Add todo",
                         "as_a": "user", "i_want": "to add a todo", "so_that": "I remember it",
                         "acceptance_criteria": ["Given ... When ... Then ..."],
                         "priority": 1, "points": 3, "status": "backlog"}]}]}
```

## Sprints
`GET /projects/1/sprints` returns
`[{"id", "number", "goal", "capacity", "status", "retro", "story_ids", "points"}]`.
`GET /sprints/1` adds `stories` and `tasks`.

## Tasks
```bash
curl -X PATCH localhost:8000/tasks/4 -H 'content-type: application/json' -d '{"status":"doing"}'
```
The change is logged as a `task_updated` event with agent `human`. An invalid status returns 422.

## Artifacts
`GET /projects/1/artifacts?kind=code` lists `id`, `kind`, `name`, `path`, `version`,
`created_by` and `created_at`. `GET /artifacts/7` adds `content` and `story_ids`.

## Traceability
`GET /projects/1/traceability` returns one row per backlog story. Artifacts are grouped by kind:
`architecture`, `diagram` and `api_spec` go in `design`; `code` and `test` keep their names;
anything else goes in `other`.
```json
[{"story_id": 2, "title": "Add todo", "status": "backlog",
  "design": [{"artifact_id": 5, "name": "openapi.yaml", "kind": "api_spec", "path": ""}],
  "code": [], "test": [], "other": []}]
```
`artifact_created`, `artifact_linked`, `design_skipped`, `design_missing`, `bug_reported`.
