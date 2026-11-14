"""Demand: the cars we will still win this week, per pickup region and arrival day, for the V2 planner (planner.py).

    expected cars = requests still to arrive (prior by day x hour x pickup place)
                    x won cars per request (prior by day and half-day x place factor) x this week's win scale
                    split over deadline days and options by the prior mix of won cars (arrival day x half-day),
                    re-weighted by this week's option shares

Why a prior and almost no online learning of the requests: the request stream is the most stable part of the world.
57 distinct level-8 weeks (one per seed; a seed's stream is identical in every run) all have 1,030-1,040 requests, day totals
vary like Poisson, and a region's morning count says nothing about its afternoon (correlation -0.14..0.06). Region counts
are clumpy (dealer batches: 48% of requests, 138 batches a week), and no clump persists: scaling a region by what it sent
so far made the held-out error worse at every strength (research/sessionA/scripts/a5_demand_check.py). What does change
with our policy is how many we win, so that is learned online, with a weak weight (WIN_K): on c3 and on three other
policies (money, k18, c1) a strong online scale was worse than the prior (a5_wins_check.py), but V2 wins far more.

Regions come from desk.supply.region() (a3's driver pools) when it exists, else a3's table below; every prior is per
pickup place, so any region map works. Everything is folded from events (on_event), so a replay rebuilds the same state.
Time: world minutes, DAY = 1440, day index Mon = 0. Tables: research/sessionA/scripts/a5_demand_tables.py.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, NamedTuple

from .geo import DAY, HOUR

if TYPE_CHECKING:
    from .desk import Desk


class Expect(NamedTuple):
    deadline_day: int        # day index of the won option's deadline (Fri arrivals: Mon2 = 7)
    option_mix: dict         # option kind -> share of these cars
    n_cars: float            # expected cars we win (legs; a trade-in counts 2)
    mean_drive_min: float    # driving minutes per car, pickup to delivery


# a3's driver pools (src/spreadbot/supply.py, claude/a-supply 4c22c81): only used when the desk has no Supply
REGION = {
    "helsinki": "cap", "vantaa": "cap", "espoo": "cap", "hyvinkaa": "cap", "porvoo": "cap",
    "tampere": "tre", "lempaala": "tre", "hameenlinna": "tre",
    "turku": "tku", "raisio": "tku", "salo": "tku", "pori": "sw", "rauma": "sw",
    "lahti": "lahti", "kouvola": "lahti", "kotka": "lahti", "lappeenranta": "lahti",
    "oulu": "oulu", "jyvaskyla": "jkl", "kuopio": "east", "joensuu": "east", "mikkeli": "east", "savonlinna": "east",
    "kajaani": "east", "vaasa": "west", "seinajoki": "west", "kokkola": "west", "ylivieska": "west",
    "rovaniemi": "north", "kemi": "north",
}

# ---- priors: 57 weeks of requests (dev-01..54, exp-01..03), 17 c3 weeks of wins (dev-07..18, dev-43..54 c3-val)
PLACE_SHARE = {"espoo": 0.0782, "hameenlinna": 0.0069, "helsinki": 0.0733, "hyvinkaa": 0.1824, "joensuu": 0.0084, "jyvaskyla": 0.0300, "kajaani": 0.0027, "kemi": 0.0022, "kokkola": 0.0107, "kotka": 0.0030, "kouvola": 0.0104, "kuopio": 0.0265, "lahti": 0.0389, "lappeenranta": 0.0109, "lempaala": 0.0403, "mikkeli": 0.0150, "oulu": 0.0464, "pori": 0.0232, "porvoo": 0.0223, "raisio": 0.0334, "rauma": 0.0052, "rovaniemi": 0.0145, "salo": 0.0115, "savonlinna": 0.0027, "seinajoki": 0.0063, "tampere": 0.0387, "turku": 0.0304, "vaasa": 0.0209, "vantaa": 0.1863, "ylivieska": 0.0183}
ARRIVALS = {  # (day, hour) -> mean requests a week; none before 08:00, after 20:59 or at the weekend
    (0, 8): 3.67, (0, 9): 21.47, (0, 10): 25.39, (0, 11): 23.49, (0, 12): 24.75, (0, 13): 24.67, (0, 14): 23.74, (0, 15): 22.98, (0, 16): 24.00, (0, 17): 24.67, (0, 18): 3.84, (0, 19): 2.51, (0, 20): 3.07,
    (1, 8): 2.68, (1, 9): 22.46, (1, 10): 24.84, (1, 11): 22.37, (1, 12): 23.35, (1, 13): 21.91, (1, 14): 21.86, (1, 15): 22.35, (1, 16): 19.70, (1, 17): 22.77, (1, 18): 3.98, (1, 19): 2.05, (1, 20): 2.40,
    (2, 8): 2.79, (2, 9): 20.00, (2, 10): 21.74, (2, 11): 21.07, (2, 12): 19.32, (2, 13): 19.51, (2, 14): 21.33, (2, 15): 20.39, (2, 16): 22.11, (2, 17): 22.77, (2, 18): 3.53, (2, 19): 1.84, (2, 20): 3.14,
    (3, 8): 3.47, (3, 9): 21.04, (3, 10): 24.33, (3, 11): 23.40, (3, 12): 23.49, (3, 13): 21.60, (3, 14): 24.21, (3, 15): 22.89, (3, 16): 22.61, (3, 17): 21.58, (3, 18): 2.67, (3, 19): 2.16, (3, 20): 1.77,
    (4, 8): 2.81, (4, 9): 17.33, (4, 10): 20.11, (4, 11): 19.98, (4, 12): 17.89, (4, 13): 19.46, (4, 14): 19.86, (4, 15): 19.82, (4, 16): 21.00, (4, 17): 20.74,
}
WIN_PRIOR = 0.3554  # won cars per request, c3 (336 orders a week)
WIN_DAY = {(0, 0): 0.3262, (0, 1): 0.3190, (1, 0): 0.3910, (1, 1): 0.4080, (2, 0): 0.4663, (2, 1): 0.3993,
           (3, 0): 0.5067, (3, 1): 0.3461, (4, 0): 0.2636, (4, 1): 0.1377}  # (day, arrived 13:00 or later) -> won cars per request
WIN_PLACE = {"espoo": 1.203, "hameenlinna": 0.680, "helsinki": 1.270, "hyvinkaa": 1.222, "joensuu": 0.402, "jyvaskyla": 0.563, "kajaani": 0.273, "kemi": 0.194, "kokkola": 0.455, "kotka": 0.505, "kouvola": 0.721, "kuopio": 0.759, "lahti": 0.785, "lappeenranta": 0.359, "lempaala": 0.880, "mikkeli": 0.449, "oulu": 0.715, "pori": 0.390, "porvoo": 0.680, "raisio": 0.722, "rauma": 0.654, "rovaniemi": 0.242, "salo": 0.692, "savonlinna": 0.344, "seinajoki": 0.601, "tampere": 0.880, "turku": 0.785, "vaasa": 0.753, "vantaa": 1.469, "ylivieska": 0.449}  # won cars over the day rate, shrunk to the region
DRIVE_PER_CAR = {"espoo": 115, "hameenlinna": 151, "helsinki": 121, "hyvinkaa": 135, "joensuu": 238, "jyvaskyla": 169, "kajaani": 202, "kemi": 198, "kokkola": 206, "kotka": 182, "kouvola": 143, "kuopio": 207, "lahti": 147, "lappeenranta": 190, "lempaala": 123, "mikkeli": 176, "oulu": 292, "pori": 203, "porvoo": 147, "raisio": 149, "rauma": 178, "rovaniemi": 337, "salo": 178, "savonlinna": 175, "seinajoki": 185, "tampere": 121, "turku": 126, "vaasa": 225, "vantaa": 118, "ylivieska": 224}  # minutes per won car
OFFSETS = {  # (arrival day, pm) -> {(deadline day - arrival day, option): share of won cars}
    (0, 0): {(0, "same_day"): 0.305, (1, "next_day"): 0.110, (1, "same_day"): 0.365, (2, "next_day"): 0.069, (2, "same_day"): 0.041, (3, "next_day"): 0.012, (3, "same_day"): 0.043, (3, "within_3_days"): 0.007, (4, "next_day"): 0.005, (4, "same_day"): 0.009, (4, "within_3_days"): 0.011, (7, "next_day"): 0.014, (7, "within_3_days"): 0.009},
    (0, 1): {(0, "same_day"): 0.078, (1, "next_day"): 0.184, (1, "same_day"): 0.451, (2, "next_day"): 0.124, (2, "same_day"): 0.031, (3, "next_day"): 0.009, (3, "same_day"): 0.036, (3, "within_3_days"): 0.009, (4, "next_day"): 0.006, (4, "same_day"): 0.039, (4, "within_3_days"): 0.021, (7, "next_day"): 0.009},
    (1, 0): {(0, "same_day"): 0.265, (1, "next_day"): 0.154, (1, "same_day"): 0.330, (2, "next_day"): 0.093, (2, "same_day"): 0.038, (3, "next_day"): 0.024, (3, "same_day"): 0.071, (3, "within_3_days"): 0.008, (6, "next_day"): 0.008, (6, "within_3_days"): 0.011},
    (1, 1): {(0, "same_day"): 0.043, (1, "next_day"): 0.221, (1, "same_day"): 0.397, (2, "next_day"): 0.164, (2, "same_day"): 0.055, (3, "next_day"): 0.009, (3, "same_day"): 0.066, (3, "within_3_days"): 0.006, (6, "next_day"): 0.016, (6, "within_3_days"): 0.024},
    (2, 0): {(0, "same_day"): 0.143, (1, "next_day"): 0.149, (1, "same_day"): 0.432, (2, "next_day"): 0.092, (2, "same_day"): 0.092, (5, "next_day"): 0.053, (5, "within_3_days"): 0.039},
    (2, 1): {(0, "same_day"): 0.053, (1, "next_day"): 0.213, (1, "same_day"): 0.325, (2, "next_day"): 0.178, (2, "same_day"): 0.130, (5, "next_day"): 0.034, (5, "within_3_days"): 0.066},
    (3, 0): {(0, "same_day"): 0.161, (1, "next_day"): 0.144, (1, "same_day"): 0.444, (4, "next_day"): 0.209, (4, "within_3_days"): 0.042},
    (3, 1): {(0, "same_day"): 0.043, (1, "next_day"): 0.155, (1, "same_day"): 0.311, (4, "next_day"): 0.426, (4, "within_3_days"): 0.065},
    (4, 0): {(0, "same_day"): 0.209, (3, "next_day"): 0.791},
    (4, 1): {(0, "same_day"): 0.050, (3, "next_day"): 0.950},
}
PM = 13                # the half-day split of WIN_DAY and OFFSETS: afternoon requests are ready the next day more often
WIN_K = 300.0          # requests of prior weight on this week's win scale (held out: 300 ~ the prior on c3/k18/c1, 30 worse)
OPT_K = 60.0           # won cars of prior weight on this week's option shares (V2 may steer to next_day)
SCALE_MIN, SCALE_MAX = 0.4, 2.5  # a week's win scale stays inside this (c3 336 orders; the top teams ~450-530)


def _prior_opt_share() -> dict[str, float]:
    """Option shares of won cars in the prior, weighted by the expected wins of each (day, half-day) cell."""
    tot: dict[str, float] = defaultdict(float)
    for (d, pm), mix in OFFSETS.items():
        reqs = sum(v for (dd, h), v in ARRIVALS.items() if dd == d and (h >= PM) == bool(pm))
        w = reqs * WIN_DAY[(d, pm)]
        for (_, opt), s in mix.items():
            tot[opt] += w * s
    t = sum(tot.values())
    return {k: v / t for k, v in sorted(tot.items())}


PRIOR_OPT = _prior_opt_share()


class Demand:
    def __init__(self, desk: "Desk") -> None:
        self.desk = desk
        self.req_at: dict[str, tuple[int, str, int]] = {}            # request id -> (arrival minute, pickup place, cars)
        self.outcome: set[str] = set()                              # request ids with a won or lost outcome
        self.won: dict[str, tuple[str, int, int, str, int]] = {}    # order id -> (place, arrival day, cars, option, deadline day)
        self.exp_done = 0.0      # prior expected won cars of the requests with an outcome
        self.won_cars = 0.0      # cars won of those requests
        self.opt_won: dict[str, float] = defaultdict(float)  # this week's won cars per option

    # ------------------------------------------------------------------ regions
    def region(self, place: str) -> str:
        sup = getattr(self.desk, "supply", None)
        if sup is not None:
            return sup.region(place)
        return REGION.get(place, "cap")

    def _places(self, region: str) -> list[str]:
        return [p for p in sorted(PLACE_SHARE) if self.region(p) == region]

    # ------------------------------------------------------------------ events
    def on_event(self, e: dict) -> None:
        k = e.get("kind")
        if k == "price_request":
            r = e["request"]
            if r["id"] not in self.req_at:
                self.req_at[r["id"]] = (r["arrivedAt"], r["legs"][0]["pickup"]["placeId"], len(r["legs"]))
        elif k == "order_won":
            o = e["order"]
            self._outcome(o["id"], True, o, e["at"])
        elif k == "order_lost":
            self._outcome(e["requestId"], False, None, e["at"])

    def _outcome(self, rid: str, won: bool, order: dict | None, at: int) -> None:
        if rid in self.outcome:
            return
        self.outcome.add(rid)
        if rid in self.req_at:
            arr, place, cars = self.req_at[rid]
        elif order is not None:
            arr, place, cars = at, order["legs"][0]["pickup"]["placeId"], len(order["legs"])
        else:
            return
        day = arr // DAY
        self.exp_done += self._win_rate(day, (arr % DAY) // HOUR, place) * 1.0
        if won and order is not None:
            ddl = order.get("deadline")
            if ddl is None:
                ddl = max(order["legs"][0].get("delivery", {}).get("window", {}).get("to", arr), arr)
            opt = order.get("option", "same_day")
            self.won[rid] = (place, day, cars, opt, ddl // DAY)
            self.won_cars += cars
            self.opt_won[opt] += cars

    # ------------------------------------------------------------------ API
    def win_scale(self) -> float:
        """This week's won cars over the prior's expectation for the same requests, shrunk with WIN_K requests."""
        k = WIN_K * WIN_PRIOR
        return min(SCALE_MAX, max(SCALE_MIN, (self.won_cars + k) / (self.exp_done + k)))

    def requests_left(self, region: str, day: int, now: int) -> float:
        """Requests with pickup in `region` still to arrive on day index `day` after minute `now`."""
        share = sum(PLACE_SHARE[p] for p in self._places(region))
        return share * sum(n for _, n in self._remaining(day, now))

    def expected(self, region: str, day: int, now: int) -> list[Expect]:
        """Cars we will still win from requests with pickup in `region` that arrive on day index `day` after `now`,
        grouped by the deadline day of the option won (sorted by deadline day). [] for a past day or a weekend."""
        places = self._places(region)
        if not places:
            return []
        scale = self.win_scale()
        optw = self._option_weights()
        cars: dict[int, float] = defaultdict(float)
        mix: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        drive: dict[int, float] = defaultdict(float)
        for hour, n in self._remaining(day, now):
            pm = int(hour >= PM)
            offs = OFFSETS.get((day, pm), {})
            norm = sum(s * optw.get(opt, 1.0) for (_, opt), s in offs.items()) or 1.0
            for p in places:
                w = n * PLACE_SHARE[p] * self._win_rate(day, hour, p) * scale
                if w <= 0:
                    continue
                for (o, opt), s in sorted(offs.items()):
                    c = w * s * optw.get(opt, 1.0) / norm
                    cars[day + o] += c
                    mix[day + o][opt] += c
                    drive[day + o] += c * DRIVE_PER_CAR[p]
        out = []
        for dd in sorted(cars):
            c = cars[dd]
            if c <= 1e-9:
                continue
            out.append(Expect(dd, {k: v / c for k, v in sorted(mix[dd].items())}, c, drive[dd] / c))
        return out

    def wins_so_far(self, region: str, day: int) -> float:
        """Cars won so far from requests with pickup in `region` that arrived on day index `day`."""
        return float(sum(c for (p, d, c, _, _) in self.won.values() if d == day and self.region(p) == region))

    def state(self) -> dict:
        return {"won_cars": self.won_cars, "exp_done": round(self.exp_done, 1), "scale": round(self.win_scale(), 3),
                "opt": {k: round(v, 2) for k, v in sorted(self._option_weights().items())}}

    # ------------------------------------------------------------------ parts
    @staticmethod
    def _win_rate(day: int, hour: int, place: str) -> float:
        """Prior won cars per request arriving at this hour of this day at this pickup place."""
        return WIN_DAY.get((day, int(hour >= PM)), 0.0) * WIN_PLACE.get(place, 1.0)

    @staticmethod
    def _remaining(day: int, now: int) -> list[tuple[int, float]]:
        """(hour, expected requests) still to arrive on day index `day` after minute `now` (partial current hour)."""
        today = now // DAY
        if day < today:
            return []
        out = []
        for h in range(24):
            n = ARRIVALS.get((day, h), 0.0)
            if not n:
                continue
            if day == today:
                start = day * DAY + h * HOUR
                frac = min(1.0, max(0.0, (start + HOUR - now) / HOUR))
                n *= frac
            if n > 0:
                out.append((h, n))
        return out

    def _option_weights(self) -> dict[str, float]:
        """This week's option shares of won cars over the prior's, shrunk with OPT_K cars (1.0 = the prior mix)."""
        tot = sum(self.opt_won.values())
        out = {}
        for opt, ps in PRIOR_OPT.items():
            out[opt] = ((self.opt_won.get(opt, 0.0) + OPT_K * ps) / (tot + OPT_K)) / ps
        return out
