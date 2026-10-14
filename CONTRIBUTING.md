# Contributing

- Pick an issue, assign yourself, branch from `main`: `feat/<issue#>-short-name`.
- Commit messages reference the issue: `Add PO agent (#7)`.
- Open a PR with `Closes #<issue>`; at least one teammate reviews; squash merge.
- Before pushing: `make lint test`.
- Develop with `MOCK_LLM=1` (default in `.env.example`) so nothing costs tokens.
- Do not change shared contracts (`workbench/schemas.py`, `docs/architecture.md`) without telling the team.

## Setup
```
make setup   # venv + deps + .env
make run     # API on http://localhost:8000 (docs at /docs)
make test
```
