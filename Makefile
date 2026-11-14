# Loads SPREAD_URL and SPREAD_KEY from .env (gitignored). See .env.example.
-include .env
export SPREAD_URL SPREAD_KEY

PY := PYTHONPATH=src .venv/bin/python
LEVEL ?= 8
SEED ?= dev-01

.PHONY: setup test check play board board-frank final-frank sweep compare emulate chaos final
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

# The team's next ranking run at LEVEL (default 8). Counts on the leaderboard; cannot be undone. Humans only.
board:
	$(PY) -m spreadbot.runtime.practice_runner --level $(LEVEL) --board

sweep:
	$(PY) harness/sweep.py --set $(SET) --n $(N) --tag $(TAG)

compare:
	$(PY) harness/sweep.py --compare $(BASE) $(NEW)

# Live-clock rehearsal: a practice world advanced at final speed, played from the stream.
emulate:
	$(PY) harness/emulate.py --seed $(SEED) --from-minute 4320

chaos:
	$(PY) harness/chaos.py --seed $(SEED) --from-minute 4320 --speed 4 --kills 2

# The team's next ranking run with Franko's v1 bot, preset chains. Counts on the leaderboard. Humans only.
board-frank:
	harness/board_frank.sh

# The final (or a test final) with Franko's v1 bot, preset chains (k18): the team's bot from 14 Nov.
final-frank:
	harness/final_frank.sh

# The final (or a test final) with our bot, under a supervisor that restarts it whenever it exits with an error.
final:
	until $(PY) -m spreadbot.runtime.live_runner --final; do echo "bot exited, restarting in 2 s"; sleep 2; done
