# Metrics

How we measure the AI Scrum process. The metrics are defined top-down with
**Goal-Question-Metric (GQM)**: start from a goal, ask the questions that tell us whether we reach
it, and only then pick the metrics that answer those questions. The code is in
`workbench/metrics.py`; the dashboard is described in [frontend.md](frontend.md).

## Goals, questions and metrics
| Goal | Question | Metrics |
|---|---|---|
| **G1** Improve the predictability of sprint delivery (Scrum Master) | **Q1** How much of what we commit do we deliver? | `committed_points`, `completed_points`, `commitment_reliability`, `carried_over_stories` |
| | **Q2** Is the sprint on track while it runs? | burndown (remaining vs ideal) |
| **G2** Improve product quality (QA) | **Q3** Does new code pass its tests the first time? | `first_pass_yield`, `test_pass_rate`, `test_runs` |
| | **Q4** How many defects appear and how costly are they to fix? | `bugs_reported`, `bugs_open_at_end`, `fix_attempts`, `retry_limit_hits`, `llm_invalid_outputs` |
| **G3** Keep requirements traceable (Product Owner) | **Q5** Is every story covered by design, code and tests? | `trace_completeness`, `ac_coverage` |
| **G4** Control the cost of the AI team (the team) | **Q6** What does the AI team cost per unit of delivered work? | `llm_calls`, `input_tokens`, `output_tokens`, `est_cost_usd`, `cost_per_completed_point` |

## Definitions and data sources
All counts are for the stories the sprint committed to (its *plan*) and for events inside the
sprint's window (see below).

| Metric | Definition | Source |
|---|---|---|
| `committed_points`, `committed_stories` | Points and number of stories chosen at planning | `sprint_planned` event |
| `completed_points`, `completed_stories` | Committed stories whose tasks are all `done` when the sprint ends | `task_created` / `task_updated` replay |
| `commitment_reliability` | `completed_points / committed_points` | derived |
| `carried_over_stories` | Committed stories not done at the end | derived |
| `test_runs` | Number of test runs for committed stories | `test_run` events |
| `first_pass_yield` | Stories whose first run in the sprint passed / stories with at least one run | `test_run` events |
| `test_pass_rate` | Σ passed / Σ (passed + failed) over each story's last run in the sprint | `test_run` events |
| `bugs_reported` | Bugs filed in the sprint for committed stories | `bug_reported` events |
| `bugs_fixed_in_sprint` | Bugs QA verified as fixed in the sprint | `bug_verified` events |
| `bugs_open_at_end` | Bugs of committed stories still open at the end (status replayed from bug events) | `bug_*` events |
| `fix_attempts` | Developer fix attempts in the sprint | `bug_fixed`, `bug_fix_failed` events |
| `retry_limit_hits` | Open bugs at the end whose fix attempts reached the sprint's `max_fix_retries` (default `DEFAULT_MAX_FIX_RETRIES`) | `bug_*` events, `sprint_planned.process` |
| `llm_calls`, `input_tokens`, `output_tokens`, `cache_hits`, `llm_invalid_outputs` | Sums of the usage that every agent run logs | `agent_finished` events |
| `est_cost_usd` | `input_tokens × input price + output_tokens × output price` | derived, see limitations |
| `cost_per_completed_point` | `est_cost_usd / completed_points` | derived |
| `trace_completeness` | Committed stories with at least one design (`architecture`, `diagram`, `api_spec`, `design`), one `code` and one `test` artifact / committed stories | `trace_links` |
| `ac_coverage` | Σ min(test functions, acceptance criteria) / Σ acceptance criteria. Test functions are the `def test_` lines of the newest version of each test file traced to the story | `trace_links`, artifacts |

Trace completeness and AC coverage are also shown, per story, on the Traceability page
(`/projects/:id/traceability`), where each gap is marked and every artifact can be opened.

Ratios are `null` when the denominator is 0. Ratios are rounded to 3 decimals, money to 4
decimals and seconds to 3.

Project totals add `stories_total`, `stories_done`, `points_total`, `points_done`,
`sprint_count`, `avg_velocity` (mean completed points of closed sprints), token and cost totals,
`llm_modes`, `loc` (lines in the newest version of each code file) and `trace_completeness` over
all planned stories. Usage logged before the first sprint (backlog and design) is reported
separately as `unattributed`.

## Windows and replay
Metrics are computed by replaying the append-only event log in id order, so any number can be
reproduced from the database and does not depend on how the orchestrator orders the agents. A
sprint's *window* starts at its `sprint_planned` event and ends at its `retro_saved` event (or
just before the next sprint starts, or at the last event while it is still running). The
burndown replays task events inside the window: after each event it recomputes which committed
stories are done and records the points still open. Usage logged after a window ends but before
the next one starts (retro, release) is charged to that sprint.

## Burndown
`GET /sprints/{id}/burndown` returns one point at sprint start, one each time a story becomes done
(or is reopened) and one at the end, plus an ideal line from the commitment to zero. `t` is the
number of seconds since sprint start. In a fast mock run all points are within a second of each
other, so the UI plots the step number instead when the sprint lasted less than a second.

## Limitations
- In mock mode no tokens are spent, so usage and cost are zero. Mock runs report `llm_mode: mock`.
- Cost is an estimate: tokens times the prices in `LLM_PRICE_INPUT_PER_MTOK` and
  `LLM_PRICE_OUTPUT_PER_MTOK` (USD per million tokens, defaults are the Claude Sonnet 5.5 list
  price). Change them if you use another model. Cached answers cost nothing and show as
  `cache_hits`.
- Replayed runs report the usage that was recorded, not new spending.
- The burndown x-axis is time since the sprint started, not working days.
- The data comes from event payloads. Projects created before the usage payload existed have no
  token data; their metrics show zeros.
