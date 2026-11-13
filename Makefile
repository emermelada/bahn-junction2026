# Loads SPREAD_URL and SPREAD_KEY from .env (gitignored). See .env.example.
-include .env
export SPREAD_URL SPREAD_KEY

PY := PYTHONPATH=src .venv/bin/python
LEVEL ?= 8
SEED ?= dev-01

.PHONY: setup test check play sweep compare emulate chaos final
SET ?= dev
TAG ?= adhoc
N ?= 20
setup:
	python3 -m venv .venv && .venv/bin/pip install -q $${SPREAD_URL:-https://spread.bahnexpress.com}/kit/spread-0.1.0-py3-none-any.whl

test:
	$(PY) -m unittest discover -s tests -t .

# The merge gate: unit tests, determinism, replay, and a 3 seed level 8 smoke that must stay ranked.
check: test
	$(PY) harness/check.py --require-ranked

play:
	$(PY) -m spreadbot.runtime.practice_runner --level $(LEVEL) --seed $(SEED)

sweep:
	$(PY) harness/sweep.py --set $(SET) --n $(N) --tag $(TAG)

compare:
	$(PY) harness/sweep.py --compare $(BASE) $(NEW)

# Live-clock rehearsal: a practice world advanced at final speed, played from the stream.
emulate:
	$(PY) harness/emulate.py --seed $(SEED) --from-minute 4320

chaos:
	$(PY) harness/chaos.py --seed $(SEED) --from-minute 4320 --speed 4 --kills 2

# The final (or a test final), under a supervisor that restarts the bot whenever it exits with an error.
final:
	until $(PY) -m spreadbot.runtime.live_runner --final; do echo "bot exited, restarting in 2 s"; sleep 2; done
