# Demo

The workbench can show a whole project, from idea to three released sprints, offline and at no
cost. The demo plays back **scripted LLM answers** through the normal agents and the normal
orchestrator, so every number, chart, commit and test result is real. Only the model's answers are
canned.

> **Honesty note.** The `todo-app` scenario is hand-written. It is not a recording of a model run
> and says nothing about what a model would produce. Say so when you present it. A real run is
> possible with an API key (see [Present live](#a-live-with-an-api-key)).

Contents: [What it shows](#what-the-todo-app-scenario-shows) · [Setup](#setup) ·
[Checklist](#pre-demo-checklist) · [Three ways to present](#three-ways-to-present) ·
[Talk track](#talk-track-about-16-minutes) · [Troubleshooting](#troubleshooting) ·
[Commands](#commands) · [Replay](#how-replay-works) · [Scenarios](#write-or-change-a-scenario)

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

## Setup

You need Python 3.12 and Node 22 or newer (the project was checked with Node 24). No API key.

PowerShell (Windows):
```powershell
git clone https://github.com/Muniya-64bit/scrum-agents-workbench.git
cd scrum-agents-workbench
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd frontend; npm ci; cd ..
```

bash (Linux, macOS, Git Bash):
```bash
git clone https://github.com/Muniya-64bit/scrum-agents-workbench.git
cd scrum-agents-workbench
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt     # Git Bash on Windows: .venv/Scripts/python
(cd frontend && npm ci)
```

Check it works (about 15 seconds, prints the summary table):
```powershell
.\.venv\Scripts\python scripts\demo.py run --scenario todo-app --fresh
```
```bash
.venv/bin/python scripts/demo.py run --scenario todo-app --fresh
```
The summary must show releases `v0.1.0, v0.2.0, v0.3.0`, sprints 10 to 7, 6 to 6 and 3 to 3, and
`0 mock fallbacks`.

## Pre-demo checklist

- [ ] The check run above matches the numbers. Do it on the machine you will present from.
- [ ] Ports 8000 and 5173 are free (see Troubleshooting).
- [ ] Terminal 1: `python scripts/demo.py serve --scenario todo-app --fresh` (**fresh every time**).
- [ ] Terminal 2: `cd frontend` then `npm run dev`. If the browser cannot reach the API on Windows,
      start it with `API_URL=http://127.0.0.1:8000` (PowerShell: `$env:API_URL="http://127.0.0.1:8000"`).
- [ ] Browser at `http://localhost:5173/projects/1/backlog` (the project is created, phase Idea).
      Window 1440 x 900 or larger, zoom 100 to 110%, light theme (better on a projector).
- [ ] The backup video `demo/video/demo.webm` exists and plays (create it with
      `cd frontend && npm run demo:video`; about two minutes; it is not in git).
- [ ] A second browser tab on this page and on `docs/demo.md` for the talk track.
- [ ] Notifications off, laptop on power, no other app on ports 8000 and 5173.

## Three ways to present

Pick the first that works. Move down the ladder, never up, once you have started.

### A. Live with an API key
Real model, unscripted, takes minutes per phase and costs money. Use a small project so it finishes:

```powershell
$env:DEFAULT_CAPACITY = "3"; $env:MAX_SPRINTS = "1"
.\.venv\Scripts\python scripts\demo.py serve --scenario todo-app --mode live --fresh
```
Put `ANTHROPIC_API_KEY` in `.env` first. A very long answer can be cut off at 8000 tokens and fail
validation (a known limit of live mode, not exercised in the tests); the client retries twice,
then the phase fails with an error toast. If that happens, switch to B.

### B. Replay (the normal demo)
`demo.py serve --scenario todo-app --fresh` plus the UI, as in the checklist. Nothing is random,
nothing costs money, the same story every time. You click through the phases yourself.

### C. Backup video
`demo/video/demo.webm`: the same tour as B, recorded by Playwright (1440 x 900, about 1 minute 45).
Open it in a browser (drag the file into a tab) or any video player. Create or refresh it with
`cd frontend && npm run demo:video`. Narrate over it with the talk track below.

## Talk track (about 16 minutes)

Click path in **bold**. "Say" is a suggestion in your own words. Each beat names the Scrum event
and the CS4222 concept it shows.

| Time | Screen and clicks | Say | Scrum event / concept |
|---|---|---|---|
| 0:00 | **Projects** page | "A multi-agent CASE tool: LLM agents play the Scrum roles and take an idea to a release. Humans approve at two gates. The model answers in this demo are scripted, everything else is real." | Process model as a program: the orchestrator *enacts* the process |
| 1:00 | Open **Todo app**, click **Start Backlog** | "The Product Owner writes the backlog, the Architect the design." After it finishes open a story (**Create item**) | Product backlog; user stories with Given/When/Then |
| 2:30 | **Start Planning**, then **Activity** (approval card) | "Sprint planning proposes 10 points. This is a gate: nothing runs until a human approves." Click **Approve** | Sprint planning; quality gate (Lec 8); human in the loop |
| 3:30 | **Sprint board**, click **Start Execution** | Watch tasks move. "Developer commits one story at a time, QA writes pytest tests from the acceptance criteria and runs them." | Sprint; Definition of Done enforced by tests |
| 5:00 | **Activity**: find *QA Bug reported* and *Developer ... fix* | "QA found a real defect: empty title returned 201 instead of 422. The Developer fixed it, QA verified. Story 4 stayed broken after its one attempt." | Quality assurance loop; every state change is an event (Tools API) |
| 6:00 | **Start Review**, **Approve** | "The second gate: sprint review." | Sprint review |
| 6:30 | **Start Retro**, then **Metrics** | "7 of 10 points: reliability 70%, first-pass yield 50%, 2 bugs. These come from the GQM goals: goal, question, metric." Expand *How these metrics were chosen* | Measurement (GQM, Lec 12); measurement support R2 |
| 8:00 | **Start Release**, then **Backlog** | "v0.1.0 is tagged. Look at *Next sprint*: capacity 10 to 7, test-first, two fix attempts, a working agreement. The retrospective changed the process, with its reason." | Retrospective; **PDCA / QIP**; process tailoring R3 (Lec 11) |
| 9:30 | **Start Sprint planning**, **Approve**; **Start Execution** on the board | "Sprint 2 runs with those levers. Tests are written first; the carried-over story is fixed with the second attempt." In Activity: *Wrote the tests for story #5 before the code* | Process deployment: the improved process is applied (Lec 8) |
| 11:30 | Review, Retro, Release; sprint 3 the same way | Keep it short. "Sprint 3 finishes the backlog; v0.3.0." Click **Finish project** | Release; Definition of Done |
| 13:00 | **Metrics**, scroll to **Process improvement (PDCA)** | "Plan, Do, Check, Act per sprint: reliability 70 to 100%, first-pass yield 50 to 100%, bugs 2 to 0. The process we used is recorded (descriptive); the retro proposes the next one (prescriptive)." | PDCA, QIP, Experience Factory; **descriptive vs prescriptive** process model (Lec 5, 9) |
| 14:30 | **Traceability**, click the chip **app/main.py v5** | "Story to design to code to test to release. The drawer shows the code that fixed the empty-title bug. Trace completeness 100%." | **Traceability** (Lec 11) |
| 15:30 | Back to the slides or this page | Limits: scripted answers, tiny app, one project; cost is zero because nothing was billed. Questions. | Honesty about validity |

If you run late, skip sprint 3 by saying so and jump to Metrics at the end of sprint 2 (the PDCA
cards still show sprints 1 and 2).

## Troubleshooting

| Problem | Fix |
|---|---|
| `Address already in use` / the UI shows old data | Free the ports: PowerShell `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen \| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`; bash `lsof -ti :8000,:5173 \| xargs kill`. Or serve on another port: `--port 8001` and `API_URL=http://127.0.0.1:8001` for the UI |
| `The demo database already has a project ... start again with --fresh` | The replay position is lost when the server restarts mid-demo. Stop the server and start it again with `--fresh` |
| UI shows "Project not found" | The server was restarted with `--fresh`: open `/projects/1/backlog` again |
| `No recorded response for developer.DeveloperAgent.execution.s1.delete-item #3 in ...` | You clicked more than the script has: a restart without `--fresh`, or a changed scenario. Use `--fresh`; to see what is missing run `scripts/scenario_keys.py --scenario demo/scenarios/todo-app --db demo_runs/todo-app.db` |
| Activity shows `llm_replay_drift` | The agent's prompt changed since the answer was written. The scripted answer is still used; harmless for the demo |
| Activity says "Docker build disabled in mock mode" | The DevOps agent labels replay as mock mode. No Docker is needed |
| Browser shows a blank page or network errors | Check both terminals are running; `curl http://127.0.0.1:8000/health` must answer `{"status":"ok"}` |
| `npm run dev` proxy errors on Windows | `localhost` can resolve to `::1`. Start the UI with `API_URL=http://127.0.0.1:8000` |
| Python or Node too old | Python 3.12 is required (the code uses 3.12 syntax); Node 22 or newer |
| `npm run demo:video` fails on the first run | `cd frontend && npx playwright install chromium`; ports 8000 and 5173 must be free (Playwright starts its own servers) |
| A phase takes a long time | Execution runs real pytest runs, 3 to 5 seconds per phase in replay. In live mode it takes minutes |

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

# the backup video (starts its own servers; ports 8000 and 5173 must be free)
cd frontend && npm run demo:video   # writes demo/video/demo.webm
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

The generated project is in `demo_runs/todo-app-workspaces/project-1`: run `git log --oneline`,
`git tag` and `python -m pytest` there to show the real repository.

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
