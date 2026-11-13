#!/usr/bin/env bash
# Plays the team's copy of the current final (or test final) with the frozen v1 config, and restarts
# the bot if it ever exits before the world ends. Run it once, before the start; it waits for the final.
#   ./run_final.sh            (from the v1 folder, with .env holding SPREAD_URL and SPREAD_KEY)
# Never run two copies at once: both would quote and post on the same world.
cd "$(dirname "$0")" || exit 1
set -a; . ./.env; set +a
export PYTHONPATH=src PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python
[ -x "$PY" ] || PY=python3
mkdir -p data
for attempt in $(seq 1 100); do
  "$PY" -m spreadbot.run final "$@" 2>&1 | tee -a data/final-console.log
  status=${PIPESTATUS[0]}
  [ "$status" -eq 0 ] && break
  echo "bot exited with $status; restarting in 3 s (attempt $attempt)" | tee -a data/final-console.log
  sleep 3
done
