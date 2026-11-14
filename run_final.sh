#!/usr/bin/env bash
# Plays the team's copy of the current final (or test final), and restarts the bot whenever it exits
# before the world ends. Run it once, before the start; it waits for the final. See research/RUNBOOK.md.
#   ./run_final.sh --preset <name> [--set key=value ...]     (from a worktree with .env and data/map.json)
#   PY=/path/to/python ./run_final.sh ...                     (another interpreter; default: a .venv nearby)
# Never run two copies at once, on this laptop or another: both would quote and post on the same world.
# A lock in $HOME refuses a second copy on this machine; FORCE=1 overrides a lock left by a dead run.
cd "$(dirname "$0")" || exit 1
[ -f .env ] || { echo "no .env here ($(pwd)): copy it from v1-evening (it holds SPREAD_URL and SPREAD_KEY)"; exit 2; }
set -a; . ./.env; set +a
[ -n "$SPREAD_KEY" ] || { echo ".env sets no SPREAD_KEY"; exit 2; }
export PYTHONPATH=src PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
if [ -z "$PY" ]; then
  for p in ./.venv/Scripts/python ./.venv/bin/python ../v1-evening/.venv/Scripts/python ../v1/.venv/Scripts/python; do
    [ -x "$p" ] && { PY=$p; break; }
  done
fi
PY=${PY:-python3}
"$PY" -c "import spread" 2>/dev/null || { echo "$PY cannot import the spread kit: set PY to a venv python"; exit 2; }
mkdir -p data
LOG=data/final-console.log

LOCK="$HOME/.spreadbot-final.lock"
if [ -f "$LOCK" ] && [ -z "$FORCE" ]; then
  read -r other where < "$LOCK"
  if kill -0 "$other" 2>/dev/null; then
    echo "another run_final.sh (pid $other, in $where) is running: stop it first, or FORCE=1 if it is gone"; exit 2
  fi
fi
echo "$$ $(pwd)" > "$LOCK"
trap 'read -r p _ < "$LOCK" 2>/dev/null; [ "$p" = "$$" ] && rm -f "$LOCK"' EXIT
trap 'echo "stopped by hand" | tee -a "$LOG"; exit 130' INT TERM

echo "=== $(date '+%F %T') laptop time, start: $(git log -1 --format='%h %s' 2>/dev/null) on $(git rev-parse --abbrev-ref HEAD 2>/dev/null); args: $*; python: $PY" | tee -a "$LOG"
attempt=0
while true; do
  attempt=$((attempt + 1))
  started=$SECONDS
  "$PY" -m spreadbot.run final "$@" 2>&1 | tee -a "$LOG"
  status=${PIPESTATUS[0]}
  [ $((SECONDS - started)) -gt 60 ] && attempt=1  # it had been running: restart fast
  case $status in
    0) echo "=== $(date '+%T') the final has ended; the bot stops" | tee -a "$LOG"; break ;;
    2) echo "=== bad arguments (status 2): fix the command, nothing was played" | tee -a "$LOG"; exit 2 ;;
    130) echo "=== stopped by hand" | tee -a "$LOG"; exit 130 ;;
  esac
  # A crash right at start-up (no network yet) waits longer each time, up to 30 s; never gives up.
  pause=$(( attempt < 10 ? 3 * attempt : 30 ))
  echo "=== $(date '+%T') bot exited with $status; restart $attempt in $pause s" | tee -a "$LOG"
  sleep "$pause"
done
