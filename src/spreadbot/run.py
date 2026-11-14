"""Runners: a practice week on `advance`, and the live final on the stream. Same Desk in both.

  python -m spreadbot.run practice --level 8 --seed dev-01 --tag base [--set key=value ...] [--reveal]
  python -m spreadbot.run final [--preset NAME] [--set key=value ...]

Every break (no network, DNS, a 20 s timeout, a server restart, a bug in the loop) is answered the same
way: wait, rebuild the desk from the world's own record (events + snapshot), go on.
Exit codes: 0 the world ended, 1 failed, 2 bad arguments (fix the command), 130 stopped by hand.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import traceback

import spread
import spread.stream

from .config import Config
from .desk import Desk
from .geo import DAY, HOUR, load_geo

WAKE = ["order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close", "gig_dropped", "no_show", "driver_late"]
STEP = 12  # minutes per daytime step: < 15 so every request gets its quote before respondBy
REGISTRY = "data/worlds_frank.jsonl"
PROBE = 6.0  # real seconds of stream silence before asking GET /events whether the stream died quietly (a day hour is 18 s)
BATCH = 50  # actions per call, the API's maximum
# The kit waits up to 300 s for a TCP connect and for the rest of a frame; 30 s bounds a hang on a dead link.
spread.stream.QUIET_LIMIT = 30
# Test finals 14:00 and 20:00 Helsinki: no new practice world from 40 min before to 50 min after (rate limits drop
# to 20/s for everyone). Laptop clock (local time) = Helsinki - 1 h. Harness only, never inside decisions.
BLACKOUT = [(12 * 60 + 20, 14 * 60 + 50), (18 * 60 + 20, 19 * 60 + 50)]


def wait_blackout() -> None:
    while True:
        t = time.localtime()
        m = t.tm_hour * 60 + t.tm_min
        if not any(a <= m < b for a, b in BLACKOUT):
            return
        time.sleep(60)


def daytime(now: int) -> bool:
    d, m = now // DAY, now % DAY
    return d < 5 and 7 * HOUR + 50 <= m < 21 * HOUR + 30


def transient(e: BaseException) -> bool:
    """A break that passes by itself: no answer, DNS, a timeout, a server restart (502-504), an overload."""
    return isinstance(e, spread.Unreachable) or (isinstance(e, spread.SpreadError) and (e.status == 429 or e.status >= 500))


def patient(fn, *args, what: str = "", tries: int = 12, **kw):
    """Calls `fn`, which must be safe to repeat (a read). On a transient break waits 5, 10, 20, 40, 60, 60 ... s
    (about 8 minutes in all) and tries again: a DNS or Wi-Fi drop costs time, not the run, and never hammers."""
    delay = 5.0
    for attempt in range(tries):
        try:
            return fn(*args, **kw)
        except spread.SpreadError as e:
            if not transient(e) or attempt == tries - 1:
                raise
            print(f"break ({what or getattr(fn, '__name__', 'call')}): {e}; again in {delay:.0f} s", flush=True)
            time.sleep(delay)
            delay = min(60.0, 2 * delay)


def play_practice(world: "spread.World", desk: Desk, ends_at: int, events_out: list, quiet: bool = False, after: int = -1) -> None:
    day = desk.now // DAY
    last_seq = after
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
            if e["seq"] <= last_seq:  # after a rebuild, a step can repeat events that the rebuild already read
                continue
            last_seq = e["seq"]
            events_out.append(e)
            desk.handle(e)
        if desk.need_resync:
            desk.resync(world.snapshot())
            desk.need_resync = False
        desk.tick()
        if desk.now // DAY > day and not quiet:
            try:
                s = world.score()
                print(f"day {day} margin {s['marginCents']/100:10.2f} orders {s['wonOrders']:4d} on-time {s['onTimeShare']:.3f} undelivered {s['undeliveredShare']:.3f}", flush=True)
            except spread.SpreadError:
                pass  # only a progress line
            day = desk.now // DAY


def play_on(world: "spread.World", geo, cfg: Config, level: int, quiet: bool, board: bool) -> tuple:
    """After a break in a practice world: wait, rebuild the desk from the world's record, play to the end.
    The wait doubles from 5 s to 60 s while the world does not move; it gives up after 12 tries in a row
    (about 10 minutes) without progress. Returns (score, desk, events, rebuilds)."""
    delay, fails, rebuilds, best_now = 5.0, 0, 0, -1
    while True:
        print(f"rebuilding from the world's record in {delay:.0f} s", flush=True)
        time.sleep(delay)
        desk = None
        try:
            events = world.events()
            snap = world.snapshot()
            desk = Desk(geo, cfg, level, snap["now"], world.roster())
            rejoin(desk, snap, events)
            rebuilds += 1
            play_practice(world, desk, snap["endsAt"], events, quiet=quiet, after=events[-1]["seq"] if events else -1)
            return world.score(), desk, events, rebuilds
        except KeyboardInterrupt:
            raise
        except Exception as e:
            traceback.print_exc()
            if not (board or transient(e)):
                raise
            moved = desk is not None and desk.now > best_now
            best_now = max(best_now, desk.now if desk is not None else -1)
            fails = 0 if moved else fails + 1
            delay = 5.0 if moved else min(60.0, 2 * delay)
            if fails >= 12:
                raise


def register(world_id: str, **info) -> None:
    os.makedirs("data", exist_ok=True)
    with open(REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"worldId": world_id, "t": time.time(), **info}) + "\n")


def practice(args) -> int:
    cfg = Config.parse(args.set or [])
    client = spread.Client()
    geo = load_geo(client)
    # The team's 8 practice slots are shared: wait for one instead of failing (409). Wait out a network break
    # too, but never for a ranking run: a lost answer may have started it, and a second create would wait on it.
    for attempt in range(180):
        if not args.board:
            wait_blackout()
        try:
            world = client.create(args.level, board=True) if args.board else client.create(args.level, seed=args.seed)
            break
        except spread.SpreadError as e:
            if attempt == 179 or not (e.status == 409 or (transient(e) and not args.board)):
                raise
            if e.status != 409:
                print(f"create: {e}; again in 20 s (if the lost answer made a world, client.worlds() lists it)", flush=True)
            time.sleep(20)
    if args.board:
        args.seed = f"board-{world.id}"
        print(f"ranking run {world.id} (never delete it: it would play out without us and still count)", flush=True)
    register(world.id, seed=args.seed, level=args.level, tag=args.tag, board=bool(args.board))
    out = os.path.join("data", "runs", args.tag, f"{args.seed}-L{args.level}")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    events: list = []
    rebuilds = 0
    try:
        snap = patient(world.snapshot)
        desk = Desk(geo, cfg, args.level, snap["now"], patient(world.roster))
        play_practice(world, desk, snap["endsAt"], events, quiet=args.quiet)
        score = patient(world.score)
    except BaseException as first_error:
        traceback.print_exc()
        stopped = isinstance(first_error, KeyboardInterrupt)
        try:
            if stopped or not (args.board or transient(first_error)):
                raise first_error
            # A ranking run must finish with us, and a network break must not cost a sweep its seed:
            # rebuild from the world's record and play on.
            score, desk, events, rebuilds = play_on(world, geo, cfg, args.level, args.quiet, bool(args.board))
        except BaseException as e:
            if e is not first_error:
                traceback.print_exc()
            if not args.board:
                try:
                    world.delete()
                except Exception:
                    pass
            return 130 if stopped or isinstance(e, KeyboardInterrupt) else 1
    summary = {"seed": args.seed, "level": args.level, "tag": args.tag, "world": world.id, "score": score, "rebuilds": rebuilds,
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
            json.dump({"reveal": patient(world.reveal), "events": events, "roster": list(desk.roster.values()),
                       "gigs": patient(world.snapshot)["gigs"]}, f)
    print(f"END {args.tag} {args.seed} L{args.level} margin {score['marginCents']/100:.2f} orders {score['wonOrders']} on-time {score['onTimeShare']:.3f} "
          f"undelivered {score['undeliveredShare']:.3f} ranked {score['ranked']} ({summary['seconds']}s)"
          + (f" rebuilt {rebuilds}x" if rebuilds else ""), flush=True)
    return 0


# ---------------------------------------------------------------------- final
def rejoin(desk: Desk, snapshot: dict, history: list) -> None:
    """Rebuilds the desk from the world's own record: replay events for the books, take gigs and
    orders from the snapshot, then answer what is missing (open requests, orders without a gig).
    Safe to repeat: the snapshot's live gigs decide which cars are posted, so no car is posted twice."""
    from .desk import GigRec
    gigs = sorted(snapshot["gigs"], key=lambda g: g["postedAt"])
    entered = 0

    def enter(upto: int) -> None:
        # Our gigs enter the replay at the minute they were posted, open, and their events move them on.
        # (All at once, the replay would pair a car with a gig from its future and drop it from a hold pool.)
        nonlocal entered
        while entered < len(gigs) and gigs[entered]["postedAt"] <= upto:
            g = gigs[entered]
            entered += 1
            rec = GigRec(g["id"], g["stops"], g["audience"], g["schedule"], g["postedAt"])
            for key in rec.legs:
                old = desk.gigs.get(desk.leg_gig.get(key, ""))
                if old is not None and old.status == "open":
                    old.status = "withdrawn"  # a car is in one live gig at a time: this one replaced it
                desk.leg_gig[key] = rec.id
            desk.gigs[rec.id] = rec

    # Replay each event at its own minute, as the first life handled it, so the chances, holds and retry
    # times computed then come out the same. (A Desk is built at the snapshot's minute: set it back first.)
    desk.now = history[0]["at"] if history else snapshot["now"]
    for e in history:
        desk.now = max(desk.now, e["at"])
        enter(desk.now)
        desk.handle(e)
    enter(10**9)
    desk.outbox.clear()
    desk.pending_posts.clear()
    desk.now = snapshot["now"]
    desk.leg_gig.clear()
    for g in snapshot["gigs"]:
        rec = desk.gigs[g["id"]]
        rec.status, rec.driver, rec.schedule, rec.fee = g["status"], g.get("driverId"), g["schedule"], g.get("feeCents", rec.fee)
        if g["status"] in ("open", "booked", "working"):
            for key in rec.legs:
                desk.leg_gig[key] = rec.id
    for o in snapshot["orders"]:
        if o["id"] in desk.orders:
            if o["status"] == "cancelled":
                desk.orders.pop(o["id"])
            else:
                desk.orders[o["id"]].order = o
    settle(desk, snapshot, history)
    for r in snapshot["openRequests"]:
        desk.handle({"kind": "price_request", "at": desk.now, "request": r, "seq": -1})
    desk.tick()


