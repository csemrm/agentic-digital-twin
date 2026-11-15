# Build the paper from experiment results. Run from the paper/ directory: `make` (or `make PY=/path/to/python`).
PY ?= ../.venv/bin/python
RESULTS ?= ../results_real

.PHONY: all tables clean
all: main.pdf

tables:
	cd .. && $(PY) paper/make_tables.py --results $(patsubst ../%,%,$(RESULTS)) --out paper/generated

main.pdf: main.tex refs.bib generated/macros.tex generated/tab_main.tex generated/tab_gate.tex
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

generated/macros.tex generated/tab_main.tex generated/tab_gate.tex: tables

clean:
	latexmk -C
	rm -f main.bbl main.run.xml
