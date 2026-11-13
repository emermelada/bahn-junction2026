"""Runners: a practice week on `advance`, and the live final on the stream. Same Desk in both.

  python -m spreadbot.run practice --level 8 --seed dev-01 --tag base [--set key=value ...] [--reveal]
  python -m spreadbot.run final [--set key=value ...]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import traceback

import spread

from .config import Config
from .desk import Desk
from .geo import DAY, HOUR, load_geo

WAKE = ["order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close", "gig_dropped", "no_show", "driver_late"]
STEP = 12  # minutes per daytime step: < 15 so every request gets its quote before respondBy
REGISTRY = "data/worlds_frank.jsonl"


def daytime(now: int) -> bool:
    d, m = now // DAY, now % DAY
    return d < 5 and 7 * HOUR + 50 <= m < 21 * HOUR + 30


def play_practice(world: "spread.World", desk: Desk, ends_at: int, events_out: list, quiet: bool = False) -> None:
    day = desk.now // DAY
    while desk.now < ends_at:
        actions = desk.outbox[:]
        desk.outbox.clear()
        if daytime(desk.now):
            # Pure time steps by day: every reaction waits at most STEP minutes, and a week takes ~500 requests.
            until, mx = [], desk.now + STEP
        else:
            until = WAKE + ["price_request", "order_won"]
            nxt = (desk.now // DAY) * DAY + 7 * HOUR + 50
            if nxt <= desk.now:
                nxt += DAY
            mx = min(nxt, desk.now + 3 * HOUR)
        if until:
            step = world.advance(until=until, max=min(mx, ends_at), actions=actions)
        else:
            step = world.advance(to=min(mx, ends_at), actions=actions)
        desk.read_results(actions, step["results"])
        desk.now = step["now"]
        for e in step["events"]:
            events_out.append(e)
            desk.handle(e)
        desk.tick()
        if desk.now // DAY > day and not quiet:
            s = world.score()
            print(f"day {day} margin {s['marginCents']/100:10.2f} orders {s['wonOrders']:4d} on-time {s['onTimeShare']:.3f} undelivered {s['undeliveredShare']:.3f}", flush=True)
            day = desk.now // DAY


def register(world_id: str, **info) -> None:
    os.makedirs("data", exist_ok=True)
    with open(REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"worldId": world_id, "t": time.time(), **info}) + "\n")


def practice(args) -> int:
    cfg = Config.parse(args.set or [])
    client = spread.Client()
    geo = load_geo(client)
    # The team's 8 practice slots are shared: wait for one instead of failing.
    for attempt in range(180):
        try:
            world = client.create(args.level, seed=args.seed)
            break
        except spread.SpreadError as e:
            if e.status != 409 or attempt == 179:
                raise
            time.sleep(20)
    register(world.id, seed=args.seed, level=args.level, tag=args.tag)
    out = os.path.join("data", "runs", args.tag, f"{args.seed}-L{args.level}")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    events: list = []
    try:
        snap = world.snapshot()
        desk = Desk(geo, cfg, args.level, snap["now"], world.roster())
        play_practice(world, desk, snap["endsAt"], events, quiet=args.quiet)
        score = world.score()
    except BaseException:
        traceback.print_exc()
        try:
            world.delete()
        except Exception:
            pass
        return 1
    summary = {"seed": args.seed, "level": args.level, "tag": args.tag, "world": world.id, "score": score,
               "seconds": round(time.time() - t0, 1), "config": {k: getattr(cfg, k) for k in cfg.__dataclass_fields__}}
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    with open(os.path.join(out, "log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(desk.log))
    if args.save_events:
        with gzip.open(os.path.join(out, "events.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(events, f)
    if args.reveal:
        with gzip.open(os.path.join(out, "reveal.json.gz"), "wt", encoding="utf-8") as f:
            json.dump({"reveal": world.reveal(), "events": events, "roster": list(desk.roster.values()), "gigs": world.snapshot()["gigs"]}, f)
    print(f"END {args.tag} {args.seed} L{args.level} margin {score['marginCents']/100:.2f} orders {score['wonOrders']} on-time {score['onTimeShare']:.3f} "
          f"undelivered {score['undeliveredShare']:.3f} ranked {score['ranked']} ({summary['seconds']}s)", flush=True)
    return 0


# ---------------------------------------------------------------------- final
def rejoin(desk: Desk, snapshot: dict, history: list) -> None:
    """Rebuilds the desk from the world's own record: replay events for the books, take gigs and
    orders from the snapshot, then answer what is missing (open requests, orders without a gig)."""
    from .desk import GigRec
    for g in snapshot["gigs"]:
        rec = GigRec(g["id"], g["stops"], g["audience"], g["schedule"], g["postedAt"], g["status"], g.get("driverId"), g.get("feeCents", 0))
        desk.gigs[rec.id] = rec
    for e in history:
        desk.now = max(desk.now, e["at"])
        desk.handle(e)
    desk.outbox.clear()
    desk.pending_posts.clear()
    desk.now = snapshot["now"]
    desk.leg_gig.clear()
    for g in snapshot["gigs"]:
        rec = desk.gigs[g["id"]]
        rec.status, rec.driver, rec.schedule = g["status"], g.get("driverId"), g["schedule"]
        if g["status"] in ("open", "booked", "working"):
            for key in rec.legs:
                desk.leg_gig[key] = rec.id
    for o in snapshot["orders"]:
        if o["id"] in desk.orders:
            if o["status"] == "cancelled":
                desk.orders.pop(o["id"])
            else:
                desk.orders[o["id"]].order = o
    for r in snapshot["openRequests"]:
        desk.handle({"kind": "price_request", "at": desk.now, "request": r, "seq": -1})
    desk.tick()


def final(args) -> int:
    cfg = Config.parse(args.set or [])
    client = spread.Client()
    geo = load_geo(client)
    logf = open(os.path.join("data", f"final-{int(time.time())}.log"), "a", encoding="utf-8")
    world = None
    while True:
        try:
            if world is None:
                world = wait_final(client)
                print("final world", world.id, flush=True)
            if run_live(world, client, geo, cfg, logf, lambda: client.final()["now"]):
                break
        except spread.Unreachable as e:
            print("unreachable:", e, "- rebuilding in 5 s", flush=True)
            time.sleep(5)
        except Exception:
            traceback.print_exc()
            time.sleep(2)
    print("final score", world.score(), flush=True)
    return 0


def wait_final(client) -> "spread.World":
    said = False
    while True:
        try:
            f = client.final()
            w = client.world(f["worldId"])
            s = w.snapshot()
            if s["now"] < s["endsAt"]:
                return w
        except spread.SpreadError as e:
            if e.status not in (404, 0):
                raise
        if not said:
            print("waiting for a final to be set ...", flush=True)
            said = True
        time.sleep(5)


def run_live(world, client, geo, cfg: Config, logf, clock) -> bool:
    """The live loop: rebuild from the world's record, then answer events from the stream.
    `clock()` gives the world minute when no event comes (client.final() in the final)."""
    history = world.events()
    snapshot = world.snapshot()
    if snapshot["now"] >= snapshot["endsAt"]:
        return True
    level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
    desk = Desk(geo, cfg, level, snapshot["now"], world.roster())
    rejoin(desk, snapshot, history)
    flush(world, desk, logf)
    last_seq = history[-1]["seq"] if history else -1
    day = desk.now // DAY
    last_tick = time.time()
    for e in world.stream(after=last_seq, idle=1.0):
        if e is not None:
            if e["seq"] <= last_seq:
                continue
            last_seq = e["seq"]
            desk.now = max(desk.now, e["at"])
            desk.handle(e)
        if e is None or time.time() - last_tick > 2.0:
            if e is None:
                desk.now = max(desk.now, clock())
            desk.tick()
            last_tick = time.time()
        flush(world, desk, logf)
        if desk.now // DAY > day:
            day = desk.now // DAY
            s = world.score()
            print(f"day {day} margin {s['marginCents']/100:.2f} orders {s['wonOrders']} on-time {s['onTimeShare']:.3f}", flush=True)
        if desk.now >= snapshot["endsAt"]:
            return True
    return True


def flush(world, desk: Desk, logf) -> None:
    if desk.log:
        logf.write("\n".join(desk.log) + "\n")
        logf.flush()
        desk.log.clear()
    if not desk.outbox:
        return
    actions = desk.outbox[:]
    desk.outbox.clear()
    # Quotes first: a late quote is a lost request; a late post only a little less slack.
    actions.sort(key=lambda a: 0 if a["type"] == "quote" else 1)
    results = world.act(actions)
    desk.read_results(actions, results)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["practice", "final"])
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--seed", default="dev-01")
    ap.add_argument("--tag", default="dev")
    ap.add_argument("--set", action="append")
    ap.add_argument("--reveal", action="store_true")
    ap.add_argument("--save-events", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    return practice(args) if args.mode == "practice" else final(args)


if __name__ == "__main__":
    sys.exit(main())
