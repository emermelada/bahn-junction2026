"""Live-clock rehearsal on a practice world: a ticker thread advances the world at the final's speed while the
live runner plays it from the stream, exactly as in the final.

    python harness/emulate.py --seed dev-01 [--from-minute 4320] [--speed 1.0]

Final speeds (HANDBOOK): a weekday hour 06-22 takes 18 s, a Saturday hour 6 s, a last-Monday hour 9 s,
every other hour 3 s. The ticker sends one advance every TICK seconds, of as many world minutes as that
speed gives. --from-minute fast-forwards first (the test finals start on Thursday 00:00 = 4320).
"""
from __future__ import annotations

import argparse
import threading
import time

from spread.client import Client

from spreadbot.runtime.live_runner import play_live

TICK = 0.3  # real seconds between advances; one weekday minute at final speed
DAY, HOUR = 1440, 60


def real_seconds_per_hour(minute: int) -> float:
    day, hour = minute // DAY, minute % DAY // HOUR
    if 6 <= hour < 22:
        if day < 5:
            return 18
        if day == 5:
            return 6
        if day == 7:
            return 9
    return 3


def ticker(world_id: str, start: int, ends_at: int, speed: float, stop: threading.Event) -> None:
    world = Client().world(world_id)
    now, owed = start, 0.0
    while now < ends_at and not stop.is_set():
        owed += TICK * speed * HOUR / real_seconds_per_hour(now)  # world minutes due this tick
        step = int(owed)
        if step:
            owed -= step
            now = world.advance(by=step)["now"]
        time.sleep(TICK)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", default="dev-01")
    p.add_argument("--level", type=int, default=8)
    p.add_argument("--from-minute", type=int, default=0)
    p.add_argument("--speed", type=float, default=1.0, help="2.0 plays twice as fast as the final")
    args = p.parse_args()
    client = Client()
    world = client.create(level=args.level, seed=args.seed)
    print(f"emulating {world.id} seed {args.seed}", flush=True)
    if args.from_minute:
        world.advance(to=args.from_minute)  # no bot yet: requests before this minute go unanswered
    snap = world.snapshot()
    stop = threading.Event()
    thread = threading.Thread(target=ticker, args=(world.id, snap["now"], snap["endsAt"], args.speed, stop), daemon=True)
    thread.start()
    try:
        print(play_live(client, world, args.level), flush=True)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
