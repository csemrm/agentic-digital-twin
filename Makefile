PY ?= .venv/bin/python
PYTHON ?= python3

.PHONY: setup test run-experiments dashboard

setup:
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q -e .

test:
	$(PY) -m pytest -q

run-experiments:
	$(PY) -m src.eval.runner

dashboard:
	$(PY) -m streamlit run src/dashboard/app.py
