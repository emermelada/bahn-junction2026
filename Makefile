# Loads SPREAD_URL and SPREAD_KEY from .env (gitignored). See .env.example.
-include .env
export SPREAD_URL SPREAD_KEY

PY := PYTHONPATH=src .venv/bin/python
LEVEL ?= 8
SEED ?= dev-01

.PHONY: setup test check play
setup:
	python3 -m venv .venv && .venv/bin/pip install -q $${SPREAD_URL:-https://spread.bahnexpress.com}/kit/spread-0.1.0-py3-none-any.whl

test:
	$(PY) -m unittest discover -s tests -t .

# The merge gate: unit tests, determinism, replay, 3 seed level 8 smoke. Add --require-ranked once a baseline is ranked.
check: test
	$(PY) harness/check.py

play:
	$(PY) -m spreadbot.runtime.practice_runner --level $(LEVEL) --seed $(SEED)
