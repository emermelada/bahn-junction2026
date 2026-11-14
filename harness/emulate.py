"""Rehearse the live final on a practice world: a ticker advances the clock by itself, the bot runs its
live loop on the stream. Optional kill/restart to test recovery.

  python harness/emulate.py --seed emu-01 [--ms-per-min 100] [--restart-at 2000] [--set k=v ...]
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, "src")
import spread  # noqa: E402

from spreadbot.config import Config  # noqa: E402
from spreadbot.geo import DAY, HOUR, load_geo  # noqa: E402
from spreadbot.run import patient, register, run_live, supervise, transient  # noqa: E402


class Ticker(threading.Thread):
    """Advances the world like the final's clock: slow in weekday daytime, fast at night and after Friday.
    A network break (DNS, Wi-Fi, server restart) pauses it, as a server restart pauses the final's clock;
    it never ends the thread. `world` needs its own Client: one HTTP connection is not shared across threads."""

    def __init__(self, world: "spread.World", ms_per_min: int):
        super().__init__(daemon=True)
        self.world = world
        self.ms, self.now, self.ends, self.stop = ms_per_min, 0, None, False
        self.day_by = 5
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self._run()
        except BaseException as e:  # a dead ticker freezes the world: say so loudly
            self.error = e
            print(f"TICKER STOPPED: {type(e).__name__}: {e}", flush=True)

    def _run(self) -> None:
        snap = patient(self.world.snapshot, what="ticker")
        self.now, self.ends = snap["now"], snap["endsAt"]
        delay = 5.0
        while self.now < self.ends and not self.stop:
            d, m = self.now // DAY, self.now % DAY
            busy = d < 5 and 6 * HOUR <= m < 22 * HOUR
            by = self.day_by if busy else 30
            t0 = time.time()
            try:
                step = self.world.advance(by=min(by, self.ends - self.now))
            except spread.SpreadError as e:
                if not transient(e):
                    raise
                # The step may have happened before the answer was lost: read the clock back instead of
                # advancing twice, then go on. 5, 10, 20, 40, 60 s between tries: no hammering.
                print(f"ticker: {e}; again in {delay:.0f} s", flush=True)
                time.sleep(delay)
                delay = min(60.0, 2 * delay)
                try:
                    self.now = self.world.snapshot()["now"]
                except spread.SpreadError:
                    pass
                continue
            delay = 5.0
            self.now = step["now"]
            time.sleep(max(0.0, self.ms * by / 1000 - (time.time() - t0)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="emu-01")
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--ms-per-min", type=int, default=100)
    ap.add_argument("--restart-at", type=int, default=-1, help="world minute at which the bot is killed and rebuilt")
    ap.add_argument("--set", action="append", default=[])
    args = ap.parse_args()
    cfg = Config.parse(args.set)
    client = spread.Client()
    geo = load_geo(client)
    world = client.create(args.level, seed=args.seed)
    register(world.id, seed=args.seed, level=args.level, tag="emulate")
    print("emulated world", world.id, flush=True)
    ticker = Ticker(spread.Client().world(world.id), args.ms_per_min)
    ticker.start()
    os.makedirs("data", exist_ok=True)
    logf = open(f"data/emulate-{args.seed}.log", "w", encoding="utf-8")
    t0 = time.time()
    try:
        if args.restart_at > 0:
            # First life: stop the live loop at the restart minute by making the clock look finished.
            class Kill(Exception):
                pass

            def clock1() -> int:
                if ticker.now >= args.restart_at:
                    raise Kill()
                return ticker.now
            try:
                run_live(world, client, geo, cfg, logf, clock1)
            except Kill:
                print(f"killed at minute {ticker.now}; rebuilding from snapshot and events", flush=True)
            client = spread.Client()  # a fresh process would have a fresh client
        # Second life (or the only one): the final's supervisor, so a break here rebuilds as it would live.
        supervise(client.world(world.id), client, geo, cfg, logf, lambda: ticker.now)
    finally:
        ticker.stop = True
    s = patient(client.world(world.id).score)
    print(f"END emulate {args.seed} margin {s['marginCents']/100:.2f} orders {s['wonOrders']} on-time {s['onTimeShare']:.3f} ranked {s['ranked']} ({time.time()-t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
