#!/bin/bash
# usage: lab/frank/loop.sh SEEDS "tag|k=v k=v ..." ...   (one sweep after another, 3 worlds at a time)
set -a; . ./.env; set +a
seeds=$1; shift
for spec in "$@"; do
  tag=${spec%%|*}; sets=${spec#*|}; args=()
  for kv in $sets; do args+=(--set "$kv"); done
  .venv/Scripts/python harness/sweep.py --tag "$tag" --seeds "$seeds" --par ${PAR:-3} ${REVEAL:+--reveal} "${args[@]}"
done
