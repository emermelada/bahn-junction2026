"""One queue for all practice runs of this worktree, so we never hold more than --par worlds at once.

  python lab/build/queue.py --par 3          # reads data/queue.txt again before every launch

data/queue.txt, one job per line:  priority | tag | preset | k=v k=v ... | seeds
Lower priority first; within a priority, seed by seed across jobs (so arms stay paired while they run).
Each tag freezes a copy of src/ at its first launch, as harness/sweep.py does. A run whose summary.json
exists is never played again. No new world in the test-final windows (see BLACKOUT in run.py).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "harness"))
from sweep import seeds_of  # noqa: E402

BLACKOUT = [(12 * 60 + 20, 14 * 60 + 50), (18 * 60 + 20, 19 * 60 + 50)]  # laptop clock = Helsinki - 1 h


def blocked() -> bool:
    t = time.localtime()
    m = t.tm_hour * 60 + t.tm_min
    return any(a <= m < b for a, b in BLACKOUT)


def jobs(path: str) -> list[tuple]:
    out = []
    if not os.path.exists(path):
        return out
    for n, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        prio, tag, preset, sets, seeds = [x.strip() for x in line.split("|")]
        out.append((int(prio), n, tag, preset, sets.split(), seeds_of(seeds)))
    return out


def done(tag: str, seed: str) -> bool:
    return os.path.exists(os.path.join("data", "runs", tag, f"{seed}-L8", "summary.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--par", type=int, default=3)
    ap.add_argument("--file", default=os.path.join("data", "queue.txt"))
    args = ap.parse_args()
    running: dict[tuple[str, str], subprocess.Popen] = {}
    failed: dict[tuple[str, str], int] = {}
    while True:
        # Count failures (exit without a summary), so a broken config does not loop forever.
        for k, p in list(running.items()):
            if p.poll() is not None:
                if not done(*k):
                    failed[k] = failed.get(k, 0) + 1
                    print(time.strftime("%H:%M:%S"), "FAILED", *k, flush=True)
                else:
                    print(time.strftime("%H:%M:%S"), "done", *k, flush=True)
                del running[k]
        if len(running) < args.par and not blocked():
            todo = []
            for prio, n, tag, preset, sets, seeds in jobs(args.file):
                for i, s in enumerate(seeds):
                    k = (tag, s)
                    if k in running or done(tag, s) or failed.get(k, 0) >= 2:
                        continue
                    todo.append(((prio, i, n), tag, preset, sets, s))
            todo.sort()
            for _, tag, preset, sets, s in todo[: args.par - len(running)]:
                snap = os.path.join("data", "runs", tag, "src")
                if not os.path.exists(snap):
                    shutil.copytree("src", snap, ignore=shutil.ignore_patterns("__pycache__"))
                env = dict(os.environ, PYTHONPATH=snap, PYTHONIOENCODING="utf-8")
                cmd = [sys.executable, "-m", "spreadbot.run", "practice", "--level", "8", "--seed", s, "--tag", tag, "--quiet"]
                if preset:
                    cmd += ["--preset", preset]
                for kv in sets:
                    cmd += ["--set", kv]
                log = open(os.path.join("data", "runs", tag, f"{s}-L8.out"), "w")
                running[(tag, s)] = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
                print(time.strftime("%H:%M:%S"), "start", tag, s, flush=True)
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
