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


def barrier_cents(proj: float, n: int, barrier: tuple) -> float:
    """Price of one expected late car (cents) under the late barrier: small while the week's expected late share is well inside
    what the target allows, steep as it nears it, capped at 2^grip x eur. proj = the governor's projected on-time share."""
    target, eur, grip, calm = barrier
    used = n * (1.0 - proj) / (calm + n) / (1.0 - target)
    return eur * 100.0 * min(2.0, max(0.0, used)) ** grip


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
        self._late = None  # LateModel, built on first use when ontime_model is "gbm"

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
        if self.desk.cfg.ontime_model == "gbm":
            # The trees fitted on 804k won orders (late_gbm.py): held-out AUC 0.897 against 0.737 for the logistic below.
            if self._late is None:
                from .late_gbm import LateModel
                self._late = LateModel(self.desk)
            opt = next((o for o in r["options"] if o["kind"] == option), r["options"][0])
            return 1.0 - self._late.p_late(r, opt), f["slack"]
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
        self.dealer_n: dict = {}  # ucb: resolved quotes per dealer this week
        self.day_obs: dict[int, list[bool]] = defaultdict(list)
        # day_kalman: per day, hypotheses [weight, mean shift, variance] for (normal day, war day), in ratio units.
        self.kal: dict[int, list[list[float]]] = {}
        self.war_seen = False
        self.out_acc: dict[tuple[int, str], list[float]] = {}  # (day, region centre) -> [sum(won - p), sum p(1-p), n], 08-18
        self.beta = 0.0                                         # dist_lr: competitor level per ln(km) around the median lane (e^4.97 = 144 km)
        self.outage: dict[int, str] = {}                        # day -> centre of the flagged outage region

    def kal_day(self, day: int) -> list[list[float]]:
        """Today's two hypotheses, made at the first quote or result of the day. The war comes once a week on a
        weekday: its prior is 1 / (weekdays left), capped at 0.7, and small once a past day looked like it."""
        if day not in self.kal:
            prev = [d for d in self.kal if d < day]
            if prev and self.kal[max(prev)][1][0] > 0.8:
                self.war_seen = True
            c = self.cfg
            pw = 0.0 if day > 4 else (0.03 if self.war_seen else min(0.7, 1.0 / (5 - day)))
            sd0, sdw = c.kal_sd * self.mu, c.kal_war_sd * self.mu
            self.kal[day] = [[1 - pw, 0.0, sd0 * sd0], [pw, (c.kal_war - 1) * self.mu, sdw * sdw]]
        return self.kal[day]

    def base_for(self, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        return self.mu + self.dealer_shift[dealer] + self.place_shift.get((place, day), 0.0) + self.cfg.lane_w * lane_shift(lane)

    def in_outage(self, day: int, place: str, t: int) -> bool:
        c = self.outage.get(day)
        return bool(c and place) and 8 * HOUR <= t % DAY < 18 * HOUR and self.desk.geo.air(c, place) <= 80.0

    def mu_for(self, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        if self.cfg.outage_z and self.in_outage(day, place, self.desk.now):
            return self.mu_base(dealer, day, place, lane) * (1 + self.cfg.outage_up)
        return self.mu_base(dealer, day, place, lane)

    def dist_x(self, lane: str) -> float:
        if not lane:
            return 0.0
        a, b = lane.split(">")
        return math.log(max(10.0, self.desk.geo.km(a, b))) - 4.97

    def mu_base(self, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        if self.cfg.dist_lr:
            return self.mu_core(dealer, day, place, lane) + self.beta * self.dist_x(lane)
        return self.mu_core(dealer, day, place, lane)

    def mu_core(self, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        if self.cfg.day_kalman:
            return self.base_for(dealer, day, place, lane) + sum(w * d for w, d, v in self.kal_day(day))
        return (self.mu + self.day_shift[day] + self.dealer_shift[dealer] + self.place_shift.get((place, day), 0.0)
                + self.cfg.lane_w * lane_shift(lane))

    def p_win(self, ratio_eff: float, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        k = self.cfg.win_slope
        if self.cfg.day_kalman:
            # The mixture of both hypotheses, each widened by its own uncertainty (probit approximation).
            b = self.base_for(dealer, day, place, lane)
            return sum(w * sigmoid(k * (b + d - ratio_eff) / math.sqrt(1 + math.pi * k * k * v / 8)) for w, d, v in self.kal_day(day))
        return sigmoid(k * (self.mu_for(dealer, day, place, lane) - ratio_eff))

    def p_price(self, ratio_eff: float, dealer: str, day: int, place: str = "", lane: str = "") -> float:
        """P(win) for pricing: with mu_w, today's, the dealer's and the lane's parts count only partly (they over-react)."""
        if self.cfg.ucb and not self.cfg.day_kalman and not self.cfg.mu_w:
            sig, n1, n2, mu_min = self.cfg.ucb
            n = self.dealer_n.get(dealer, 0)
            kap = 1.0 if n < n1 else 0.5 if n < n2 else 0.0
            bump = kap * sig if self.mu > mu_min else 0.0
            return sigmoid((self.cfg.price_slope or self.cfg.win_slope) * (self.mu_for(dealer, day, place, lane) + bump - ratio_eff))
        if (self.cfg.price_slope and not self.cfg.day_kalman and not self.cfg.mu_w
                and (not self.cfg.price_slope_mu or self.mu >= self.cfg.price_slope_mu)):
            return sigmoid(self.cfg.price_slope * (self.mu_for(dealer, day, place, lane) - ratio_eff))
        if not self.cfg.mu_w or self.cfg.day_kalman:
            return self.p_win(ratio_eff, dealer, day, place, lane)
        wd, wl, wn = self.cfg.mu_w
        mu = (self.mu + wd * self.day_shift[day] + wl * self.dealer_shift[dealer] + self.place_shift.get((place, day), 0.0)
              + wn * self.cfg.lane_w * lane_shift(lane))
        return sigmoid(self.cfg.win_slope * (mu - ratio_eff))

    def kal_observe(self, day: int, b: float, ratio_eff: float, won: bool) -> float:
        """One result: weigh each hypothesis by how well it predicted it, then one EKF step on each. Returns P(war)."""
        k, y = self.cfg.win_slope, 1.0 if won else 0.0
        hs = self.kal_day(day)
        for h in hs:
            w, d, v = h
            pp = sigmoid(k * (b + d - ratio_eff) / math.sqrt(1 + math.pi * k * k * v / 8))
            h[0] = w * (pp if won else 1 - pp)
            p = sigmoid(k * (b + d - ratio_eff))
            hh = k * k * p * (1 - p)
            v2 = v / (1 + hh * v)
            h[1], h[2] = d + v2 * k * (y - p), v2
        tot = sum(h[0] for h in hs) or 1.0
        for h in hs:
            h[0] = max(1e-6, h[0] / tot)
        return hs[1][0]

    def observe(self, at: int, dealer: str, ratio_eff: float, won: bool, place: str = "", lane: str = "") -> None:
        day = at // DAY
        g = (1.0 if won else 0.0) - self.p_win(ratio_eff, dealer, day, place, lane)
        self.dealer_n[dealer] = self.dealer_n.get(dealer, 0) + 1
        k = self.cfg.win_slope
        if self.cfg.day_kalman:
            # The day level lives in the two hypotheses; the world and dealer levels learn less while a war is likely,
            # so a war day's losses do not drag tomorrow's prices down.
            pw = self.kal_observe(day, self.base_for(dealer, day, place, lane), ratio_eff, won)
            self.mu = min(max(self.mu + self.cfg.mu_lr * k * g * (1 - pw), 0.95), 1.9)
            self.dealer_shift[dealer] = min(max(self.dealer_shift[dealer] + self.cfg.dealer_lr * k * g * (1 - pw), -0.3), 0.3)
            self.n_obs += 1
            self.day_obs[day].append(won)
            return
        if self.cfg.outage_z and place and 8 * HOUR <= at % DAY < 18 * HOUR:
            if self.in_outage(day, place, at):
                self.n_obs += 1
                return  # the outage region's dealers pay the backup's price today: nothing to learn for the rest of the world
            # Evidence for "this region pays the backup's price": log-likelihood of the result at level x (1 + outage_up) vs as is.
            p0 = min(1 - 1e-6, max(1e-6, (1.0 if won else 0.0) - g))
            p1 = min(1 - 1e-6, max(1e-6, sigmoid(k * (self.mu_base(dealer, day, place, lane) * (1 + self.cfg.outage_up) - ratio_eff))))
            llr = math.log(p1 / p0) if won else math.log((1 - p1) / (1 - p0))
            for c, _ in self.desk.nearby(place):
                a = self.out_acc.setdefault((day, c), [0.0, 0.0, 0])
                a[0] += llr
                a[2] += 1
                if (day not in self.outage and a[2] >= self.cfg.outage_min and self.day_shift[day] > -self.cfg.war_shift
                        and a[0] >= self.cfg.outage_z):
                    self.outage[day] = c
                    self.desk.say("OUTAGE", f"day {day} region {c} llr={a[0]:.1f} n={a[2]}")
        if self.cfg.dist_lr:
            self.beta = min(0.4, max(-0.4, self.beta + self.cfg.dist_lr * k * g * self.dist_x(lane)))
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
            ev = self.p_price(r, dealer, day, place, lane) * (price * (1 - risk_frac) - cost - shadow)
            if ev > best_ev:
                best, best_ev = r, ev
            r += 0.01
        return best, best_ev

    def speed_offset(self, kind: str) -> int:
        """The dealer's euros for speed below same_day: what a slower option's threshold lacks."""
        a, b = self.cfg.speed_cents
        return {"same_day": 0, "next_day": a}.get(kind, a + b)

    def best_menu(self, dealer: str, day: int, list_fast: int, tf: float, cost: float, cands: list, place: str = "", lane: str = "") -> tuple[dict, float]:
        """Menu pricing: the dealer compares options by price + speed offset, so P(win) follows the lowest such price.
        Search that effective price; at each, the option with the best margin sets it; the others get the same margin."""
        cfg = self.cfg
        s0 = min(c[2] for c in cands)
        best, best_ev, best_m = None, 0.0, 0.0
        r = cfg.min_ratio
        while r <= cfg.max_ratio + 1e-9:
            eff = list_fast * r * tf
            m = max(((eff - (s - s0) * tf) * (1 - risk) - cost - extra for _, lst, s, risk, extra in cands if eff - (s - s0) * tf >= lst * cfg.min_ratio * tf), default=None)
            if m is not None:
                ev = (self.p_price if (self.cfg.price_slope or self.cfg.ucb) else self.p_win)(r, dealer, day, place, lane) * m
                if ev > best_ev:
                    best, best_ev, best_m = r, ev, m
            r += 0.01
        if best is None:
            return {}, 0.0
        prices = {}
        for kind, lst, s, risk, extra in cands:
            p = (best_m + cost + extra) / (1 - risk)
            p = max(p, list_fast * best * tf - (s - s0) * tf, lst * cfg.min_ratio * tf)
            if p <= lst * cfg.max_ratio * tf:
                prices[kind] = int(round(p))
        return prices, best_ev


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

    def projection(self, stuck: bool = True) -> float:
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
                c = d.cfg
                if stuck and c.gov_stuck_p and any((g := d.leg_gig.get((oid, l))) and d.gigs[g].status == "open"
                                                   and d.now - d.gigs[g].posted_at >= c.gov_stuck_age for l in legs):
                    # Nobody booked it for an hour. Measured: 30-40% late with under a day to its last pickup, 15-20% with more.
                    near = d.last_pickup(ob, legs) - d.now <= c.gov_stuck_left
                    cap = c.gov_stuck_p if near else (c.gov_stuck_far or 1.0)
                    p = min(p, cap)
            open_p += p
        total = ontime + late + n_open
        pf = d.cfg.proj_future
        if pf and total:
            # Self-lock fix: the share the bar can still recover to, counting the cars this week's pace would add by Friday night.
            elapsed = min(5.0, d.now / DAY)
            if elapsed >= 0.5:
                k = min(float(total), total / elapsed * max(0.0, 5.0 - elapsed))
                return (ontime + open_p + pf * k) / (total + k)
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
