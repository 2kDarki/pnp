.PHONY: check compile type test schema

check: compile type test schema

compile:
	python -m compileall -q pnp tests tools

type:
	python -m mypy

test:
	python -m unittest discover -s tests -v

schema:
	python tools/schema_gate.py
