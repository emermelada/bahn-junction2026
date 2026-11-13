#!/usr/bin/env bash
# Usage: ./run.sh [--level N] [--seed text] [--board] [--final]
cd "$(dirname "$0")" && set -a && . ./.env && set +a && node starter.ts "$@"
