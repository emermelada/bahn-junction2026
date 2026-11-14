#!/usr/bin/env bash
# One ranking run with Franko's v1 bot, preset "chains_plus" (k18 + batch cap 6), from ../frank-plus with this repo's Python.
# Counts on the leaderboard and cannot be undone: humans only. Waits for a free practice slot.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/../frank-plus" || exit 1
set -a; . "$HERE/.env"; set +a
export PYTHONPATH=src PYTHONIOENCODING=utf-8
exec "$HERE/.venv/bin/python" -m spreadbot.run practice --board --level 8 --tag board --preset chains_plus
