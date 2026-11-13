"""Run one config on many seeds (at most --par worlds at once) and print the summary table.

  python harness/sweep.py --tag base --seeds dev-01..dev-06 [--level 8] [--par 3] [--set k=v ...]
  python harness/sweep.py --report base [other ...]      # table(s) from saved runs, paired on common seeds
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import time


def seeds_of(spec: str) -> list[str]:
    out = []
    for part in spec.split(","):
        if ".." in part:
            a, b = part.split("..")
            pre = a.rstrip("0123456789")
            lo, hi = int(a[len(pre):]), int(b[len(pre):])
            width = len(a) - len(pre)
            out += [f"{pre}{i:0{width}d}" for i in range(lo, hi + 1)]
        else:
            out.append(part)
    return out


def load(tag: str) -> dict[str, dict]:
    res = {}
    for p in glob.glob(os.path.join("data", "runs", tag, "*", "summary.json")):
        s = json.load(open(p))
        res[f"{s['seed']}-L{s['level']}"] = s
    return res


def table(tag: str, runs: dict[str, dict]) -> str:
    if not runs:
        return f"{tag}: no runs"
    m = sorted((r["score"]["marginCents"] / 100, k) for k, r in runs.items())
    ot = [r["score"]["onTimeShare"] for r in runs.values()]
    ranked = sum(r["score"]["ranked"] for r in runs.values())
    margins = [x for x, _ in m]
    p10 = margins[max(0, int(len(margins) * 0.1) - (1 if len(margins) >= 10 else 0))]
    orders = statistics.mean(r["score"]["wonOrders"] for r in runs.values())
    return (f"{tag:18s} n={len(runs):2d} ranked={ranked}/{len(runs)} min_ontime={min(ot):.3f} p10={p10:9.0f} "
            f"median={statistics.median(margins):9.0f} mean={statistics.mean(margins):9.0f} orders={orders:.0f} worst={[f'{k}:{x:.0f}' for x, k in m[:3]]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--seeds", default="dev-01..dev-06")
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--par", type=int, default=3)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--report", nargs="*")
    ap.add_argument("--reveal", action="store_true")
    args = ap.parse_args()
    if args.report:
        all_runs = {t: load(t) for t in args.report}
        common = set.intersection(*(set(r) for r in all_runs.values()))
        for t, r in all_runs.items():
            print(table(t, r))
        if len(all_runs) > 1:
            print(f"-- paired on {len(common)} common seeds")
            for t, r in all_runs.items():
                print(table(t, {k: v for k, v in r.items() if k in common}))
            print("seed".ljust(14) + "".join(t[:16].rjust(18) for t in all_runs))
            for k in sorted(common):
                print(k.ljust(14) + "".join(f"{all_runs[t][k]['score']['marginCents']/100:10.0f}/{all_runs[t][k]['score']['onTimeShare']:.3f}" for t in all_runs))
        return 0
    env = dict(os.environ, PYTHONPATH="src", PYTHONIOENCODING="utf-8")
    todo = [s for s in seeds_of(args.seeds) if not os.path.exists(os.path.join("data", "runs", args.tag, f"{s}-L{args.level}", "summary.json"))]
    running: list[subprocess.Popen] = []
    os.makedirs(os.path.join("data", "runs", args.tag), exist_ok=True)
    while todo or running:
        while todo and len(running) < args.par:
            s = todo.pop(0)
            cmd = [sys.executable, "-m", "spreadbot.run", "practice", "--level", str(args.level), "--seed", s, "--tag", args.tag, "--quiet"]
            for kv in args.set:
                cmd += ["--set", kv]
            if args.reveal:
                cmd.append("--reveal")
            log = open(os.path.join("data", "runs", args.tag, f"{s}-L{args.level}.out"), "w")
            running.append(subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT))
        time.sleep(2)
        running = [p for p in running if p.poll() is None]
    print(table(args.tag, load(args.tag)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
