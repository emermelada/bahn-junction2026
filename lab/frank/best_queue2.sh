#!/bin/bash
# usage: lab/frank/best_queue2.sh FIRST LAST "tag|preset|k=v k=v" ...   e.g. 7 18 -> dev-07..dev-18
# One world at a time, one seed per sweep call, and no new world in the test-final windows
# (laptop clock = Helsinki - 1 h: no start 12:20-13:50 and 18:20-19:50 laptop time).
set -a; . ./.env; set +a
export PYTHONPATH=src
first=$1; last=$2; shift 2
blocked() { local t=$((10#$(date +%H%M))); { [ $t -ge 1220 ] && [ $t -lt 1350 ]; } || { [ $t -ge 1820 ] && [ $t -lt 1950 ]; }; }
for spec in "$@"; do
  IFS='|' read -r tag preset sets <<< "$spec"
  args=()
  [ -n "$preset" ] && args+=(--preset "$preset")
  for kv in $sets; do args+=(--set "$kv"); done
  for n in $(seq $first $last); do
    s=$(printf "dev-%02d" $n)
    while blocked; do sleep 60; done
    ../v1-evening/.venv/Scripts/python harness/sweep.py --tag "$tag" --seeds "$s..$s" --par 1 --reveal "${args[@]}" > /dev/null
  done
  ../v1-evening/.venv/Scripts/python harness/sweep.py --report "$tag" | head -1
done
