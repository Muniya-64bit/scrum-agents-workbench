# Scripted scenario: todo-app

**Scripted scenario — hand-written responses, not a recorded model run.**

Every file in `calls/` was written by a person (`"source": "scripted"`, zero token usage). Nothing
here shows what a model would answer. What is real: the generated FastAPI code, the pytest tests,
the two defects (the runner really executes the tests and they really fail or pass), the git
history and tags, and every number on the Metrics page. The scenario exists so the process
(sprints, bugs, carry-over, retrospective, process change, releases) can be shown offline, at zero
cost, in the same way every time.

## Story ids (a fresh database)

| Id | Story | Priority | Points |
|---|---|---|---|
| 1 | Create item | 1 | 3 |
| 2 | List items | 1 | 2 |
| 3 | Complete item | 1 | 2 |
| 4 | Delete item | 2 | 3 |
| 5 | Edit title | 2 | 3 |
| 6 | Filter by status | 3 | 3 |

## What happens

| Sprint | Process used | Stories | Committed -> completed | What the run shows |
|---|---|---|---|---|
| 1 | capacity 10, 1 fix attempt, tests after the code | 1, 2, 3, 4 | 10 -> 7 | Story 1: QA's "empty title -> 422" test fails (the code returns 201), the Developer fixes it. Story 4: "unknown id -> 404" fails (200), the one fix attempt is wrong, the story is carried over |
| retro 1 | | | | Capacity 7 (last sprint's velocity), test-first on, 2 fix attempts, one working agreement |
| 2 | capacity 7, 2 attempts, test-first | 4 (carried), 5 | 6 -> 6 | The second fix attempt for story 4 works; story 5's tests are written before its code and pass first time |
| 3 | unchanged | 6 | 3 -> 3 | Tests first again; the backlog is empty |

Releases: `v0.1.0`, `v0.2.0`, `v0.3.0` (notes, git tag, traceability). The generated app ends with
14 passing tests. Expected numbers: commitment reliability 70% -> 100% -> 100%, first-pass yield
50% -> 100% -> 100%, bugs 2 -> 0 -> 0, no mock fallbacks, no prompt drift.

The scenario needs `DEFAULT_CAPACITY=10`, `DEFAULT_MAX_FIX_RETRIES=1` and `MAX_SPRINTS=3`;
`scenario.json` sets them and `scripts/demo.py` applies them.

## Run it

```bash
python scripts/demo.py run --scenario todo-app --fresh          # in the terminal
python scripts/demo.py serve --scenario todo-app --fresh        # for the UI
```

See [docs/demo.md](../../../docs/demo.md).

## Change it

The JSON files are generated: edit `author.py` and run `python demo/scenarios/todo-app/author.py`.
It builds the application code story by story, so a defect can be added or removed by changing one
argument of `main_py(...)`. Keys name the call (`developer.DeveloperAgent.execution.s1.delete-item`)
and a number counts repeats of the same key (the second answer is the fix). After a change run
`python scripts/demo.py run --scenario todo-app --fresh` and
`python scripts/scenario_keys.py --scenario demo/scenarios/todo-app --db demo_runs/todo-app.db`;
the second command lists calls that fell back to the mock because no answer was written for them.
`tests/test_demo_scenario.py` pins the numbers above.

## Re-record with a real model

`python scripts/demo.py record --scenario todo-app` runs the same idea against the real model
(needs `ANTHROPIC_API_KEY`, costs money, asks for confirmation) and writes
`demo/scenarios/todo-app-recorded/`. A real model will not hit this exact storyline. Replay the
recording with `--scenario todo-app-recorded`.
