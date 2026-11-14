#!/bin/bash
# usage: lab/build/queue.sh PAR   (loads .env, never prints it; jobs in data/queue.txt)
cd "$(dirname "$0")/../.." || exit 1
set -a; . ./.env; set +a
export PYTHONIOENCODING=utf-8
exec ./.venv/Scripts/python lab/build/queue.py --par "${1:-2}" --file "${2:-data/queue.txt}" >> "${3:-data/queue.log}" 2>&1
