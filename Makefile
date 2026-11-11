PY ?= .venv/bin/python

.PHONY: setup test run-experiments dashboard

setup:
	python3.11 -m venv .venv
	$(PY) -m pip install -q -e .

test:
	$(PY) -m pytest -q

run-experiments:
	$(PY) -m src.eval.runner

dashboard:
	$(PY) -m streamlit run src/dashboard/app.py
