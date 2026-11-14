"""V2 capacity-first planner: plan the week's driver-hours first, then price and dispatch against the plan.

Why: on the board c3 wins 264-379 orders a run, the top ten 400-530 at 95-98% on time and EUR 35-42 an order. The lever is
cars moved on time, so admission is a question of driver-hours per region and day, not of gate risk. Target: ~450 orders at
P(on time) >= 0.95, every car on a planned driver-day.

======================================================================================================================
FROZEN INTERFACES (Sat 14 Nov, 11:30 laptop). a3 builds Supply in src/spreadbot/supply.py, a4 builds Fees in
src/spreadbot/fees.py, each against these signatures; a1 integrates. The stubs at the bottom of this file keep the planner
running until they land (same signatures, prior-only numbers), and are replaced by importing the real class.

Time: world minutes (DAY = 1440, day index = minute // DAY, Mon = 0). Hours are floats. Money is cents unless stated.

Supply (a3)  ----------------------------------------------------------------------------------------------------------
    class Supply:
        def __init__(self, desk: "Desk") -> None
            desk.roster (driver id -> {homePlaceId, licence, rating, ...}), desk.geo, desk.cfg are available.
        def regions(self) -> list[str]
            All region ids, sorted, fixed for the world (built from the map once).
        def region(self, place: str) -> str
            The region of a place. Every place id of the map has one.
        def hours(self, region: str, day: int) -> float
            Expected driver-hours available FOR OUR GIGS in this region on this day index: drivers who work that day, live
            or end a gig there, times the hours each gives us, less what snow takes away. Prior from ~250 played weeks,
            updated by this week's views, bookings, drops, starts and finishes. Must be >= 0 and deterministic.
        def on_event(self, e: dict) -> None
            Fold any world event (gig_viewed, gig_booked, gig_dropped, gig_started, delivered, forecast, ...). Called by
            Desk.handle before its own handlers. Rebuilds from snapshot + replayed events; no wall clock, no randomness.

Fees (a4)  ------------------------------------------------------------------------------------------------------------
    class Fees:
        def __init__(self, desk: "Desk") -> None
        def clearing(self, region: str, day: int, hour: int, drive: int, n_cars: int) -> float
            The fee (cents, for the whole gig) at which a gig starting in `region` on day index `day` at `hour` (0-23),
            with `drive` minutes of driving over `n_cars` cars, books with high probability (about 0.8 within an hour)
            when posted the day before. A flat fee: no raise ladder. Prior from the reveals, updated by on_event.
        def on_event(self, e: dict) -> None
            Same contract as Supply.on_event.

Planner (a1, this file)  ----------------------------------------------------------------------------------------------
    class Planner:
        def __init__(self, desk: "Desk", supply: Supply, fees: Fees) -> None
        def replan(self, now: int) -> None
            Runs once per world hour (Desk.tick calls it; cheap enough to call more often). Assigns every undelivered won
            car without a live gig to a driver-day and a chain (1-3 cars, <= 12 h of driving + transfers, pickup windows,
            site hours and deadlines respected), adds the expected future wins per (region, day), and sets lam.
        def lam(self, region: str, day: int) -> float
            Shadow price of one driver-hour in this region on this day, EUR (float, not cents): ~0 while the day has idle
            hours, rising steeply as the planned hours approach Supply.hours(region, day). Pricing charges
            lam(region, planned day) x hours of the car; dispatch does not use it.
        def planned_day(self, r: dict, deadline: int) -> int
            The day the planner would move a request's car on, given the option's deadline: the latest feasible day with
            the lowest lam (ties -> latest). Used by Desk.price for the lam charge.
        def chain_for(self, oid: str) -> list[tuple[str, int]]
            The planned chain containing this order's legs, as [(order id, leg), ...] in driving order, or [] when the car
            is not planned (then dispatch posts it alone as c3 does). Chains are posted at release time (the evening
            before the planned day, cfg.hold_hour) at Fees.clearing(...), flat.
        def hours_of(self, r_or_o: dict) -> float
            Driver-hours one car costs: driving minutes of its legs + handling (v2_handling_min per leg), in hours.
        def state(self) -> dict
            For the log: planned hours and lam per (region, day), chains, unplanned cars.
    Determinism: the plan is a function of desk state at `now` only; the same events give the same plan. The planner keeps
    no state that cannot be rebuilt (replan() recomputes everything from desk.orders / gigs / requests).
======================================================================================================================

The plan (what replan does, in order):
1. Committed hours: booked/working gigs stay where they are; their hours count on their planned day and region.
2. Open cars (won, no booked gig): for each car the feasible days are from its ready day to the day a pickup still makes
   the deadline. It goes to the feasible day with the lowest utilisation (ties -> the latest day, nearest the deadline:
   drivers book the day before, and later pickups wait for the evening release and can pair).
3. Chains: per (region, day), cars sorted by last pickup; a car joins the chain whose last delivery is nearest its pickup
   when the transfer keeps the chain under v2_chain_hours and every car still makes its deadline; else it opens a chain.
4. Expected future wins: this week's request rate per pickup region (prior + online) x our recent win share x hours per
   car, for the request hours still to come whose cars would land on that day.
5. lam(region, day) = v2_lam_eur x max(0, u - v2_lam_free) / max(0.05, 1 - u), u = planned hours / Supply.hours.
   A queue-style price: free while idle, steep near full. Capped at v2_lam_max.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

from .geo import DAY, HOUR

if TYPE_CHECKING:
    from .desk import Desk


class Planner:
    def __init__(self, desk: "Desk", supply, fees) -> None:
        self.desk, self.cfg = desk, desk.cfg
        self.supply, self.fees = supply, fees
        self.hours_planned: dict[tuple[str, int], float] = defaultdict(float)  # (region, day) -> hours, known cars
        self.hours_future: dict[tuple[str, int], float] = defaultdict(float)   # (region, day) -> hours, expected wins
        self.chains: dict[str, list[tuple[str, int]]] = {}                      # chain id -> [(oid, leg)]
        self.chain_of: dict[str, str] = {}                                      # oid -> chain id
        self.day_of: dict[str, int] = {}                                        # oid -> planned day
        self.unplanned: list[str] = []
        self.last_replan = -1
        self.req_count: dict[tuple[str, int], int] = defaultdict(int)           # (region, day) -> requests seen
        self.n_req = 0

    # ------------------------------------------------------------------ public API
    def lam(self, region: str, day: int) -> float:
        cfg = self.cfg
        cap = max(1.0, self.supply.hours(region, day))
        u = (self.hours_planned[(region, day)] + self.hours_future[(region, day)]) / cap
        if u <= cfg.v2_lam_free:
            return 0.0
        return min(cfg.v2_lam_max, cfg.v2_lam_eur * (u - cfg.v2_lam_free) / max(0.05, 1.0 - u))

    def hours_of(self, x: dict) -> float:
        geo = self.desk.geo
        drive = sum(geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in x["legs"])
        return (drive + self.cfg.v2_handling_min * len(x["legs"])) / 60.0

    def feasible_days(self, legs: list[dict], ready: int, deadline: int) -> list[int]:
        """Day indexes on which a pickup can start and still deliver by the deadline."""
        drive = sum(self.desk.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in legs)
        first = max(ready, legs[0]["pickup"]["window"]["from"]) // DAY
        last_start = deadline - drive - 20
        last = last_start // DAY
        return [d for d in range(first, last + 1) if d * DAY + 8 * HOUR <= last_start or d == first]

    def planned_day(self, r: dict, deadline: int) -> int:
        days = self.feasible_days(r["legs"], r["respondBy"], deadline)
        region = self.supply.region(r["legs"][0]["pickup"]["placeId"])
        if not days:
            return deadline // DAY
        if len(days) > 1:
            days = days[:-1]
        return min(days, key=lambda d: (round(self.lam(region, d), 0), d))

    def chain_for(self, oid: str) -> list[tuple[str, int]]:
        cid = self.chain_of.get(oid)
        return list(self.chains.get(cid, [])) if cid else []

    def on_request(self, r: dict) -> None:
        self.req_count[(self.supply.region(r["legs"][0]["pickup"]["placeId"]), r["arrivedAt"] // DAY)] += 1
        self.n_req += 1

    def state(self) -> dict:
        keys = sorted(set(self.hours_planned) | set(self.hours_future))
        return {"lam": {f"{r}/{d}": round(self.lam(r, d), 1) for r, d in keys},
                "hours": {f"{r}/{d}": (round(self.hours_planned[(r, d)], 1), round(self.hours_future[(r, d)], 1), round(self.supply.hours(r, d), 1)) for r, d in keys},
                "chains": sum(1 for c in self.chains.values() if len(c) > 1), "unplanned": len(self.unplanned)}

    # ------------------------------------------------------------------ the plan
    def replan(self, now: int) -> None:
        desk, geo, cfg = self.desk, self.desk.geo, self.cfg
        self.last_replan = now
        self.hours_planned = defaultdict(float)
        self.hours_future = defaultdict(float)
        self.chains, self.chain_of, self.day_of, self.unplanned = {}, {}, {}, []
        today = now // DAY
        # 1. committed: booked or working gigs
        committed: set[str] = set()
        for gid in sorted(desk.gigs):
            rec = desk.gigs[gid]
            if rec.status not in ("booked", "working"):
                continue
            for oid, leg in rec.legs:
                committed.add(oid)
                o = desk.orders.get(oid)
                if o is None:
                    continue
                L = o.order["legs"][leg]
                day = max(today, L["pickup"]["window"]["from"] // DAY)
                region = self.supply.region(L["pickup"]["placeId"])
                self.hours_planned[(region, day)] += (geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) + cfg.v2_handling_min) / 60.0
        # 2. open cars -> a day each
        cars = []
        for oid in sorted(desk.orders):
            ob = desk.orders[oid]
            o = ob.order
            if o["status"] == "cancelled" or oid in committed:
                continue
            legs = desk.undelivered(oid)
            if not legs:
                continue
            L = [o["legs"][l] for l in legs]
            ready = max(desk.leg_note(oid, l).ready_at or 0 for l in legs)
            ready = max(ready, now)
            deadline = desk.deadline(o, legs[0])
            days = [d for d in self.feasible_days(L, ready, deadline) if d >= today]
            region = self.supply.region(L[0]["pickup"]["placeId"])
            hours = sum(geo.drive(x["pickup"]["placeId"], x["delivery"]["placeId"]) + cfg.v2_handling_min for x in L) / 60.0
            cars.append((deadline, oid, legs, region, hours, days))
        for deadline, oid, legs, region, hours, days in sorted(cars):
            if not days:
                self.unplanned.append(oid)
                days = [max(today, deadline // DAY)]
            if len(days) > 1:
                days = days[:-1]  # keep a day of slack: a pickup on the deadline day has no room for a drop or a slow site
            cap = {d: max(1.0, self.supply.hours(region, d)) for d in days}
            day = min(days, key=lambda d: (round(self.hours_planned[(region, d)] / cap[d], 1), d))
            self.hours_planned[(region, day)] += hours
            self.day_of[oid] = day
        # 3. chains per (region, day): nearest-end greedy
        groups: dict[tuple[str, int], list[str]] = defaultdict(list)
        for oid, day in self.day_of.items():
            ob = desk.orders[oid]
            if len(ob.order["legs"]) == 1 and desk.simple(ob):
                groups[(self.supply.region(ob.order["legs"][0]["pickup"]["placeId"]), day)].append(oid)
        for key in sorted(groups):
            ends: list[tuple[str, str, int, float]] = []  # (chain id, end place, end minute, hours)
            for oid in sorted(groups[key], key=lambda x: (desk.orders[x].order["lastPickupAt"], x)):
                ob = desk.orders[oid]
                L = ob.order["legs"][0]
                p, d = L["pickup"]["placeId"], L["delivery"]["placeId"]
                drive = geo.drive(p, d)
                best: Optional[int] = None
                for i, (cid, end_place, end_at, hrs) in enumerate(ends):
                    if len(self.chains[cid]) >= cfg.v2_chain_cars:
                        continue
                    tr = geo.drive(end_place, p)
                    start = max(end_at + tr, L["pickup"]["window"]["from"])
                    if hrs + (tr + drive + cfg.v2_handling_min) / 60.0 > cfg.v2_chain_hours or start > desk.last_pickup(ob, [0]):
                        continue
                    if best is None or tr < geo.drive(ends[best][1], p):
                        best = i
                if best is None:
                    cid = "c" + oid
                    self.chains[cid] = [(oid, 0)]
                    start = max(L["pickup"]["window"]["from"], key[1] * DAY + 8 * HOUR)
                    ends.append((cid, d, start + drive + cfg.v2_handling_min, (drive + cfg.v2_handling_min) / 60.0))
                else:
                    cid, end_place, end_at, hrs = ends[best]
                    self.chains[cid].append((oid, 0))
                    tr = geo.drive(end_place, p)
                    start = max(end_at + tr, L["pickup"]["window"]["from"])
                    ends[best] = (cid, d, start + drive + cfg.v2_handling_min, hrs + (tr + drive + cfg.v2_handling_min) / 60.0)
                self.chain_of[oid] = cid
        # 4. expected future wins
        self._future(now)

    def _future(self, now: int) -> None:
        """Hours the requests still to come will add per (region, day): request rate per region and business hour
        (prior 1,040 requests a week over 50 request hours; this week's count replaces it as it grows) x the share we win
        x hours per car. A request on day t lands on t (same_day) or t + 1 (next_day and later), half each."""
        desk, cfg = self.desk, self.cfg
        today = now // DAY
        hour = (now % DAY) / 60.0
        win = (desk.n_won_quoted + 0.45 * 20) / (desk.n_quoted_outcomes + 20)
        regions = self.supply.regions()
        elapsed = sum(max(0.0, min(10.0, (8 + 10 if d < today else hour - 8))) for d in range(today + 1) if d < 5)
        for region in regions:
            seen = sum(self.req_count[(region, d)] for d in range(today + 1))
            prior = cfg.v2_req_per_hour * self.supply.hours(region, 1) / max(1.0, sum(self.supply.hours(x, 1) for x in regions))
            rate = (seen + prior * 10.0) / (elapsed + 10.0)  # requests per request-hour in this region
            for d in range(today, 5):
                hours_left = max(0.0, 18 - max(8.0, hour)) if d == today else 10.0
                n = rate * hours_left * win
                self.hours_future[(region, d)] += 0.5 * n * cfg.v2_hours_per_car
                if d + 1 <= 6:
                    self.hours_future[(region, d + 1)] += 0.5 * n * cfg.v2_hours_per_car


# ---------------------------------------------------------------------- stubs until supply.py / fees.py land
_HUBS = ("helsinki", "tampere", "turku", "jyvaskyla", "kuopio", "oulu")


class SupplyStub:
    """Prior-only Supply with the frozen signature: regions = nearest of six hubs; hours = drivers living in the region
    x the share who work a day (0.45) x hours each gives us (3.0). Replaced by a3's Supply."""

    def __init__(self, desk: "Desk") -> None:
        self.desk = desk
        geo = desk.geo
        self._region = {p: min(_HUBS, key=lambda h: (geo.air(p, h), h)) for p in geo.ids}
        self._homes: dict[str, int] = defaultdict(int)
        for d in desk.roster.values():
            self._homes[self._region.get(d["homePlaceId"], _HUBS[0])] += 1

    def regions(self) -> list[str]:
        return sorted(_HUBS)

    def region(self, place: str) -> str:
        return self._region.get(place, _HUBS[0])

    def hours(self, region: str, day: int) -> float:
        share = 0.45 if day % 7 < 5 else 0.2  # weekend: few work
        # drivers travel: a region's hours are 60% its residents and 40% an equal share of everyone (east Finland has
        # few homes but sees drivers finishing gigs there)
        n = 0.6 * self._homes.get(region, 0) + 0.4 * len(self.desk.roster) / len(_HUBS)
        return n * share * 3.0 * self.desk.cfg.v2_supply_scale

    def on_event(self, e: dict) -> None:
        return None


class FeesStub:
    """Prior-only Fees: cents per driving minute, learned this week from the dealers' typical fees (referenceFeeCents over
    the legs' driving minutes; prior v2_fee_per_min), times v2_fee_mult: the flat fee that books the day before."""

    def __init__(self, desk: "Desk") -> None:
        self.desk = desk
        self.ref_sum, self.drive_sum = 0.0, 0.0
        self.adj_sum, self.adj_n = 0.0, 0.0  # this week's bookings: paid over our opening fee

    def clearing(self, region: str, day: int, hour: int, drive: int, n_cars: int) -> float:
        cfg = self.desk.cfg
        per_min = (self.ref_sum + cfg.v2_fee_per_min * 600.0) / (self.drive_sum + 600.0)
        adj = (self.adj_sum + 1.0 * 10.0) / (self.adj_n + 10.0)
        return (drive * per_min + n_cars * cfg.v2_fee_fixed) * cfg.v2_fee_mult * min(1.3, max(0.9, adj))

    def on_event(self, e: dict) -> None:
        if e["kind"] == "price_request":
            r = e["request"]
            self.ref_sum += r["referenceFeeCents"] - self.desk.cfg.v2_fee_fixed * len(r["legs"])
            self.drive_sum += sum(self.desk.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        elif e["kind"] == "gig_booked":
            rec = self.desk.gigs.get(e["gigId"])
            if rec and rec.schedule and rec.status == "open":
                self.adj_sum += e["feeCents"] / max(1.0, rec.schedule[0]["feeCents"])
                self.adj_n += 1
