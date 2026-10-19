VENV=.venv
PY=$(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r requirements.txt
	test -f .env || cp .env.example .env

run:
	$(PY) -m uvicorn workbench.api.main:app --reload --reload-dir workbench --port 8000

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest -q --cov=workbench --cov-report=term-missing --cov-fail-under=95

lint:
	$(VENV)/bin/ruff check .

ui-setup:
	cd frontend && npm ci

ui:
	cd frontend && npm run dev

ui-test:
	cd frontend && npm run typecheck && npm test

seed:
	$(PY) scripts/seed_demo.py
