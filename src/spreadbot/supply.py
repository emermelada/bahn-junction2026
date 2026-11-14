"""Supply: driver-hours available to our gigs per (region, day), the capacity side of the V2 planner (planner.py).

Hours are planner hours: driving + handling of our cars (Planner.hours_of), charged to the pickup region and pickup day.

    hours(region, day) = BASE[region] x roster x day share x learned x flu x snow x cfg.v2_supply_scale

- BASE: p95 over 302 played level-8 weeks of the planner-hours our cars used in the region on a Tue-Fri, x HEADROOM.
  Book time and drops stay flat up to that p95 (no sign of saturation), and the top teams move ~1.4x our cars, so the
  soft limit lies above it (research/sessionA/scripts/a3_supply_fit.py, a3_supply_prior.py).
- roster: this world's drivers living in the region against the 302-week mean, weighted by the share of the region's
  hours they drive (capital 70%; elsewhere 4-26%: the rest come from other regions, mostly the capital).
- day share: Mon and Mon2 count as a weekday (both are demand-limited, not supply-limited: Mon2 has 20 of our drivers
  against 55-73 on Tue-Fri); Saturday has short site hours (p95 0.17 of a weekday); Sunday every site is closed.
- learned: how readily drivers near here took our gigs this week (booked within an hour at the posted fee, a drop counts
  as a miss) against the week's share everywhere, shrunk to 1 and clamped: a region whose gigs sit gets fewer hours.
- flu: FLU_DROPS morning drops on a day cut the rest of that day by 30% everywhere (handbook: 30% of the drivers who
  meant to work stay at home). snow: a forecast region-day x SNOW.
Everything is folded from events (on_event) and the roster, so a replay after a restart gives the same numbers.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .geo import DAY

if TYPE_CHECKING:
    from .desk import Desk

# Driver pools: places whose gigs the same drivers take (80 km catchments; drivers' home region per started gig).
REGION = {
    "helsinki": "cap", "vantaa": "cap", "espoo": "cap", "hyvinkaa": "cap", "porvoo": "cap",
    "tampere": "tre", "lempaala": "tre", "hameenlinna": "tre",
    "turku": "tku", "raisio": "tku", "salo": "tku", "pori": "sw", "rauma": "sw",
    "lahti": "lahti", "kouvola": "lahti", "kotka": "lahti", "lappeenranta": "lahti",
    "oulu": "oulu", "jyvaskyla": "jkl", "kuopio": "east", "joensuu": "east", "mikkeli": "east", "savonlinna": "east",
    "kajaani": "east", "vaasa": "west", "seinajoki": "west", "kokkola": "west", "ylivieska": "west",
    "rovaniemi": "north", "kemi": "north",
}
# region: (mean drivers living there, share of the region's hours they drive, p95 Tue-Fri planner-hours a day)
# 302 weeks of v1 / v1-evening / v1-best reveals, <= 8 per seed (a3_supply_prior.py).
PRIOR = {
    "cap": (413, 0.70, 200.3),
    "east": (39, 0.11, 28.1),
    "jkl": (42, 0.20, 16.0),
    "lahti": (37, 0.10, 25.6),
    "north": (6, 0.06, 12.8),
    "oulu": (60, 0.16, 34.4),
    "sw": (8, 0.04, 13.1),
    "tku": (48, 0.21, 29.9),
    "tre": (79, 0.25, 34.0),
    "west": (34, 0.10, 29.9),
}
HEADROOM = 1.5        # no saturation seen up to the p95 day; the top teams move ~1.4x our cars at 95% on time
DAY_SHARE = (1.0, 1.0, 1.0, 1.0, 1.0, 0.17, 0.0, 1.0)  # Mon..Sun, Mon2 (see the docstring)
LEARN_K = 30.0        # bookings of prior weight on a region's own booking share (regions differ little: 0.75-0.82)
LEARN_MIN, LEARN_MAX = 0.8, 1.2
FAST_MIN = 60         # "booked readily": within an hour of posting, at the opening fee
FLU_DROPS = 5         # morning (05-13 h) drops on one day: 4% of 440 played weekdays reach 5
FLU_CUT = 0.7         # handbook: the flu keeps 30% of the drivers who meant to work at home
SNOW = 0.9            # handbook: some drivers stay at home; the reveals show no fall in hours used (x1.10, 855 region-days)


class Supply:
    def __init__(self, desk: "Desk") -> None:
        self.desk = desk
        homes: dict[str, int] = defaultdict(int)
        for d in desk.roster.values():
            homes[self.region(d["homePlaceId"])] += 1
        self.base: dict[str, float] = {}
        for rg, (n_mean, share, p95) in PRIOR.items():
            roster = share * homes.get(rg, 0) / max(1.0, n_mean) + (1.0 - share)
            self.base[rg] = p95 * HEADROOM * roster
        self.fast: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # region -> [readily booked, booked or dropped]
        self.seen: set[str] = set()  # gigs whose first booking is counted
        self.morning_drops: dict[int, int] = defaultdict(int)
        self.snow: set[tuple[str, int]] = set()
        self.viewers: dict[tuple[str, int], set[str]] = defaultdict(set)  # (home region, day) -> drivers seen, for the log

    # ------------------------------------------------------------------ API (frozen in planner.py)
    def regions(self) -> list[str]:
        return sorted(PRIOR)

    def region(self, place: str) -> str:
        return REGION.get(place, "cap")

    def hours(self, region: str, day: int) -> float:
        h = self.base.get(region, 0.0) * DAY_SHARE[day if 0 <= day <= 7 else 0] * self.learned(region)
        if self.morning_drops.get(day, 0) >= FLU_DROPS:
            h *= FLU_CUT
        if (region, day) in self.snow:
            h *= SNOW
        return max(0.0, h * self.desk.cfg.v2_supply_scale)

    def on_event(self, e: dict) -> None:
        k = e.get("kind")
        if k == "gig_booked":
            rg = self._gig_region(e["gigId"])
            rec = self.desk.gigs.get(e["gigId"])
            if rg and rec and e["gigId"] not in self.seen:
                self.seen.add(e["gigId"])
                s = self.fast[rg]
                s[0] += int(e["at"] - rec.posted_at <= FAST_MIN and e["feeCents"] <= rec.schedule[0]["feeCents"])
                s[1] += 1
        elif k == "gig_dropped":
            rg = self._gig_region(e["gigId"])
            if rg:
                self.fast[rg][1] += 1
            if 5 * 60 <= e["at"] % DAY < 13 * 60:
                self.morning_drops[e["at"] // DAY] += 1
        elif k == "forecast":
            for day in range(e["from"] // DAY, (e["to"] - 1) // DAY + 1):
                for p in e.get("placeIds", []):
                    self.snow.add((self.region(p), day))
        elif k == "gig_viewed":
            d = self.desk.roster.get(e["driverId"])
            if d:
                self.viewers[(self.region(d["homePlaceId"]), e["at"] // DAY)].add(e["driverId"])

    # ------------------------------------------------------------------ parts
    def learned(self, region: str) -> float:
        """This week's share of readily booked gigs here over the share everywhere, shrunk to 1 by LEARN_K bookings."""
        fa = sum(s[0] for s in self.fast.values())
        na = sum(s[1] for s in self.fast.values())
        if na == 0:
            return 1.0
        week = (fa + 0.8 * LEARN_K) / (na + LEARN_K)  # 0.80: the share in played c3 weeks (0.74-0.86 per week)
        s = self.fast.get(region, (0, 0))
        mine = (s[0] + week * LEARN_K) / (s[1] + LEARN_K)
        return min(LEARN_MAX, max(LEARN_MIN, mine / week))

    def _gig_region(self, gid: str):
        rec = self.desk.gigs.get(gid)
        if not rec or not rec.stops:
            return None
        oid, leg = rec.stops[0]["orderId"], rec.stops[0].get("leg", 0)
        ob = self.desk.orders.get(oid)
        o = ob.order if ob else self.desk.requests.get(oid)
        if not o:
            return None
        return self.region(o["legs"][leg]["pickup"]["placeId"])

    def state(self) -> dict:
        """For the log: hours per region for the next days, learned factors, flu and snow days."""
        today = self.desk.now // DAY
        return {"hours": {rg: [round(self.hours(rg, d), 1) for d in range(today, min(8, today + 3))] for rg in self.regions()},
                "learned": {rg: round(self.learned(rg), 2) for rg in self.regions()},
                "flu": sorted(d for d, n in self.morning_drops.items() if n >= FLU_DROPS), "snow": sorted(self.snow)}
