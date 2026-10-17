# Development guide

## Prerequisites
- Python 3.12
- `make` and `git`
- A Claude API key only if you want real model calls

## Setup
```bash
git clone https://github.com/Muniya-64bit/scrum-agents-workbench.git
cd scrum-agents-workbench
make setup
```
`make setup` creates `.venv`, installs `requirements.txt` and copies `.env.example` to `.env`.
The default `MOCK_LLM=1` needs no API key.

## Everyday commands
| Command | Purpose |
|---|---|
| `make run` | Start the API with reload on port 8000 |
| `make test` | Run pytest |
| `make lint` | Run ruff |

## Environment variables
| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Needed only with `MOCK_LLM=0` |
| `WORKBENCH_MODEL` | `claude-sonnet-5-5` | Model used by all agents |
| `MOCK_LLM` | `1` | `1` = deterministic canned responses, no API calls. Used only when `LLM_MODE` is unset (`0` means `live`) |
| `LLM_MODE` | derived from `MOCK_LLM` | `mock`, `live`, `record` or `replay` (see below). Any other value stops the app at start |
| `LLM_SCENARIO_DIR` | empty | Scenario directory for `record` and `replay` |
| `LLM_REPLAY_FALLBACK` | `error` | `replay` only: `error` fails on a missing answer, `mock` uses the agent's mock output |
| `DATABASE_URL` | `sqlite:///./workbench.db` | Database |
| `WORKSPACES_DIR` | `./workspaces` | Where generated code is written |
| `DEFAULT_MAX_FIX_RETRIES` | `3` | Developer attempts per bug in the first sprint |
| `DEFAULT_CAPACITY` | `10` | Story points the first sprint commits to |
| `MAX_SPRINTS` | `3` | The orchestrator stops starting new sprints after this many |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | `2.0`, `10.0` | USD per million tokens, for cost estimates |

Later sprints take capacity and the retry limit from the retrospective (docs/agents.md).

## LLM modes
Every agent talks to the model through `LLMClient`. `LLM_MODE` decides where the answers come from.

| Mode | What it does | Cost | Use it for |
|---|---|---|---|
| `mock` | Each agent's `mock_output()`; no network | Free | Development, unit tests, CI |
| `live` | Claude API, answers cached by prompt hash in `.cache/llm/` | Tokens | Real runs |
| `record` | Like `live` but ignores the cache and saves every answer in the scenario directory | Tokens | Making a scenario from a real run |
| `replay` | Reads the answers from the scenario directory; never calls a model | Free | Demos, the backup video, regression tests |

`record` and `replay` need `LLM_SCENARIO_DIR`. Recorded answers are filed by meaning, not by
prompt hash, so a prompt edit does not invalidate a recording (see `llm_key` in
[agents.md](agents.md)). In `replay` mode `config.MOCK_LLM` is true, so the DevOps agent skips
the docker build as it does in mock mode.

```
demo/scenarios/<name>/
  scenario.json                 name, idea, env, fallback (see demo.md)
  README.md
  calls/<key>.<n>.json          one file per LLM call; n counts calls with the same key
```

Each call file holds `key`, `n`, `schema`, `prompt_sha256`, `output` (the validated answer),
`usage` (`input_tokens`, `output_tokens`), `source` (`recorded` or `scripted`), `model` and
`recorded_at`.

**Record** a run with a real key (this spends tokens: a three-sprint run is several dozen calls):

```bash
LLM_MODE=record LLM_SCENARIO_DIR=demo/scenarios/my-run ANTHROPIC_API_KEY=... python scripts/demo.py ...
```

**Replay.** The n-th call with a key reads `<key>.<n>.json`. A prompt that differs from the one
recorded still gets the recorded answer, and the run logs an `llm_replay_drift` event. A missing
file raises `LLMError: No recorded response for <key> #<n> in <dir>`; with
`LLM_REPLAY_FALLBACK=mock` the agent's mock output is used instead and an `llm_replay_fallback`
event is logged. `python scripts/scenario_keys.py --scenario DIR [--db FILE]` lists the recorded
keys and, with the database of a replay run, the keys that fell back to the mock: those are the
calls still to record or write by hand.

## Team workflow
1. Pick an issue and assign yourself. Labels show the day (`day-1` to `day-3`) and workstream (`ws1` to `ws6`).
2. Branch from an up-to-date `main` as `feat/<issue>-short-name`.
3. Commit small and mention the issue, for example `Add PO agent (#7)`.
4. Run `make lint test` before pushing.
5. Open a pull request with `Closes #<issue>` and ask one teammate to review.
6. Squash merge once CI is green.

Only commit source and docs. `.gitignore` already excludes `.venv`, `.env`, databases, caches
and generated workspaces. Stage files by name rather than `git add -A` if you are unsure.

Do not change shared contracts (`workbench/schemas.py`, `docs/architecture.md`) without telling
the team, because other workstreams build against them.

## Conventions
- Line length 100, enforced by ruff.
- Tests run with `MOCK_LLM=1` and an in-memory database (see `tests/conftest.py`).
- Use type hints on public functions.

## Troubleshooting
| Problem | Fix |
|---|---|
| `make setup` is slow | The first dependency install downloads about 100 MB; let it finish |
| `ModuleNotFoundError: workbench` | Run commands from the repo root, using `.venv/bin/python` or `make` |
| Tests call the real API | Check `.env` has `MOCK_LLM=1` |
| `LLMError: No valid output` | The model returned JSON that failed the schema; simplify the schema or prompt |
| 409 on `/advance` | The project is waiting at a gate; call `/approve` first |
| Stale database after a model change | Delete `workbench.db`; it is recreated on startup |
