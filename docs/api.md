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
| GET | `/projects/{id}/traceability` | Story -> design -> code -> test table with test results |
| GET | `/projects/{id}/metrics` | GQM metrics per sprint, project totals, cost |
| GET | `/sprints/{id}/burndown` | Burndown series and ideal line of one sprint |

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

Add `&comment=...` to record a reason, for example when rejecting. It is saved as the message
of the `approved` or `rejected` event.

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

The stream starts with a `retry: 3000` line and a `: connected` comment, so clients see it open
at once. Use `?after=<id>` to skip older events. On reconnect, `EventSource` sends `Last-Event-ID`
automatically and the stream resumes after that event. A `: keep-alive` comment is sent after
15 seconds without events.

```js
const es = new EventSource("/projects/1/stream");
es.onmessage = (msg) => console.log(JSON.parse(msg.data));
```

Event kinds: `phase_started`, `approval_requested`, `approved`, `rejected`, `agent_started`,
`agent_finished`, `epic_created`, `story_created`, `task_created`, `task_updated`,
`artifact_created`, `artifact_linked`, `design_skipped`, `design_missing`, `bug_reported`,
`code_committed`, `code_unchanged`, `code_skipped`,
`file_rejected`, `bug_fixed`, `bug_fix_failed`, `bug_retry_limit`, `tests_committed`, `test_run`,
`tests_skipped`, `tests_missing`, `bug_reopened`, `bug_verified`, `bugs_left_open`,
`sprint_planned`, `release_file_rejected`, `release_file_missing`, `release_file_unchanged`, `release_committed`,
`docker_build_skipped`, `docker_build_succeeded`, `docker_build_failed`.

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
anything else goes in `other`. The other fields summarise the story's quality state.
```json
[{"story_id": 2, "title": "Add todo", "status": "sprint",
  "design": [{"artifact_id": 5, "name": "openapi.yaml", "kind": "api_spec", "path": ""}],
  "code": [], "test": [], "other": [],
  "sprint_number": 1, "tests_passed": 2, "tests_failed": 0, "last_test_ok": true,
  "open_bugs": 0, "ac_count": 2, "test_count": 2, "complete": false}]
```
| Field | Meaning |
|---|---|
| `sprint_number` | Number of the story's current sprint, `null` when it is not planned |
| `tests_passed`, `tests_failed`, `last_test_ok` | Result of the story's latest `test_run` (any sprint). `last_test_ok` is `null` when it never ran |
| `open_bugs` | Bugs of the story with status `open` |
| `ac_count` | Acceptance criteria of the story |
| `test_count` | Test functions in the latest version of each test file traced to the story |
| `complete` | The story has at least one design, one code and one test artifact |

## Metrics
`GET /projects/1/metrics` returns the GQM metrics (definitions in [metrics.md](metrics.md)).
Ratios are `null` when they are undefined (for example no test ran). Unknown project: 404.
```json
{"project": {"stories_total": 4, "stories_done": 4, "sprint_count": 2, "avg_velocity": 5.0,
             "total_cost_usd": 0.067, "llm_modes": ["live"], "trace_completeness": 0.25},
 "sprints": [{"sprint_id": 5, "sprint_number": 1, "closed": true, "committed_points": 8,
              "completed_points": 5, "commitment_reliability": 0.625, "first_pass_yield": 0.333,
              "test_pass_rate": 0.8, "bugs_open_at_end": 1, "est_cost_usd": 0.04,
              "process": {}}],
 "unattributed": {"llm_calls": 1, "input_tokens": 1000, "output_tokens": 500,
                  "est_cost_usd": 0.007},
 "gqm": [{"id": "G1", "goal": "...", "viewpoint": "Scrum Master",
          "questions": [{"id": "Q1", "text": "...", "metrics": [
            {"key": "commitment_reliability", "name": "...", "definition": "...",
             "unit": "ratio"}]}]}],
 "pricing": {"model": "claude-sonnet-5-5", "input_per_mtok": 2.0, "output_per_mtok": 10.0,
             "source": "..."}}
```
(The `project` and `sprints` objects are trimmed here; each lists every key from metrics.md.)

## Burndown
`GET /sprints/5/burndown` returns the points still open over time, rebuilt from task events.
`t` is seconds since the sprint started and `step` is the point's index; draw `step` when
`duration_s` is below one second. Unknown sprint: 404 `sprint not found`.
```json
{"sprint_id": 5, "sprint_number": 1, "committed_points": 8, "remaining_points": 3,
 "duration_s": 125.0, "closed": true,
 "series": [{"t": 0.0, "step": 0, "at": "2026-10-17T10:00:00", "remaining": 8,
             "story_id": null, "label": "Sprint start"},
            {"t": 40.2, "step": 1, "at": "2026-10-17T10:00:40", "remaining": 5,
             "story_id": 3, "label": "Done: A: sign in"}],
 "ideal": [{"t": 0.0, "remaining": 8}, {"t": 125.0, "remaining": 0}]}
```

`artifact_created`, `artifact_linked`, `design_skipped`, `design_missing`, `bug_reported`.
