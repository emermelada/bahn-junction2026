"""A world played back from a recorded week, for offline tests of the live path. No network.

The recorded events are the world's facts; they do not react to our actions. What the world says about
OUR gigs is rebuilt from them (status at minute T), and the gigs we post here are added on top, so a
second rebuild sees what the first one posted. Faults are injected per method: `world.fail["act"] =
[spread.Unreachable(0, "x")]` raises once on the next act().
"""
from __future__ import annotations

import copy
import gzip
import json
import os
import time
from typing import Any, Iterator, Optional

import spread
from spread.client import check_whole

from spreadbot.geo import DAY, HOUR, Geo

HERE = os.path.dirname(__file__)
ENDS = 9 * DAY + 22 * HOUR  # Wednesday 22:00 of the second week


def load_week() -> dict:
    with gzip.open(os.path.join(HERE, "fixtures", "week-dev31.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def load_map() -> Geo:
    for p in (os.path.join(HERE, "..", "..", "data", "map.json"), os.path.join(HERE, "..", "..", "..", "v1-evening", "data", "map.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return Geo(json.load(f))
    raise FileNotFoundError("data/map.json: copy it from v1-evening/data")


class FakeClock:
    """Stands in for the `time` module inside spreadbot.run: sleeps and stream waits move it, nothing blocks."""

    def __init__(self) -> None:
        self.t = 1_000_000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s

    def localtime(self) -> "time.struct_time":
        return time.struct_time((2026, 11, 14, 10, 0, 0, 5, 318, 0))  # laptop 10:00: outside the test-final blackouts


class FakeWorld:
    def __init__(self, week: dict, now: int, ends: int = ENDS, clock: Optional[FakeClock] = None):
        self.week, self.now, self.ends, self.clock = week, now, ends, clock or FakeClock()
        # The recording's own gigs exist up to the minute we take over; after it, only our posts do.
        self.start = now
        self.id = "fake-world"
        self.events_all: list[dict] = week["events"]
        self.own: dict[str, dict] = {}  # gigs we posted here
        self.override: dict[str, str] = {}  # recorded gig -> status after our withdraw
        self.acts: list[dict] = []  # every action that reached the world, in order
        self.calls: list[int] = []  # size of each act() call
        self.fail: dict[str, list[BaseException]] = {}
        self.reject = None  # fn(action) -> True: the server answers 400 naming that action
        self.reject_indexed = True  # False: the 400 names no action
        self.dead_after: Optional[int] = None  # the stream goes silent (no error) after this many events
        self.dup = False  # the stream sends each event twice
        self.minutes_per_idle = 1  # world minutes that pass for each idle yield once the recording is used up
        self.streams = 0

    # ------------------------------------------------------------------ faults
    def _maybe_fail(self, method: str) -> None:
        q = self.fail.get(method)
        if q:
            raise q.pop(0)

    # ------------------------------------------------------------------ reads
    def events(self, after: int = -1, limit: Optional[int] = None) -> list[dict]:
        self._maybe_fail("events")
        return copy.deepcopy([e for e in self.events_all if e["seq"] > after and e["at"] <= self.now])

    def roster(self) -> list[dict]:
        self._maybe_fail("roster")
        return copy.deepcopy(self.week["roster"])

    def score(self) -> dict:
        self._maybe_fail("score")
        return {"marginCents": 0, "revenueCents": 0, "marginShare": 0.0, "wonOrders": 0, "onTimeShare": 1.0, "undeliveredShare": 0.0, "ranked": True}

    def snapshot(self) -> dict:
        self._maybe_fail("snapshot")
        T = self.now
        evs = [e for e in self.events_all if e["at"] <= T]
        orders: dict[str, dict] = {}
        delivered: dict[tuple, int] = {}
        failed: set = set()
        resolved: set = set()
        for e in evs:
            k = e["kind"]
            if k in ("order_won", "order_changed"):
                o = copy.deepcopy(e["order"])
                o["deliveredAt"] = [delivered.get((o["id"], i)) for i in range(len(o["legs"]))]
                if o["id"] in orders and orders[o["id"]]["status"] == "cancelled":
                    o["status"] = "cancelled"
                orders[o["id"]] = o
            if k in ("order_won", "order_lost"):
                resolved.add(e["order"]["id"] if k == "order_won" else e["requestId"])
            elif k == "delivered":
                delivered[(e["orderId"], e["leg"])] = e["at"]
                if e["orderId"] in orders:
                    orders[e["orderId"]]["deliveredAt"][e["leg"]] = e["at"]
            elif k == "visit_failed":
                failed.add((e["gigId"], e["orderId"], e["leg"]))
            elif k == "deadline_close" and e["orderId"] in orders:
                orders[e["orderId"]]["lastPickupAt"] = e["lastPickupAt"]
            elif k == "order_cancelled" and e["orderId"] in orders:
                orders[e["orderId"]]["status"] = "cancelled"
        for o in orders.values():
            if o["status"] != "cancelled" and all(t is not None for t in o["deliveredAt"]):
                o["status"] = "delivered"
        gigs = self._gig_states(evs, delivered, failed)
        open_requests = [copy.deepcopy(e["request"]) for e in evs if e["kind"] == "price_request"
                         and e["request"]["respondBy"] > T and e["request"]["id"] not in resolved]
        return {"worldId": self.id, "now": T, "endsAt": self.ends, "openRequests": open_requests, "orders": list(orders.values()),
                "gigs": gigs, "driverPositions": [], "score": self.score()}

    def _gig_states(self, evs: list, delivered: dict, failed: set) -> list[dict]:
        T = self.now
        rec = {g["id"]: copy.deepcopy(g) for g in self.week["gigs"] if g["postedAt"] <= min(T, self.start)}
        for g in rec.values():
            g["status"], g["driverId"] = "open", None
        for e in evs:
            g = rec.get(e.get("gigId"))
            if g is None:
                continue
            k = e["kind"]
            if k == "gig_booked" or (k == "offer_answered" and e.get("answer") == "accepted"):
                g["status"], g["driverId"] = "booked", e["driverId"]
            elif k == "gig_started":
                g["status"] = "working"
            elif k in ("gig_dropped", "no_show"):
                g["status"], g["driverId"] = "open", None
            elif k == "gig_expired":
                g["status"] = "withdrawn"
        for e in evs:
            if e["kind"] == "order_cancelled":
                for x in e.get("gigs", []):
                    if x["gigId"] in rec and x["outcome"] in ("withdrawn", "released"):
                        rec[x["gigId"]]["status"] = "withdrawn"
        for g in rec.values():
            legs = [(s["orderId"], s["leg"]) for s in g["stops"] if s["kind"] == "pickup"]
            if all(l in delivered or (g["id"],) + l in failed for l in legs) and g["status"] != "withdrawn":
                g["status"] = "done"
        # A gig withdrawn by our own action leaves no event: a later gig for the same car replaced it.
        latest: dict[tuple, str] = {}
        for g in sorted(rec.values(), key=lambda g: (g["postedAt"], int(g["id"][1:]))):
            for s in g["stops"]:
                if s["kind"] == "pickup":
                    prev = latest.get((s["orderId"], s["leg"]))
                    if prev and rec[prev]["status"] in ("open", "booked"):
                        rec[prev]["status"] = "withdrawn"
                    latest[(s["orderId"], s["leg"])] = g["id"]
        for gid, st in self.override.items():
            if gid in rec:
                rec[gid]["status"] = st
        return list(rec.values()) + [copy.deepcopy(g) for g in self.own.values()]

    # ------------------------------------------------------------------ actions
    def act(self, actions: list[dict]) -> list[dict]:
        self._maybe_fail("act")
        check_whole(actions)  # the real client refuses a fraction before it sends
        for i, a in enumerate(actions):
            if self.reject and self.reject(a):
                raise spread.SpreadError(400, "does not parse", f"[{i}].type" if self.reject_indexed else None)
        self.calls.append(len(actions))
        out = []
        for a in actions:
            self.acts.append(a)
            t = a["type"]
            if t == "post":
                gid = f"x{len(self.own) + 1}"
                self.own[gid] = {"id": gid, "stops": a["stops"], "audience": a["audience"], "schedule": a["schedule"], "status": "open",
                                 "postedAt": self.now, "feeCents": a["schedule"][0]["feeCents"], "driverId": None}
                out.append({"ok": True, "id": gid})
            elif t in ("withdraw", "reprice"):
                g = self.own.get(a["gigId"])
                if g is None:
                    live = {x["id"]: x for x in self._gig_states([e for e in self.events_all if e["at"] <= self.now], {}, set())}
                    g = live.get(a["gigId"])
                if g is None or g["status"] != "open":
                    out.append({"ok": False, "reason": f"Gig {a['gigId']} is not open"})
                    continue
                if t == "withdraw":
                    if a["gigId"] in self.own:
                        self.own[a["gigId"]]["status"] = "withdrawn"
                    else:
                        self.override[a["gigId"]] = "withdrawn"
                elif a["gigId"] in self.own:
                    self.own[a["gigId"]]["schedule"] = a["schedule"]
                out.append({"ok": True})
            else:
                out.append({"ok": True})
        return out

    # ------------------------------------------------------------------ stream
    def stream(self, after: Optional[int] = None, idle: Optional[float] = None) -> Iterator[Optional[dict]]:
        """Plays the recording on from `after`, moving the world clock with it. When the recording is used
        up, idle yields move the clock on to the end. With `dead_after`, the connection dies quietly."""
        self._maybe_fail("stream")
        self.streams += 1
        last = -1 if after is None else after
        sent = 0
        while True:
            nxt = next((e for e in self.events_all if e["seq"] > last), None)
            if nxt is not None and nxt["at"] > self.ends:
                nxt = None
            if self.dead_after is not None and sent >= self.dead_after:
                # Silent: the world goes on, the socket says nothing.
                self.clock.t += idle or 0.25
                if nxt is not None:
                    self.now = max(self.now, nxt["at"])
                    last = nxt["seq"]
                else:
                    self.now = min(self.ends, self.now + self.minutes_per_idle)
                yield None
                continue
            if nxt is None:
                self.clock.t += idle or 0.25
                self.now = min(self.ends, self.now + self.minutes_per_idle)
                yield None
                continue
            last = nxt["seq"]
            self.now = max(self.now, nxt["at"])
            self.clock.t += 0.02
            sent += 1
            yield copy.deepcopy(nxt)
            if self.dup:
                yield copy.deepcopy(nxt)


def legs_of(a: dict) -> list[tuple]:
    return [(s["orderId"], s["leg"]) for s in a["stops"] if s["kind"] == "pickup"]


def live_legs(snapshot: dict) -> dict[tuple, str]:
    out = {}
    for g in snapshot["gigs"]:
        if g["status"] in ("open", "booked", "working"):
            for s in g["stops"]:
                if s["kind"] == "pickup":
                    out[(s["orderId"], s["leg"])] = g["id"]
    return out


class FakePractice(FakeWorld):
    """A practice world: `advance` moves the clock through the recording. `lose[n]` makes the n-th advance
    happen on the server but lose its answer (Unreachable), as on a DNS drop mid-request."""

    def __init__(self, week: dict, now: int, ends: int, clock: Optional[FakeClock] = None):
        super().__init__(week, now, ends, clock)
        self.adv_seq = -1
        self.advances = 0
        self.lose: set[int] = set()
        self.deleted = False

    def advance(self, to=None, by=None, until=None, max=None, actions=()):
        self._maybe_fail("advance")
        self.advances += 1
        results = self.act(list(actions)) if actions else []
        if until is not None:
            nxt = next((e for e in self.events_all if e["at"] > self.now and e["kind"] in until and e["at"] <= max), None)
            target = nxt["at"] if nxt else max
        else:
            target = to if to is not None else self.now + by
        target = min(target, self.ends)
        evs = [e for e in self.events_all if e["seq"] > self.adv_seq and e["at"] <= target]
        if evs:
            self.adv_seq = evs[-1]["seq"]
        self.now = target
        if self.advances in self.lose:
            raise spread.Unreachable(0, "Cannot reach the server: [Errno 11001] getaddrinfo failed")
        return {"now": target, "events": copy.deepcopy(evs), "results": results}

    def delete(self) -> None:
        self.deleted = True

    def reveal(self) -> dict:
        return {}


class FakeClient:
    def __init__(self, world: FakeWorld):
        self.w = world

    def worlds(self) -> list[dict]:
        return [{"worldId": self.w.id, "level": 8}]

    def create(self, level: int = 8, seed: Any = None, board: bool = False) -> FakeWorld:
        return self.w

    def world(self, world_id: str) -> FakeWorld:
        return self.w

    def map(self) -> dict:
        raise AssertionError("tests load the map from data/map.json")
