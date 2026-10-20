# REST API reference

Base URL: `http://localhost:8000`. Interactive docs are served at `/docs` (Swagger UI).
All bodies are JSON. Authentication is optional: see [Authentication](#authentication).

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
| GET | `/projects/{id}/backlog` | Vision, epics and their stories (priority order), NFRs and the backlog check |
| GET | `/projects/{id}/sprints` | Sprints with story ids and total points |
| GET | `/sprints/{id}` | One sprint with its stories and tasks |
| GET | `/projects/{id}/tasks?sprint_id=&status=` | Tasks, optionally filtered |
| PATCH | `/tasks/{id}` | Move a task to `todo`, `doing`, `testing` or `done` |
| GET | `/projects/{id}/artifacts?kind=` | Artifact list (without content) |
| GET | `/artifacts/{id}` | One artifact with content and linked story ids |
| GET | `/projects/{id}/bugs?status=` | Bugs filed against the project's stories |
| GET | `/projects/{id}/traceability` | Story -> design -> code -> test table with test results |
| GET | `/projects/{id}/releases` | One release per finished sprint (`v0.N.0`) with its notes artifact |
| GET | `/projects/{id}/release-checks` | The checks made on each release: the app starts, serves its contract, requirements, security |
| POST | `/projects/{id}/maintenance` | Report a problem found after the release (409 unless the project is done) |
| GET | `/projects/{id}/report` | A Markdown report of the project |
| GET | `/projects/{id}/export` | A zip of the report and the generated project |
| GET | `/projects/{id}/process` | The sprint's process levers and the process planned for the next sprint |
| GET | `/process/model` | The process model: roles, product flow, entry/exit criteria and RACI per phase |
| GET | `/projects/{id}/metrics` | GQM metrics per sprint, project totals, cost |
| GET | `/sprints/{id}/burndown` | Burndown series and ideal line of one sprint |

Every response has a schema in the OpenAPI docs at `/docs`. Unknown ids return 404.

## Authentication
By default there is none: run the API locally or behind an SSH tunnel. Start it with
`WORKBENCH_API_TOKEN=<secret>` and every endpoint except `/health` needs the token, as
`Authorization: Bearer <secret>`. A browser `EventSource` cannot send headers, so the event stream
and any other URL also accept `?token=<secret>`. A request without a valid token gets 401 and
`{"detail": "A valid API token is required"}`. The web UI asks for the token once and keeps it in
the browser. The token is compared in constant time; it protects against casual access, not against
someone who can read the traffic, so use HTTPS or a tunnel on a shared network.

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

Rejecting **sprint planning** returns the planned stories to the backlog, removes the tasks the
plan created (a carried-over story keeps its earlier tasks) and sets the sprint to `replanning`.
The project stays at `sprint_planning` with `"replanning": true`, and the next `advance` plans the
same sprint again; the Scrum Master's prompt includes the reason. Rejecting the **review** does
not repeat the sprint: the next `advance` runs the retrospective, which is told the reason and
must respond to it.

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
`docker_build_skipped`, `docker_build_succeeded`, `docker_build_failed`, `vision_set`,
`sprint_created`, `story_planned`, `sprint_skipped`, `story_carried_over`, `process_changed`,
`burndown_snapshot`, `retro_saved`, `retro_exists`, `standup`, `tests_unchanged`,
`tests_written_first`, `release_created`, `release_exists`, `release_skipped`,
`llm_replay_drift`, `llm_replay_fallback`, `nfrs_set`, `backlog_validated`,
`entry_criteria_checked`, `exit_criteria_checked`, `sprint_plan_rejected`, `story_unplanned`,
`sprint_replanned`, `agent_message`, `story_refined`, `backlog_refined`, `refinement_skipped`,
`tests_corrected`, `tests_review_unchanged`, `tests_revised`, `tests_revision_unchanged`,
`code_rejected`, `bug_attempts_reset`, `release_check`, `maintenance_requested`.

`agent_message` is one agent telling another something (`payload.to` is the receiver role,
`payload.body` the detail), for example the Architect announcing a contract or QA asking the
Developer to fix a bug.

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
A story's `status` is `backlog` or `sprint` as stored, and `done` once all its tasks are done (derived
when the response is built; the same value is used in sprint details and the traceability rows).

The response also has `nfrs`, the non-functional requirements the Product Owner wrote (`[]` if
none), and `quality`, the latest rule-based backlog check (`null` before the backlog phase). See
`workbench/requirements.py` for the rules.
```json
{"nfrs": [{"category": "product", "requirement": "The API shall answer in fixed time.",
           "measure": "95% of requests answered in under 300 ms"}],
 "quality": {"stories": 6, "flagged_stories": 1,
             "warnings": [{"rule": "vague_wording", "story_id": 4,
                           "message": "Wording is vague and cannot be verified",
                           "detail": "easy"}]}}
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
`architecture`, `diagram` and `api_spec` go in `design`; `code`, `test` and `release` keep their
names (`release` holds the `Release vX.Y.Z` notes of the sprints that released the story);
anything else goes in `other`. The other fields summarise the story's quality state.
```json
[{"story_id": 2, "title": "Add todo", "status": "sprint",
  "design": [{"artifact_id": 5, "name": "openapi.yaml", "kind": "api_spec", "path": "",
              "version": 1}],
  "code": [], "test": [], "release": [], "other": [],
  "sprint_number": 1, "sprints": [1], "tests_passed": 2, "tests_failed": 0, "last_test_ok": true,
  "open_bugs": 0, "ac_count": 2, "test_count": 2, "complete": false}]
