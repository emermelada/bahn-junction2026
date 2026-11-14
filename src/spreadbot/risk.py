"""Risk: P(a won car ends late), on what the planner knows when it quotes and plans the car (V2, planner.py).

Why a new model: OnTime (policy.py) sees only the request. On played weeks the late cars are mostly cars that no driver booked
before the world's deadline warning (c3: 11 of 20 late cars a week; the volume probes p3/p5 on dev-07/08: 16-17 of 31), and
that grows with our load: Thursday/Friday deadlines, a region already full of our cars, many of our gigs still unbooked there,
a short lead from posting to the last pickup. Risk adds those dispatch terms to the request's own.

Logistic fit on 87,606 won cars of ~265 played level-8 weeks (research/sessionA/scripts/a3_risk_fit.py). Held-out seeds
(number % 4 == 3, 23,288 cars): AUC 0.81 against 0.73 for OnTime's p_ok as quoted; deciles pred/actual 0.006/0.012 ...
0.054/0.061, 0.083/0.096, 0.255/0.255 (p_ok over-predicts: 0.023/0.018 ... 0.181/0.144). On the volume probes it
under-predicts by ~1-1.5 points (p5 0.067 vs 0.078, p7 0.075 vs 0.087): few played weeks reach that load.

Features: see features() and the fit script; all from the desk at call time, so nothing to rebuild after a restart.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .geo import DAY, HOUR

if TYPE_CHECKING:
    from .desk import Desk

# a3_risk_fit.py, fit on all 87,606 cars (L2 1.0). Same feature definitions as the fit script. A regional load (our cars
# due that day in the Supply region over Supply.hours) added nothing once the world-wide load is in (held-out coef -0.06).
RISK_COEF = {
    "intercept": -5.336, "slack12": -0.049, "overnight": 0.294, "lead_h": -0.076, "pick_dl": 0.095, "thu": 0.311,
    "fri": 0.117, "mon2": -0.642, "log_drive": 0.878, "tradein": 2.230, "private": 0.795, "note": 0.096,
    "premium": 1.441, "log_sup80": -0.294, "backlog": 0.111, "chain2": 0.877, "gload": 1.398, "gload_hi": 1.356,
}
RELEASE_HOUR = 16     # a car for a later day is posted at the evening release the day before (cfg.hold_hour)


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


class Risk:
    def __init__(self, desk: "Desk") -> None:
        self.desk = desk
        self._supply = None
        self._cache: dict[tuple, float] = {}
        self._cache_at = -1

    # ------------------------------------------------------------------ API
    def p_late(self, x: dict, option: Optional[str], planned_day: int, chain_size: int = 1) -> float:
        """x: a price request (with options; `option` names the one) or a won order (its own deadline). planned_day: the day
        the planner would pick the car up. chain_size: distinct orders in the car's chain (1 = alone)."""
        f = self.features(x, option, planned_day, chain_size)
        return _sig(RISK_COEF["intercept"] + sum(RISK_COEF[k] * v for k, v in f.items()))

    def on_event(self, e: dict) -> None:
        """No state of its own: every feature is read from the desk when asked (rebuilds with the desk)."""
        return None

    # ------------------------------------------------------------------ features
    def features(self, x: dict, option: Optional[str], planned_day: int, chain_size: int = 1) -> dict[str, float]:
        desk = self.desk
        geo = desk.geo
        legs = x["legs"]
        L0 = legs[0]
        pk = L0["pickup"]["placeId"]
        drive = sum(geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in legs)
        if "options" in x:
            dl = next((o["deadline"] for o in x["options"] if o["kind"] == option), x["options"][0]["deadline"])
        else:
            dl = x["deadline"]
        ns = desk.note(x["id"])
        if ns and ns[0].deadline:
            dl = min(dl, ns[0].deadline)
        now = desk.now
        dday = dl // DAY
        slack = (dl - max(now, L0["pickup"]["window"]["from"]) - drive) / 60.0
        post = now if planned_day <= now // DAY else max(now, (planned_day - 1) * DAY + RELEASE_HOUR * HOUR)
        lead = (dl - drive - post) / 60.0
        region = self.supply().region(pk)
        gload = 10.0 * self.due(dday) / max(1, len(desk.roster))
        return {
            "slack12": min(max(slack, 0.0), 12.0), "overnight": float(slack > 12), "lead_h": min(max(lead, 0.0), 24.0),
            "pick_dl": float(min(planned_day, dday) >= dday), "thu": float(dday == 3), "fri": float(dday == 4), "mon2": float(dday >= 7),
            "log_drive": math.log(drive + 10), "tradein": float(len(legs) == 2),
            "private": float(L0["pickup"]["privateAddress"] or L0["delivery"]["privateAddress"]), "note": float(x.get("note") is not None),
            "premium": float(any(L["car"]["premium"] for L in legs)), "log_sup80": math.log1p(desk.supply_near(pk, 80.0)),
            "backlog": math.log1p(self.backlog(region)), "chain2": float(chain_size >= 2),
            "gload": gload, "gload_hi": max(0.0, gload - 1.0),
        }

    def supply(self):
        if self._supply is None:
            self._supply = getattr(self.desk, "supply", None)
            if self._supply is None:
                from .supply import Supply
                self._supply = Supply(self.desk)
        return self._supply

    def _fresh(self) -> None:
        if self._cache_at != self.desk.now:
            self._cache, self._cache_at = {}, self.desk.now

    def due(self, dday: int) -> int:
        """Our won cars (not cancelled) due on this day, all regions: c3's day load."""
        self._fresh()
        key = ("d", dday)
        if key not in self._cache:
            desk = self.desk
            self._cache[key] = sum(1 for oid in sorted(desk.orders)
                                   if min(desk.deadline(desk.orders[oid].order, l) for l in range(len(desk.orders[oid].order["legs"]))) // DAY == dday)
        return self._cache[key]

    def backlog(self, region: str) -> int:
        """Our gigs open (posted, not booked) whose first pickup is in the region."""
        self._fresh()
        key = ("b", region)
        if key not in self._cache:
            desk, sup = self.desk, self.supply()
            n = 0
            for gid in sorted(desk.gigs):
                rec = desk.gigs[gid]
                if rec.status != "open" or not rec.legs:
                    continue
                ob = desk.orders.get(rec.legs[0][0])
                if ob and sup.region(ob.order["legs"][rec.legs[0][1]]["pickup"]["placeId"]) == region:
                    n += 1
            self._cache[key] = n
        return self._cache[key]
