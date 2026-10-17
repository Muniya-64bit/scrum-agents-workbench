# Demo

The workbench can show a whole project, from idea to three released sprints, offline and at no
cost. The demo plays back **scripted LLM answers** through the normal agents and the normal
orchestrator, so every number, chart, commit and test result is real. Only the model's answers are
canned.

> **Honesty note.** The `todo-app` scenario is hand-written. It is not a recording of a model run
> and says nothing about what a model would produce. Say so when you present it. A real run is
> possible with an API key (see "Record a real run").

## What the todo-app scenario shows

| Step | What happens | Concept |
|---|---|---|
| Backlog | A Product Owner turns the idea into 6 stories (16 points); an Architect designs the API | Process enactment by agents |
| Sprint 1 (capacity 10) | Four stories, 10 points. QA's tests catch a missing empty-title check in story 1, the Developer fixes it. Story 4 (delete) is still wrong after the one allowed fix | Quality gates, bug loop |
| Review and retro 1 | 7 of 10 points done. Story 4 goes back to the backlog. The retrospective changes the process: capacity 7, test-first on, two fix attempts, a working agreement | Measurement, PDCA/QIP, process tailoring |
| Sprint 2 (capacity 7) | Story 4 (carried) and story 5. Tests are written before the code; story 4's second fix works. 6 of 6 points | Descriptive process (what was used) vs the proposal |
| Sprint 3 | Story 6, tests first. The backlog is empty | |
| Releases | `v0.1.0`, `v0.2.0`, `v0.3.0`: notes, git tags, traceability from story to release | Traceability |
| End | The generated app has 14 passing tests; the Metrics page shows reliability 70% to 100% and first-pass yield 50% to 100% | GQM |

Details, the story-id map and the expected numbers: [demo/scenarios/todo-app/README.md](../demo/scenarios/todo-app/README.md).

## Commands

`scripts/demo.py` sets the environment, creates a database and a workspace under `demo_runs/`
(git-ignored; it never touches `./workbench.db` or `./workspaces`) and plays the scenario.

```bash
# in the terminal, idea -> done in about 15 seconds, then a summary and the PDCA comparison
python scripts/demo.py run --scenario todo-app --fresh

# the same, paused after every phase with a short summary (press Enter to continue)
python scripts/demo.py run --scenario todo-app --fresh --step

# for the UI: creates the project, then serves the API on :8000
python scripts/demo.py serve --scenario todo-app --fresh
cd frontend && npm run dev          # http://localhost:5173, open the printed project URL
```

| Option | Meaning |
|---|---|
| `--scenario NAME` | A folder under `demo/scenarios/` |
| `--fresh` | Delete the run database and workspace first. Needed whenever the run already exists: a restarted server or a second run would lose its place in the script |
| `--mode` | `replay` (default), `record`, `mock` (the agents' built-in mock answers) or `live` (the real model, costs money) |
| `--step` | `run` only: pause after each phase |
| `--port`, `--host` | `serve` only (defaults 8000, 127.0.0.1) |

Variables that are already set in the shell win over the scenario's `env` (for example
`MAX_SPRINTS=1`).

## How replay works

Each agent asks the model through `LLMClient`. In `replay` mode the client reads the answer from
`calls/<key>.<n>.json`. The key says what the call is for (`developer.DeveloperAgent.execution.s1.
delete-item`), the number counts repeats of the same key (the second Developer call for that
story is the bug fix). See [development.md](development.md#llm-modes) for the file format, drift
and fallback. If a call has no file the run stops with
`No recorded response for <key> #<n>`; with `fallback: "mock"` in `scenario.json` the agent's mock
answer is used and an `llm_replay_fallback` event is logged.

## Write or change a scenario

1. Copy `demo/scenarios/todo-app` and edit `scenario.json` (`project_name`, `idea`, `env`).
2. Run `python scripts/demo.py run --scenario NAME --fresh`. Calls without a file use the mock.
3. List what is missing:
   `python scripts/scenario_keys.py --scenario demo/scenarios/NAME --db demo_runs/NAME.db`.
4. Write those answers (the todo-app files come from `author.py`, which builds the generated
   application story by story) and repeat until the storyline happens as you want it.
5. Pin it with a test like `tests/test_demo_scenario.py`.

Scripted answers carry `"source": "scripted"` and zero usage, so the Metrics page shows no cost.

## Record a real run

```bash
python scripts/demo.py record --scenario todo-app
```

This needs `ANTHROPIC_API_KEY` in `.env`, asks for a typed `yes` (it calls the real model for every
agent step, which costs money) and writes `demo/scenarios/todo-app-recorded/`. A real model will
not follow the scripted storyline. Replay the recording with `--scenario todo-app-recorded`.
