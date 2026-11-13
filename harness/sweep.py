"""Seed sweeps and paired comparisons. Every run writes data/runs/<world id>/; every sweep appends one row per
seed to data/results/<tag>.jsonl.

    python harness/sweep.py --set dev --tag base                    # the 10 DEV seeds
    python harness/sweep.py --set fresh --n 20 --tag rc1             # 20 fresh seeds named rc1-01 .. rc1-20
    python harness/sweep.py --set dev --tag hi --flag dealer.quote_ratio=1.4
    python harness/sweep.py --compare base hi                        # paired table on the seeds both played

Report order (CLAUDE.md): ranked rate, minimum on-time share, 10th percentile margin, median margin, worst 3 seeds.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from spread.client import Client

from spreadbot.runtime.practice_runner import play

RESULTS = "data/results"
WORKERS = 3  # our share of the team's 8 practice slots


def seeds_for(name: str, n: int, tag: str) -> list[str]:
    if name == "dev":
        return [f"dev-{k:02d}" for k in range(1, 11)]
    return [f"{tag}-{k:02d}" for k in range(1, n + 1)]


def set_flags(pairs: list[str]) -> dict[str, object]:
    """--flag side.name=value sets FLAGS[name] in spreadbot.<side>.flags for this process."""
    applied = {}
    for pair in pairs:
        key, raw = pair.split("=", 1)
        side, name = key.split(".", 1)
        flags = importlib.import_module(f"spreadbot.{side}.flags").FLAGS
        if name not in flags:
            sys.exit(f"unknown flag {key}; known: {sorted(flags)}")
        value = json.loads(raw)
        flags[name] = value if flags[name] is None or value is None else type(flags[name])(value)
        applied[key] = flags[name]
    return applied


def stats(rows: list[dict]) -> str:
    margins = sorted(r["marginCents"] / 100 for r in rows)
    p10 = margins[len(margins) // 10]
    ranked = sum(r["ranked"] for r in rows)
    worst = sorted(rows, key=lambda r: r["marginCents"])[:3]
    return (f"ranked {ranked}/{len(rows)}  min on-time {min(r['onTimeShare'] for r in rows):.1%}  p10 €{p10:,.0f}  "
            f"median €{statistics.median(margins):,.0f}  worst: " + ", ".join(f"{r['seed']} €{r['marginCents'] / 100:,.0f}" for r in worst))


def sweep(seeds: list[str], level: int, tag: str, flags: dict) -> list[dict]:
    world_map = Client().map()
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, f"{tag}.jsonl")

    def one(seed: str) -> Optional[dict]:
        try:
            r = play(level, seed, world_map=world_map, tag=tag)
        except Exception as error:  # noqa: BLE001 - one failed seed must not end the sweep
            print(f"{seed:<10} FAILED {error!r}", flush=True)
            return None
        row = {k: r[k] for k in ("seed", "level", "worldId", "commit", "marginCents", "revenueCents", "onTimeShare",
                                 "undeliveredShare", "wonOrders", "ranked", "steps", "seconds")}
        row["flags"] = flags
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{seed:<10} €{r['marginCents'] / 100:>11,.2f}  on time {r['onTimeShare']:6.1%}  orders {r['wonOrders']:>4}  "
              f"ranked {r['ranked']}", flush=True)
        return row

    with ThreadPoolExecutor(WORKERS) as pool:
        rows = [r for r in pool.map(one, seeds) if r is not None]
    print(f"[{tag}] {stats(rows)}")
    return rows


def load(tag: str) -> dict[str, dict]:
    with open(os.path.join(RESULTS, f"{tag}.jsonl"), encoding="utf-8") as f:
        return {r["seed"]: r for r in map(json.loads, f)}  # the latest row per seed


def compare(base: str, new: str) -> None:
    a, b = load(base), load(new)
    seeds = [s for s in a if s in b]
    print(f"{'seed':<10}{base:>14}{new:>14}{'delta':>12}   on-time {base} -> {new}")
    for s in seeds:
        d = (b[s]["marginCents"] - a[s]["marginCents"]) / 100
        print(f"{s:<10}{a[s]['marginCents'] / 100:>14,.0f}{b[s]['marginCents'] / 100:>14,.0f}{d:>12,.0f}   "
              f"{a[s]['onTimeShare']:.1%} -> {b[s]['onTimeShare']:.1%}")
    print(f"[{base}] {stats([a[s] for s in seeds])}")
    print(f"[{new}] {stats([b[s] for s in seeds])}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=["dev", "fresh"], default="dev")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--tag", default="adhoc")
    p.add_argument("--level", type=int, default=8)
    p.add_argument("--seeds", help="comma list, overrides --set")
    p.add_argument("--flag", action="append", default=[])
    p.add_argument("--compare", nargs=2, metavar=("BASE", "NEW"))
    args = p.parse_args()
    if args.compare:
        return compare(*args.compare)
    flags = set_flags(args.flag)
    seeds = args.seeds.split(",") if args.seeds else seeds_for(args.set, args.n, args.tag)
    sweep(seeds, args.level, args.tag, flags)


if __name__ == "__main__":
    main()