def settle(desk: Desk, snapshot: dict, history: list) -> None:
    """What the replay cannot know (it runs no tick and gets no gig ids), taken from the world's record."""
    try:
        # Hold pools (evening release; the chain planner's pool on claude/best): a car in any gig of the
        # snapshot was released before the break, and a delivered car has nothing to hold. Keep the rest.
        posted = {s["orderId"] for g in snapshot["gigs"] for s in g["stops"]}
        for name in ("held", "chain_held"):
            pool = getattr(desk, name, None)
            if isinstance(pool, dict):
                for oid in [o for o in pool if o in posted or not desk.undelivered(o)]:
                    del pool[oid]
    except Exception as exc:
        desk.say("ERR", f"rejoin held {type(exc).__name__}: {exc}")
    try:
        # Pairs posted by the release (in tick) lost their unbundle timer, and without it tick splits every
        # open pair at once. Give each open multi-car gig the last start that desk.chain computes for it.
        for g in snapshot["gigs"]:
            oids = list(dict.fromkeys(s["orderId"] for s in g["stops"]))
            if g["status"] == "open" and len(oids) > 1 and all(o in desk.orders for o in oids):
                last = chain_last(desk, [desk.orders[o] for o in oids])
                for o in oids:
                    desk.bundle_last[o] = last
    except Exception as exc:
        desk.say("ERR", f"rejoin bundles {type(exc).__name__}: {exc}")
    try:
        # Direct offers sent by tick are not replayed: their answers still say who was asked, and each one
        # counts against the driver's three a day (RULES: at most three direct offers per driver per day).
        for e in history:
            if e["kind"] == "offer_answered" and (e["gigId"], e["driverId"]) not in desk.offered:
                desk.offered.add((e["gigId"], e["driverId"]))
                desk.offers_today[(e["driverId"], e["at"] // DAY)] += 1
    except Exception as exc:
        desk.say("ERR", f"rejoin offers {type(exc).__name__}: {exc}")


def chain_last(desk: Desk, obs: list) -> int:
    """The last minute to start a chain gig (one driver takes these one-car orders in this order), as
    desk.chain computes it for two: min(last pickup of A, last pickup of B - drive A - transfer)."""
    last, lead, prev = None, 0, None
    for ob in obs:
        L = ob.order["legs"][0]
        if prev is not None:
            lead += desk.geo.drive(prev["pickup"]["placeId"], prev["delivery"]["placeId"]) + desk.geo.drive(prev["delivery"]["placeId"], L["pickup"]["placeId"])
        x = desk.last_pickup(ob, [0]) - lead
        last = x if last is None else min(last, x)
        prev = L
    return last


def keep_awake() -> None:
    """Windows: no idle sleep while this process runs (ES_CONTINUOUS | ES_SYSTEM_REQUIRED). A closed lid or
    the power button still sleeps the laptop (RUNBOOK.md)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass


def final(args) -> int:
    cfg = Config.parse(args.set or [])
    keep_awake()
    try:
        client = spread.Client()
    except spread.SpreadError as e:
        print(f"cannot start: {e}", file=sys.stderr, flush=True)
        return 2
    geo = load_geo(client)
    os.makedirs("data", exist_ok=True)
    logf = open(os.path.join("data", f"final-{int(time.time())}.log"), "a", encoding="utf-8")
    print("overrides:", " ".join(args.set or []) or "(none: Config defaults)", flush=True)
    world = None
    while world is None:
        try:
            world = wait_final(client)
        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            time.sleep(5)
    print("final world", world.id, flush=True)
    supervise(world, client, geo, cfg, logf, lambda: client.final()["now"])
    try:
        print("final score", world.score(), flush=True)
    except Exception as e:
        print("the world ended; score not read:", e, flush=True)
    return 0


def supervise(world, client, geo, cfg: Config, logf, clock) -> None:
    """Plays a live world to its end. Every break is answered the same way: wait (5 s after a network
    break, as the kit's starter does; 2 s after a bug), rebuild from the world's record, go on."""
    while True:
        try:
            if run_live(world, client, geo, cfg, logf, clock):
                return
        except KeyboardInterrupt:
            raise
        except spread.SpreadError as e:
            if not transient(e):
                traceback.print_exc()
            print(f"break: {e} - rebuilding in 5 s", flush=True)
            time.sleep(5)
        except Exception:
            traceback.print_exc()
            print("bug in the live loop - rebuilding in 2 s", flush=True)
            time.sleep(2)


def wait_final(client) -> "spread.World":
    said = False
    while True:
        try:
            f = client.final()
            w = client.world(f["worldId"])
            s = w.snapshot()
            if s["now"] < s["endsAt"]:
                print(f"final {f['worldId']} starts at {f.get('startsAt')} (world minute {s['now']})", flush=True)
                return w
        except spread.SpreadError as e:
            if e.status not in (404, 0) and not transient(e):
                raise
        if not said:
            print("waiting for a final to be set ...", flush=True)
            said = True
        time.sleep(5)


def run_live(world, client, geo, cfg: Config, logf, clock) -> bool:
    """The live loop: rebuild from the world's record, then answer events from the stream until the world
    ends (returns True). `clock()` gives the world minute when no event comes (client.final() in the
    final). A break raises, and the caller rebuilds."""
    said = False
    while True:
        history = world.events()
        snapshot = world.snapshot()
        if snapshot["now"] >= snapshot["endsAt"]:
            return True
        roster = world.roster()
        if roster:
            break
        # A world that has not started may list no drivers yet; a desk built without them stays blind all week.
        if not said:
            print("the world lists no drivers yet; asking every 5 s", flush=True)
            said = True
        time.sleep(5)
    ends = snapshot["endsAt"]
    try:
        level = next((w["level"] for w in client.worlds() if w["worldId"] == world.id), 8)
    except spread.SpreadError:
        level = 8  # the final is level 8; the list costs a practice token and may fail on its own
    desk = Desk(geo, cfg, level, snapshot["now"], roster)
    rejoin(desk, snapshot, history)
    print(f"rebuilt at minute {desk.now}: {len(history)} events, {len(desk.orders)} orders, {len(desk.held)} held, "
          f"{len(snapshot['openRequests'])} open requests, {len(desk.outbox)} actions to send", flush=True)
    flush(world, desk, logf)
    last_seq = history[-1]["seq"] if history else -1
    day = desk.now // DAY
    t = time.time()
    last_tick = last_flush = last_event = last_clock = last_sync = last_heard = last_probe = t
    while True:
        stream = world.stream(after=last_seq, idle=0.25)
        reopen = False
        try:
            for e in stream:
                t = time.time()
                fresh = [] if e is None else [e]
                if e is not None:
                    last_heard = t
                elif t - last_heard > PROBE and t - last_probe > PROBE:
                    # The kit cannot tell a quiet stream from a dead connection (a laptop that slept, a Wi-Fi
                    # switch): ask GET /events for anything after our last event (one read token).
                    last_probe = t
                    fresh = missed(world, last_seq)
                    reopen = bool(fresh)
                for x in fresh:
                    if x["seq"] <= last_seq:  # repeated events (a reconnect, a probe) are dropped by seq
                        continue
                    last_seq = x["seq"]
                    desk.now = max(desk.now, x["at"])
                    desk.handle(x)
                    last_event = t
                if (not fresh and t - last_event > 2.0) or t - last_clock > 5.0:
                    desk.now = max(desk.now, read_clock(clock, desk.now))  # when the stream is quiet, and every 5 s (one read token)
                    last_event = last_clock = t
                if t - last_tick > 2.0:
                    if desk.need_resync or t - last_sync > 60.0:
                        try:
                            desk.resync(world.snapshot())  # one read a minute keeps our books equal to the world's
                            desk.need_resync = False
                        except spread.SpreadError:
                            pass  # next tick (need_resync) or next minute
                        last_sync = t
                    desk.tick()
                    last_tick = t
                # Batch: one actions call per 0.3 s at most, or at once when the stream is quiet. A price
                # request has 4.5 real seconds, so a short wait costs nothing and saves the action bucket.
                if desk.outbox and (e is None or t - last_flush > 0.3):
                    flush(world, desk, logf)
                    last_flush = time.time()
                elif desk.log and t - last_flush > 1.0:
                    flush(world, desk, logf)
                if desk.now // DAY > day:
                    day = desk.now // DAY
                    try:
                        s = world.score()
                        print(f"day {day} minute {desk.now} margin {s['marginCents']/100:.2f} orders {s['wonOrders']} on-time {s['onTimeShare']:.3f}", flush=True)
                    except spread.SpreadError:
                        pass  # only a progress line
                if desk.now >= ends:
                    flush(world, desk, logf)
                    return True
                if reopen:
                    print(f"the stream was silent but events were waiting: reconnecting after seq {last_seq}", flush=True)
                    break
            else:
                # The server closed the stream for good (code 1000). Only the end of the world stops the bot.
                if ended(world):
                    flush(world, desk, logf)
                    return True
                print("the stream closed before the end; reconnecting", flush=True)
                time.sleep(1)
        finally:
            stream.close()


def missed(world, after: int) -> list:
    try:
        return world.events(after=after)
    except spread.SpreadError:
        return []  # the stream and the next actions call will show whether the server is there


def read_clock(clock, now: int) -> int:
    try:
        return clock()
    except spread.SpreadError:
        return now  # the clock only moves us between events; the next read will do


def ended(world) -> bool:
    try:
        s = world.snapshot()
        return s["now"] >= s["endsAt"]
    except spread.SpreadError:
        return False


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
    # Our own batches of 50: results of a batch that went through are read even when a later batch breaks.
    for i in range(0, len(actions), BATCH):
        batch = actions[i:i + BATCH]
        results = send(world, desk, batch)
        try:
            desk.read_results(batch, results)
        except Exception as exc:
            desk.say("ERR", f"read_results {type(exc).__name__}: {exc}")
            desk.need_resync = True  # the snapshot tells which posts became gigs


def send(world, desk: Desk, batch: list) -> list:
    """One actions call. When the server (400) or the client's whole-number check cannot parse the batch,
    only the action it names is dropped (a DROPPED line, an ok=false result) and the rest go again, so one
    malformed post never blocks the quotes in its batch. Breaks (network, 5xx) are raised."""
    results: list = [None] * len(batch)
    todo = list(range(len(batch)))
    while todo:
        try:
            got = world.act([batch[j] for j in todo])
        except spread.SpreadError as e:
            if transient(e) or e.status not in (0, 400):
                raise
            m = re.match(r"\[(\d+)\]", e.field or "")
            k = int(m.group(1)) if m else -1
            if not 0 <= k < len(todo):
                if len(todo) > 1:  # no index: one at a time finds the bad ones
                    for j in todo:
                        results[j] = send(world, desk, [batch[j]])[0]
                    return results
                k = 0
            bad = todo.pop(k)
            results[bad] = {"ok": False, "reason": f"dropped by the client: {e}"}
            desk.say("DROPPED", f"{batch[bad]['type']} {str(e)[:160]}")
            continue
        for j, res in zip(todo, got):
            results[j] = res
        todo = []
    return results


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
    ap.add_argument("--board", action="store_true", help="play the team's next ranking run (humans only)")
    ap.add_argument("--preset", default="", help="named overrides from presets.py, e.g. money")
    args = ap.parse_args()
    if args.preset:
        from .presets import PRESETS
        if args.preset not in PRESETS:
            print(f"unknown preset {args.preset!r}; this branch has: {', '.join(sorted(PRESETS))}", file=sys.stderr)
            return 2
        args.set = PRESETS[args.preset] + (args.set or [])
    try:
        Config.parse(args.set or [])
    except Exception as e:
        print(f"bad --set or preset: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    try:
        return practice(args) if args.mode == "practice" else final(args)
    except KeyboardInterrupt:
        print("stopped by hand", flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
