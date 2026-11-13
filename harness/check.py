"""The merge gate after the unit tests: a 3 seed level 8 smoke, the determinism test (dev-01 twice, the same
score to the cent and the same state) and the replay test (the saved log rebuilds the same state).

    python harness/check.py [--require-ranked]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from spread.client import Client

from spreadbot.core.state import State, replay
from spreadbot.runtime.practice_runner import play

SEEDS = ["dev-01", "dev-02", "dev-03", "dev-01"]
WORKERS = 3  # our share of the team's 8 practice slots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ranked", action="store_true", help="fail when a smoke seed is not ranked")
    parser.add_argument("--level", type=int, default=8)
    args = parser.parse_args()
    world_map = Client().map()
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = list(pool.map(lambda seed: play(args.level, seed, world_map=world_map, tag="check"), SEEDS))
    for r in rows:
        print(f"{r['seed']:<8} margin €{r['marginCents'] / 100:>11,.2f}  on time {r['onTimeShare']:6.1%}  orders {r['wonOrders']:>4}  "
              f"ranked {str(r['ranked']):<5}  {r['steps']} steps {r['seconds']}s  digest {r['digest']}")
    failures = []
    a, b = rows[0], rows[3]
    if (a["marginCents"], a["digest"]) != (b["marginCents"], b["digest"]):
        failures.append(f"determinism: dev-01 gave {a['marginCents']}/{a['digest']} then {b['marginCents']}/{b['digest']}")
    with open(os.path.join(a["runDir"], "log.jsonl"), encoding="utf-8") as f:
        rebuilt = replay(map(json.loads, f), State(a["worldId"], args.level, 0, 0, world_map)).summary()["digest"]
    if rebuilt != a["digest"]:
        failures.append(f"replay: log rebuilt {rebuilt}, run ended with {a['digest']}")
    if args.require_ranked:
        failures += [f"not ranked: {r['seed']}" for r in rows[:3] if not r["ranked"]]
    for failure in failures:
        print("FAIL", failure)
    print("check OK" if not failures else "check FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