```
| Field | Meaning |
|---|---|
| `sprint_number` | Number of the story's current sprint, `null` when it is not planned |
| `sprints` | Every sprint number the story was planned into, carried-over ones included (`[]` when never planned). The traceability page filters by it |
| `tests_passed`, `tests_failed`, `last_test_ok` | Result of the story's latest `test_run` (any sprint). `last_test_ok` is `null` when it never ran |
| `open_bugs` | Bugs of the story with status `open` |
| `ac_count` | Acceptance criteria of the story |
| `test_count` | Test functions in the latest version of each test file traced to the story |
| `complete` | The story has at least one design, one code and one test artifact |

## Releases
`GET /projects/1/releases` lists the releases, oldest first. Each sprint ends with one release
(see "Release step" in [agents.md](agents.md)); `artifact_id` is the release notes artifact, open
it with `GET /artifacts/{artifact_id}`. Unknown project: 404.
```json
[{"artifact_id": 21, "version": "v0.1.0", "sprint_id": 5, "sprint_number": 1,
  "created_at": "2026-10-17T10:00:00", "story_ids": [2, 3], "sha": "0123456789abcdef..."}]
```

## Release checks
`GET /projects/1/release-checks` lists the checks made when each sprint was released, oldest
release first (see "Release checks" in [agents.md](agents.md)). A run without a real model makes
none, so the list is empty. Unknown project: 404.
```json
[{"version": "v0.1.0", "sprint_id": 5, "name": "starts", "status": "passed",
  "detail": "serves its OpenAPI document"},
 {"version": "v0.1.0", "sprint_id": 5, "name": "serves its contract", "status": "failed",
  "detail": "not served: GET /loans"},
 {"version": "v0.1.0", "sprint_id": 5, "name": "The API shall respond quickly", "status": "met",
  "detail": "p95 12 ms against 300 ms"}]
```
`status` is `passed`, `failed` or `skipped` for the checks of the app, and `met`, `not met` or
`unverified` for a non-functional requirement (`unverified`: no automatic check exists for it).

## Maintenance
`POST /projects/1/maintenance` reports a problem found after the release. Body:
`{"title": "Empty title is accepted", "description": "Creating an item with an empty title returns
201.", "points": 2}` (`title` 3 to 120 characters, `description` 3 to 1000, `points` 1, 2, 3 or 5,
default 2). It adds a top-priority story `Fix: <title>` with two Given/When/Then criteria to a
`Maintenance` epic, logs `maintenance_requested` and moves the project to `release`, so the next
`advance` plans a maintenance sprint (it may exceed `MAX_SPRINTS`: each request adds one sprint to
the limit while its fix waits). The response is the project (`has_more_sprints` is true). A project
that is not finished: 409. Unknown project: 404. Invalid body: 422.

## Export
`GET /projects/1/report` returns a Markdown report (`text/markdown`): the idea and vision, the
outcome, the non-functional requirements, the backlog with acceptance criteria, every sprint with
its retrospective, the releases and their checks and the open bugs.
`GET /projects/1/export` returns a zip (`application/zip`, `Content-Disposition: attachment;
filename="<project>.zip"`) with `PROJECT_REPORT.md` and the generated project under `project/`
(code, tests, Dockerfile, CI workflow and release notes; no git history, caches or database files).
Unknown project: 404.

## Process
`GET /projects/1/process` returns the levers of the latest sprint and the ones the next sprint will
use once the retrospective's changes are applied (`next_changes` lists `[old, new]` pairs for the
levers that change, `{}` when nothing changes). Before any sprint, `current` and `next` are the
defaults. Unknown project: 404.
```json
{"current": {"capacity": 10, "max_fix_retries": 3, "test_first": false, "guidelines": []},
 "current_sprint_number": 1,
 "next": {"capacity": 7, "max_fix_retries": 3, "test_first": true,
          "guidelines": ["Write the acceptance tests first and make them pass before committing"]},
 "next_changes": {"capacity": [10, 7], "test_first": [false, true],
                  "guidelines": [[], ["Write the acceptance tests first and make them pass before committing"]]},
 "next_reason": "Commit to last sprint's velocity (yesterday's weather); ..."}
```

## Process model
`GET /process/model` returns one entry per phase from `workbench/process_model.py`: `phase`,
`name`, `purpose`, `responsible`, `agents`, `consumes`, `produces`, `gate`, `raci` (role ->
`R`, `A`, `R/A`, `C` or `I`), and `entry` and `exit` criteria (`[{id, text}]`). The orchestrator
checks the criteria at every phase and logs `entry_criteria_checked` and `exit_criteria_checked`
events (`payload.results`, `payload.unmet`). They are advisory and never block a step. The same
model generates the tables in [process-handbook.md](process-handbook.md).

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

## Improvement
`GET /projects/1/improvement` returns one Plan-Do-Check-Act row per sprint (see
[metrics.md](metrics.md)). Unknown project: 404. `GET /projects/{id}` also has `has_more_sprints`,
true only while the project is at `release` and another sprint will follow.
```json
[{"sprint_number": 2,
  "plan": {"process": {"capacity": 7, "max_fix_retries": 2, "test_first": true, "guidelines": []},
           "changes_applied": {"capacity": [10, 7]}, "reason": "..."},
  "do": {"committed_points": 7, "completed_points": 7},
  "check": {"commitment_reliability": 1.0, "first_pass_yield": 1.0, "test_pass_rate": 1.0,
            "bugs_reported": 1, "fix_attempts": 3, "est_cost_usd": 0.05},
  "deltas": {"commitment_reliability": 0.3, "first_pass_yield": 0.667, "test_pass_rate": 0.2,
             "bugs_reported": -2, "fix_attempts": 1, "est_cost_usd": 0.01},
  "act": {"went_well": [], "went_wrong": [], "actions": [], "proposed_changes": {}}}]
```
