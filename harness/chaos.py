"""Chaos test: the live runner plays an emulated live week and is killed (SIGKILL) and restarted on the way.
A pass means the week ends ranked and no leg was ever on two live gigs at once.

    python harness/chaos.py --seed chaos-01 --from-minute 4320 --speed 4 --kills 2
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from collections import Counter

from spread.client import Client

from spreadbot.runtime.practice_runner import create_world

sys.path.insert(0, os.path.dirname(__file__))
from emulate import ticker  # noqa: E402

RUNNER = [sys.executable, "-m", "spreadbot.runtime.live_runner", "--world"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", default="chaos-01")
    p.add_argument("--from-minute", type=int, default=4320)
    p.add_argument("--speed", type=float, default=4.0)
    p.add_argument("--kills", type=int, default=2)
    p.add_argument("--every", type=float, default=60, help="real seconds between kills")
    args = p.parse_args()
    client = Client()
    world = create_world(client, 8, args.seed)
    if args.from_minute:
        world.advance(to=args.from_minute)
    snap = world.snapshot()
    stop = threading.Event()
    threading.Thread(target=ticker, args=(world.id, snap["now"], snap["endsAt"], args.speed, stop), daemon=True).start()
    print(f"chaos on {world.id}", flush=True)
    env = {**os.environ, "PYTHONPATH": "src"}
    doubled: set = set()

    def watch(seconds: float) -> None:
        """Polls the world, collecting legs that sit on two live gigs at once."""
        end = time.monotonic() + seconds
        while time.monotonic() < end and bot.poll() is None:
            live = Counter((s["orderId"], s["leg"]) for g in world.snapshot()["gigs"] if g["status"] in ("open", "booked", "working")
                           for s in g["stops"] if s["kind"] == "pickup")
            doubled.update(leg for leg, n in live.items() if n > 1)
            time.sleep(5)

    bot = subprocess.Popen(RUNNER + [world.id], env=env)
    for k in range(args.kills):
        watch(args.every)
        if bot.poll() is not None:
            break
        bot.send_signal(signal.SIGKILL)
        bot.wait()
        print(f"kill {k + 1} at minute {world.snapshot()['now']}", flush=True)
        time.sleep(5)
        bot = subprocess.Popen(RUNNER + [world.id], env=env)
    watch(float("inf"))
    bot.wait()
    stop.set()
    score = world.score()
    print(f"score {score}")
    print(f"legs on two live gigs: {len(doubled)}")
    ok = score["ranked"] and not doubled
    print("chaos PASS" if ok else "chaos FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
