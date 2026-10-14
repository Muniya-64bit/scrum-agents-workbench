VENV=.venv
PY=$(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r requirements.txt
	test -f .env || cp .env.example .env

run:
	$(PY) -m uvicorn workbench.api.main:app --reload --port 8000

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check .
