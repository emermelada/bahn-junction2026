#!/bin/bash
# usage: lab/frank/best_queue.sh SEEDS "tag|preset|k=v k=v" ...   (one sweep after another, 1 world at a time)
# preset may be empty (= Config defaults, y4).
set -a; . ./.env; set +a
export PYTHONPATH=src
seeds=$1; shift
for spec in "$@"; do
  IFS='|' read -r tag preset sets <<< "$spec"
  args=()
  [ -n "$preset" ] && args+=(--preset "$preset")
  for kv in $sets; do args+=(--set "$kv"); done
  ../v1-evening/.venv/Scripts/python harness/sweep.py --tag "$tag" --seeds "$seeds" --par 1 --reveal "${args[@]}" | tail -1
done
