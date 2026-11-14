"""One fee per gig, chosen from a booking model (flag fee1). The leaders' mechanism, replacing the opening + ladder for single cars.

Drivers are notified of new posts, not of raises (a raise of a sitting gig reaches ~1 view), and book trips that end near home. So a
gig's fee is one decision: the fee m (x typical) that minimises the expected cost of moving the car,

    E(m) = P1(m) * m * typ + (1 - P1(m)) * V_next,

where P1(m) = P(booked within the first window | m) comes from the booking model (book_gbm: a booking hazard fitted on our played
weeks), V_next is the expected cost of the re-pick (a new post at a newly chosen fee after fee1_repick minutes: a new notification)
or, with no time for one, of the rescue at our alarm: rescue fee + P(late | rescued) x the desk's late cost.
Measured rescue (24 k-safe-dcl weeks, research/re/fleet/rescue_cost.py): cars booked 6-3 h before the last pickup paid 1.27x, 1.8%
late; after the 3 h warning 1.39x, 55% late; together about 1.31x and 19% late.

The model's hazard is scaled by this week's calibration k = (bookings + a) / (predicted cumulative hazard + a) over our fee1 gigs,
so a week where drivers are scarcer than the model thinks raises the fees by itself.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .geo import DAY

if TYPE_CHECKING:
    from .desk import Desk, GigRec, OrderBook

WARN = 180  # the world's deadline warning: 3 h before lastPickupAt (deadline_close.at = lastPickupAt - 180 in every reveal)


def _model():
    from . import book_gbm
    return book_gbm


class Fee1:
    def __init__(self, desk: "Desk"):
        self.desk = desk
        self._np: dict[tuple[str, int], int] = {}
        self.k = 1.0
        self.k_at = -1
        self.closed_h = 0.0   # predicted cumulative hazard of finished fee1 exposures (uncalibrated)
        self.closed_n = 0     # and their bookings
        self.done: set[str] = set()
        self.picks: dict[str, int] = {}  # order -> fee1 posts so far (re-picks are capped)

    # ------------------------------------------------------------------ features (as research/re/fleet/book_data.py)
    def home_near_pickup(self, place: str, minutes: int) -> int:
        key = (place, minutes)
        if key not in self._np:
            d = self.desk
            self._np[key] = sum(c for h, c in sorted(d.home_count.items()) if d.geo.drive(h, place) <= minutes)
        return self._np[key]

    def others(self, p: str, skip: Optional[str] = None) -> tuple[list[float], int]:
        """Current fee / typical of our other open unbooked gigs whose first pickup is <= 60 road min from p; and all open gigs."""
        from .desk import current_fee
        d = self.desk
        near, n_open = [], 0
        for gid in sorted(d.gigs):
            rec = d.gigs[gid]
            if rec.status != "open" or gid == skip:
                continue
            n_open += 1
            ob = d.orders.get(rec.legs[0][0])
            if not ob:
                continue
            p2 = ob.order["legs"][rec.legs[0][1]]["pickup"]["placeId"]
            if d.geo.drive(p2, p) <= 60:
                near.append(current_fee(rec.schedule, d.now) / max(1.0, d.gig_base(rec)))
        return near, n_open

    def features(self, ob: "OrderBook", legs: list[int], last: int, at: int, skip: Optional[str] = None) -> dict:
        d = self.desk
        o = ob.order
        L0, L1 = o["legs"][legs[0]], o["legs"][legs[-1]]
        p, q = L0["pickup"]["placeId"], L1["delivery"]["placeId"]
        drive = sum(d.geo.drive(o["legs"][l]["pickup"]["placeId"], o["legs"][l]["delivery"]["placeId"]) for l in legs)
        near, n_open = self.others(p, skip)
        near.sort()
        med = (near[(len(near) - 1) // 2] + near[len(near) // 2]) / 2 if near else float("nan")
        wl = o.get("lastPickupAt") or last  # the world's lastPickupAt, which the trees were fitted on (notes' deadlines aside)
        return {
            "fee_typ": 1.0, "_med": med, "fee_rel": float("nan"), "n_open_near": len(near), "n_open": n_open,
            "elapsed": 0.0, "raised": 0.0, "left_h": (wl - at) / 60, "to_warn_h": (wl - WARN - at) / 60,
            "hour": (at % DAY) / 60, "wday": at // DAY, "drive": drive, "cars": 1, "legs": len(o["legs"]),
            "priv": float(L0["pickup"]["privateAddress"]), "priv_d": float(L1["delivery"]["privateAddress"]),
            "premium": float(any(o["legs"][l]["car"]["premium"] for l in legs)), "same_town": float(p == q),
            "nd30": d.home_near_delivery(q, 30), "nd60": d.home_near_delivery(q, 60), "nd120": d.home_near_delivery(q, 120),
            "np30": self.home_near_pickup(p, 30), "np60": self.home_near_pickup(p, 60), "roster": len(d.roster),
            "typ": d.base_fee(ob, legs) / 100,
        }

    # ------------------------------------------------------------------ the decision
    def p_book(self, x: dict, m: float, horizon: float, start_elapsed: float = 0.0) -> float:
        """P(booked within horizon minutes at a flat fee m), the model's hazard scaled by this week's calibration k."""
        if horizon <= 0:
            return 0.0
        y = dict(x)
        y["fee_typ"] = m
        y["fee_rel"] = m / x["_med"] if x["_med"] == x["_med"] and x["_med"] > 0 else float("nan")
        p = _model().p_book(y, m, horizon, start_elapsed)
        h = -math.log(max(1e-9, 1.0 - min(p, 1 - 1e-9)))
        return 1.0 - math.exp(-self.k * h)

    def choose(self, ob: "OrderBook", legs: list[int], last: int, base: float, desert: bool) -> Optional[tuple[float, str]]:
        """(fee multiplier, reason) for a new post, or None: too little time for a choice (the ladder and alarm take it)."""
        d, cfg = self.desk, self.desk.cfg
        alarm = max(cfg.alarm_minutes, cfg.desert_alarm) if desert else cfg.alarm_minutes
        T = (last - alarm) - d.now
        if T < cfg.fee1_min_minutes:
            return None
        self.calibrate()
        price = ob.order.get("priceCents") or 2 * base
        r_fee, r_late = cfg.fee1_rescue
        v_res = r_fee * base + r_late * cfg.late_cost_frac * price
        grid = [m for m in cfg.fee1_grid if not (desert and m < cfg.fee1_desert_floor)] or [cfg.fee1_desert_floor]
        x = self.features(ob, legs, last, d.now)
        N = cfg.fee1_repick
        v_next, T1 = v_res, T
        if N and T > N + cfg.fee1_min_minutes and self.picks.get(ob.order["id"], 0) + 1 < cfg.fee1_max_posts:
            x2 = self.features(ob, legs, last, d.now + N)
            x2["n_open"], x2["n_open_near"], x2["_med"] = x["n_open"], x["n_open_near"], x["_med"]
            v_next = min(self.p_book(x2, m, T - N) * m * base + (1 - self.p_book(x2, m, T - N)) * v_res for m in grid)
            T1 = N
        best = None
        for m in grid:
            p1 = self.p_book(x, m, T1)
            e = p1 * m * base + (1 - p1) * v_next
            if best is None or e < best[0] - 1e-9:
                best = (e, m, p1)
        e, m, p1 = best
        return m, f"m={m:.2f} p1={p1:.2f} T1={T1} E={e / max(1.0, base):.3f} Vn={v_next / max(1.0, base):.3f} k={self.k:.2f} nd30={x['nd30']} med={x['_med']:.2f}"

    # ------------------------------------------------------------------ this week's calibration
    def exposure_h(self, rec: "GigRec", until: int) -> float:
        """Predicted cumulative hazard (uncalibrated) of a fee1 gig from its post to `until` at its posted fee."""
        d = self.desk
        ob = d.orders.get(rec.legs[0][0])
        if not ob or until <= rec.posted_at:
            return 0.0
        legs = [l for _, l in rec.legs]
        last = d.last_pickup(ob, legs)
        x = self.features(ob, legs, last, rec.posted_at, skip=rec.id)
        m = rec.schedule[0]["feeCents"] / max(1.0, d.base_fee(ob, legs))
        x["fee_typ"] = m
        x["fee_rel"] = m / x["_med"] if x["_med"] == x["_med"] and x["_med"] > 0 else float("nan")
        p = _model().p_book(x, m, until - rec.posted_at, 0.0)
        return -math.log(max(1e-9, 1.0 - min(p, 1 - 1e-9)))

    def close(self, rec: "GigRec", booked: bool, at: int) -> None:
        """A fee1 gig's flat exposure ended (booked, withdrawn for a re-pick, or escalated at the alarm)."""
        if rec.id in self.done:
            return
        self.done.add(rec.id)
        try:
            self.closed_h += self.exposure_h(rec, at)
            self.closed_n += int(booked)
        except Exception as exc:  # the calibration must never stop the desk
            self.desk.say("ERR", f"fee1 close {type(exc).__name__}: {exc}")

    def calibrate(self) -> None:
        """k = (bookings + a) / (predicted hazard + a), over closed fee1 exposures and the open ones so far; once per world hour."""
        d, cfg = self.desk, self.desk.cfg
        if d.now // 60 == self.k_at:
            return
        self.k_at = d.now // 60
        h, n = self.closed_h, self.closed_n
        for gid in sorted(d.gigs):
            rec = d.gigs[gid]
            if rec.status == "open" and self.desk.fee1_gig(rec) and gid not in self.done:
                h += self.exposure_h(rec, d.now)
        a = cfg.fee1_prior
        self.k = min(cfg.fee1_k_range[1], max(cfg.fee1_k_range[0], (n + a) / (h + a)))
