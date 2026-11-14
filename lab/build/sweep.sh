#!/bin/bash
# usage: lab/build/sweep.sh TAG SEEDS PAR [--preset P] [--set k=v ...]   (loads .env, never prints it)
cd "$(dirname "$0")/../.." || exit 1
set -a; . ./.env; set +a
export PYTHONIOENCODING=utf-8
tag=$1; seeds=$2; par=$3; shift 3
./.venv/Scripts/python harness/sweep.py --tag "$tag" --seeds "$seeds" --par "$par" "$@" > "data/sweep-$tag.txt" 2>&1
