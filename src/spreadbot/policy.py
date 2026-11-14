"""The three small models behind every quote.

- OnTime: the chance that a car is delivered on time, from what the request says (slack, drive,
  driver supply, premium, Friday, ...). Fitted offline on research weeks; structural features only.
- Market: the chance that the dealer takes our price, P(win | r) = sigmoid(k (mu - r / trust)),
  with mu = world level + today's shift + this dealer's shift, all learned live from wins and losses.
- Governor: keeps the projected on-time share above the gate by raising the bar for risky cars.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING

from .geo import DAY, HOUR

if TYPE_CHECKING:
    from .desk import Desk


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, x))))


# Logistic fit on 6,291 orders played by the v1c/v1h/v1i policies (dev-01..06), lab/frank/refit_ontime.py.
# Held-out-seed AUC 0.71; predicted vs actual on held-out seeds: 0.78/0.80, 0.88/0.87, 0.92/0.93, 0.95/0.95, 0.97/0.96.
ONTIME_COEF = {
    "intercept": 1.02, "slack12": 0.114, "overnight": -0.983, "log_drive": -0.198, "same_day": -0.709,
    "friday": -0.018, "ready_later": 0.55, "log_sup_p80": 0.359, "log_sup_d30": 0.072, "premium": -1.451,
    "private": -0.636, "note": -0.258, "fee": 0.0,
}
# The first fit, on 3 research weeks with random flat fees (kept for the ablation and the pitch).
ONTIME_COEF_RESEARCH = {
    "intercept": -0.24, "slack12": 0.306, "overnight": -1.177, "log_drive": -0.424, "same_day": -0.363,
    "friday": -0.574, "ready_later": 0.883, "log_sup_p80": 0.142, "log_sup_d30": 0.037, "premium": -1.19,
    "private": -0.164, "note": -0.375, "fee": 0.755,
}


class OnTime:
    def __init__(self, desk: "Desk"):
        self.desk = desk
        self._sup: dict[tuple[str, float], int] = {}

    def supply(self, place: str, radius: float) -> int:
        key = (place, radius)
        if key not in self._sup:
            self._sup[key] = self.desk.supply_near(place, radius)
        return self._sup[key]

    def features(self, r: dict, deadline: int, option: str) -> dict:
        geo, desk = self.desk.geo, self.desk
        L0 = r["legs"][0]
        p, d = L0["pickup"]["placeId"], L0["delivery"]["placeId"]
        drive = sum(geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        notes = desk.note(r["id"])
        ready = L0["pickup"]["window"]["from"]
        if notes and notes[0].ready_at:
            ready = max(ready, notes[0].ready_at)
        if notes and notes[0].deadline:
            deadline = min(deadline, notes[0].deadline)
        slack = (deadline - max(r["respondBy"], ready) - drive) / 60
        return {
            "slack": slack, "slack12": min(max(slack, 0.0), 12.0), "overnight": float(slack > 12), "log_drive": math.log(drive + 10),
            "same_day": float(option == "same_day"), "friday": float(r["respondBy"] // DAY == 4),
            "ready_later": float(ready > r["respondBy"] + 2 * HOUR), "log_sup_p80": math.log1p(self.supply(p, 80.0)),
            "log_sup_d30": math.log1p(self.supply(d, 30.0)), "premium": float(any(L["car"]["premium"] for L in r["legs"])),
            "private": float(L0["pickup"]["privateAddress"] or L0["delivery"]["privateAddress"]), "note": float(r["note"] is not None),
            "fee": desk.cfg.ontime_fee_assumed,
        }

    def p_ok(self, r: dict, deadline: int, option: str) -> tuple[float, float]:
        f = self.features(r, deadline, option)
        coef = ONTIME_COEF_RESEARCH if self.desk.cfg.ontime_model == "research" else ONTIME_COEF
        z = coef["intercept"] + sum(c * f[k] for k, c in coef.items() if k != "intercept")
        return sigmoid(z + self.desk.cfg.ontime_shift), f["slack"]


_LANES: dict = {}


def lane_shift(lane: str) -> float:
    """The competitor's lane factor that holds in every world (RULES), as a shift of the ratio that wins as often.
    Fitted by Javier on 303,778 quotes over 443 level 8 weeks (lanes.json, from main: lab/a/lane_table.py)."""
    if not lane:
        return 0.0
    if not _LANES:
        import json
        import os
        with open(os.path.join(os.path.dirname(__file__), "lanes.json"), encoding="utf-8") as f:
            _LANES.update(json.load(f)["shift"])
    return max(-0.35, min(0.35, _LANES.get(lane, 0.0)))


class Market:
    def __init__(self, desk: "Desk"):
        self.desk, self.cfg = desk, desk.cfg
        self.mu = self.cfg.mu_prior          # world level: competitor price over list
        self.day_shift: dict[int, float] = defaultdict(float)   # today's day factor, price war
        self.dealer_shift: dict[str, float] = defaultdict(float)  # competitor's answer to our wins per dealer
        self.place_shift: dict[tuple[str, int], float] = {}  # (pickup place, day): the outage region
        self.n_obs = 0
        self.day_obs: dict[int, list[bool]] = defaultdict(list)

    def mu_for(self, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        return (self.mu + self.day_shift[day] + self.dealer_shift[dealer] + self.place_shift.get((place, day), 0.0)
                + self.cfg.lane_w * lane_shift(lane))

    def p_win(self, ratio_eff: float, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        return sigmoid(self.cfg.win_slope * (self.mu_for(dealer, day, place, lane) - ratio_eff))

    def observe(self, at: int, dealer: str, ratio_eff: float, won: bool, place: str = "", lane: str = "") -> None:
        day = at // DAY
        g = (1.0 if won else 0.0) - self.p_win(ratio_eff, dealer, day, place, lane)
        k = self.cfg.win_slope
        war = self.cfg.war_guard and self.day_shift[day] < -self.cfg.war_shift
        if not war:
            # On a price-war day (the competitor 20% under everywhere) only today's shift learns: tomorrow it is back.
            self.mu += self.cfg.mu_lr * k * g
            self.dealer_shift[dealer] += self.cfg.dealer_lr * k * g
        self.day_shift[day] += self.cfg.day_lr * k * g
        if self.cfg.place_lr and place:
            # The outage: one region's dealers pay ~30% more for a day. Each place nearby learns from this result.
            for other, w in self.desk.nearby(place):
                key = (other, day)
                self.place_shift[key] = min(0.45, max(-0.3, self.place_shift.get(key, 0.0) + self.cfg.place_lr * w * k * g))
        self.mu = min(max(self.mu, 0.95), 1.9)
        self.day_shift[day] = min(max(self.day_shift[day], -0.4), 0.4)
        self.dealer_shift[dealer] = min(max(self.dealer_shift[dealer], -0.3), 0.3)
        self.n_obs += 1
        self.day_obs[day].append(won)

    def best_ratio(self, dealer: str, day: int, list_cents: int, tf: float, cost: float, risk_frac: float, shadow: float, place: str = "", lane: str = "") -> tuple[float, float]:
        """The ratio over list (before trust) with the best expected margin, and that margin."""
        cfg = self.cfg
        best, best_ev = 0.0, 0.0
        r = cfg.min_ratio
        while r <= cfg.max_ratio + 1e-9:
            price = list_cents * r * tf
            ev = self.p_win(r, dealer, day, place, lane) * (price * (1 - risk_frac) - cost - shadow)
            if ev > best_ev:
                best, best_ev = r, ev
            r += 0.01
        return best, best_ev


class Governor:
    """Projected on-time share = (orders on time + open orders weighted by their on-time chance) / orders.
    Below the target, the bar for new cars rises; far below, only safe cars are taken."""

    def __init__(self, desk: "Desk"):
        self.desk = desk

    def calibration(self) -> float:
        """Observed on-time share of finished orders over what the model predicted for them (this world)."""
        d = self.desk
        done, obs = [], 0
        for oid, ob in d.orders.items():
            if oid in d.ontime_orders:
                done.append(ob)
                obs += 1
            elif oid in d.late_orders or any(t is None and d.now > d.deadline(ob.order, l) for l, t in enumerate(ob.order["deliveredAt"])):
                done.append(ob)
        if len(done) < 15:
            return 1.0
        pred = sum(ob.p_ok for ob in done)
        k = len(done) / (len(done) + 30)  # shrink to 1 while few orders are done
        return min(1.05, max(0.75, k * obs / max(pred, 1e-6) + (1 - k)))

    def projection(self) -> float:
        """Expected final on-time share of the orders won so far, from the live state of each open order."""
        d = self.desk
        ontime = len(d.ontime_orders)
        late = len(d.late_orders)
        cal = self.calibration()
        open_p = 0.0
        n_open = 0
        for oid, ob in d.orders.items():
            if oid in d.ontime_orders or oid in d.late_orders:
                continue
            n_open += 1
            legs = [l for l, t in enumerate(ob.order["deliveredAt"]) if t is None]
            held = legs and all((g := d.leg_gig.get((oid, l))) and d.gigs[g].status in ("booked", "working") for l in legs)
            if any(d.now > d.deadline(ob.order, l) for l in legs):
                p = 0.0
            elif held:
                p = 0.95
            elif ob.urgent:
                p = 0.45
            else:
                p = ob.p_ok * cal
            open_p += p
        total = ontime + late + n_open
        return (ontime + open_p) / total if total else 1.0

    def bar(self) -> float:
        cfg = self.desk.gov_cfg()
        proj = self.projection()
        if proj < cfg.gov_rescue:
            if cfg.dilute:
                # Take a car only if it is likelier on time than the orders we hold: each one then lifts the share.
                return max(cfg.theta_tight, min(cfg.theta_rescue, proj + cfg.dilute_margin))
            return cfg.theta_rescue
        if proj < cfg.gov_tight:
            return cfg.theta_tight
        return cfg.theta
