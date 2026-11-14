#!/usr/bin/env bash
# Plays the final (or a test final) with Franko's v1 bot, preset "chains" (k18), from the worktree ../frank-v1,
# with this repo's Python environment (the kit is installed there). Restarts the bot whenever it exits with an
# error. Run once, before the start; it waits for the final. Never run two copies at once.
#   harness/final_frank.sh            (from this repo)
# Update the bot first: git fetch && git -C ../frank-v1 checkout --detach origin/branch-v1-frank
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BOT="$HERE/../frank-v1"
PY="$HERE/.venv/bin/python"
cd "$BOT" || { echo "no worktree at $BOT: git worktree add --detach ../frank-v1 origin/branch-v1-frank"; exit 1; }
set -a; . "$HERE/.env"; set +a
export PYTHONPATH=src PYTHONIOENCODING=utf-8
mkdir -p data
for attempt in $(seq 1 100); do
  "$PY" -m spreadbot.run final --preset chains 2>&1 | tee -a data/final-console.log
  status=${PIPESTATUS[0]}
  [ "$status" -eq 0 ] && break
  echo "bot exited with $status; restarting in 3 s (attempt $attempt)" | tee -a data/final-console.log
  sleep 3
done
