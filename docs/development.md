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
