#!/bin/sh
# Supervisor for the final (Linux VM): restarts the desk until the world ends. Usage: ./final.sh [cfg/gated.json]
cd "$(dirname "$0")"
while true; do
  node src/run-final.ts --cfg "${1:-cfg/gated.json}"; code=$?
  [ $code -eq 0 ] && echo "final ended" && break
  [ $code -eq 130 ] && echo "stopped" && break
  echo "desk exited with $code; restarting in 2 s"; sleep 2
done
