"""One fee per gig, chosen from a clearing-fee model of the car (flag fee1). The leaders' mechanism, replacing the opening + ladder
for single cars.

Every car has one clearing fee c: at a flat fee m it books before the deadline warning iff m >= c (PROBE's counterfactual forks:
the same gig replayed at 0.85/0.95/1.05/1.2x is monotone for every car; research/re/probe/CURVE.md). Across cars ln c is normal:

    ln c ~ N(mu(x) + delta, sigma),   mu(x) linear in ln(1 + drivers near the delivery), ln(lead hours), ln(drive), ...

fitted on those forks (fee1_clear). delta is this week's offset, learned live from our own posts (booked at m: c <= m; sat unbooked
until the re-pick or the alarm: c > m), so a week where drivers are scarce raises the fees by itself (Halal's learned intercept).

A gig's fee is one decision: the m that minimises the expected cost of moving the car,

    E(m) = P1(m) m typ + (1 - P1(m)) V2(m) + harm(m),

P1 = P(c <= m) x the share of bookings that come inside the first window; V2(m) = the best re-pick (a withdraw + new post after
fee1_repick minutes, which notifies drivers again; only fees above m can book a car that did not book at m), or with no time for one
the rescue at our alarm: 1.31x typical and 19% late, priced at the desk's late cost (k-safe-dcl, research/re/fleet/rescue_cost.py).
harm(m): a fee above the going fee of our other waiting gigs near the pickup pulls drivers off them (Halal's fee weighs 3.96 on its
fee over the going level, 0.88 on the level; without the term they paid 1.12x instead of 0.94x, -EUR 2,967/wk).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .geo import DAY

if TYPE_CHECKING:
    from .desk import Desk, GigRec, OrderBook

WARN = 180  # the world's deadline warning: 3 h before lastPickupAt (deadline_close.at = lastPickupAt - 180 in every reveal)
DAY_FROM, DAY_TO = 7 * 60, 22 * 60  # drivers plan in the day: no re-pick posted at night (RoutePulse: no steps 22:45-07:05)


def phi(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def Phi(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2))


def day_minutes(a: int, b: int) -> int:
    """Minutes of [a, b) between DAY_FROM and DAY_TO of each day."""
    n, t = 0, a
    while t < b:
        d0 = (t // DAY) * DAY
        lo, hi = d0 + DAY_FROM, d0 + DAY_TO
        n += max(0, min(b, hi) - max(t, lo))
        t = d0 + DAY
    return n


def repick_at(posted: int, N: int) -> int:
    """When a gig posted at `posted` is re-picked: N minutes later, moved to the next DAY_FROM if that falls at night."""
    t = posted + N
    m = t % DAY
    if m < DAY_FROM:
        return t - m + DAY_FROM
    if m >= DAY_TO:
        return t - m + DAY + DAY_FROM
    return t


class Fee1:
    def __init__(self, desk: "Desk"):
        self.desk = desk
        self.delta = 0.0      # this week's offset of ln(clearing fee)
        self.d_at = -1
        self.obs: dict[str, tuple[float, int]] = {}  # closed first posts: gig -> (z at posting without delta, booked 0/1)
        self.done: set[str] = set()
        self._w: dict[str, tuple[int, float]] = {}   # gig -> (world hour, its harm weight)

    # ------------------------------------------------------------------ features
    def others(self, p: str, skip: Optional[str] = None, ids: Optional[list] = None) -> list[float]:
        """Current fee / typical of our other open unbooked gigs whose first pickup is <= 60 road min from p (ids: their gig ids)."""
        from .desk import current_fee
        d = self.desk
        near = []
        for gid in sorted(d.gigs):
            rec = d.gigs[gid]
            if rec.status != "open" or gid == skip:
                continue
            ob = d.orders.get(rec.legs[0][0])
            if not ob:
                continue
            p2 = ob.order["legs"][rec.legs[0][1]]["pickup"]["placeId"]
            if d.geo.drive(p2, p) <= 60:
                near.append(current_fee(rec.schedule, d.now) / max(1.0, d.gig_base(rec)))
                if ids is not None:
                    ids.append(gid)
        return near

    def posts(self, oid: str, legs: list[int]) -> int:
        """Single-order gigs we posted for these legs of the order (the re-pick cap counts them; restart-proof)."""
        n = 0
        for gid in sorted(self.desk.gigs):
            rec = self.desk.gigs[gid]
            if {o for o, _ in rec.legs} == {oid} and any(l in legs for _, l in rec.legs):
                n += 1
        return n

    def prior_miss(self, oid: str, legs: list[int], before: int) -> Optional["GigRec"]:
        """The latest single gig of these legs withdrawn before `before` without ever being booked (a re-pick): the car did not
        clear at its fee. A gig withdrawn after a drop had a booking (rec.fee > 0) and says nothing about the clearing fee."""
        best = None
        for gid in sorted(self.desk.gigs):
            rec = self.desk.gigs[gid]
            if (rec.status == "withdrawn" and not rec.fee and rec.posted_at < before and len(rec.schedule) == 1
                    and {o for o, _ in rec.legs} == {oid} and any(l in legs for _, l in rec.legs)):
                if best is None or rec.posted_at > best.posted_at:
                    best = rec
        return best

    def mu(self, ob: "OrderBook", legs: list[int], at: int) -> float:
        """mu(x): the car's expected ln clearing fee when posted at `at` (fee1_clear: PROBE's fit on counterfactual forks)."""
        d, cfg = self.desk, self.desk.cfg
        o = ob.order
        L0, L1 = o["legs"][legs[0]], o["legs"][legs[-1]]
        p, q = L0["pickup"]["placeId"], L1["delivery"]["placeId"]
        drive = sum(d.geo.drive(o["legs"][l]["pickup"]["placeId"], o["legs"][l]["delivery"]["placeId"]) for l in legs)
        lead_h = max(1.0, (d.last_pickup(ob, legs) - at) / 60)
        b0, b_nd, b_np, b_lead, b_drive, b_fri, b_priv, b_prem, _ = cfg.fee1_clear
        priv = bool(L0["pickup"]["privateAddress"] or L1["delivery"]["privateAddress"])
        return (b0 + b_nd * math.log1p(d.home_near_delivery(q, 30)) + b_np * math.log1p(d.home_near_delivery(p, 30))
                + b_lead * math.log(lead_h) + b_drive * math.log(max(5, drive)) + b_fri * float(at // DAY >= 4)
                + b_priv * float(priv) + b_prem * float(any(o["legs"][l]["car"]["premium"] for l in legs)))

    # ------------------------------------------------------------------ the decision
    def window(self, minutes: float) -> float:
        """Share of a post's eventual bookings that come within `minutes` of daytime: most at first sight (10% of a post's views
        in its first 5 min book, < 1% after 2 h; PROBE: booked within 1 h is 0.6-0.9 of booked before the warning)."""
        if minutes <= 0:
            return 0.0
        if minutes < 60:
            return 0.7 * minutes / 60
        return 1.0 - 0.3 * math.exp(-(minutes - 60) / 240)

    def plan(self, ob: "OrderBook", legs: list[int], last: int, base: float, desert: bool) -> Optional[tuple]:
        """(fee m, expected cost in cents, P1(m), the first window's end, V2(m), info), or None with too little time before the alarm."""
        d, cfg = self.desk, self.desk.cfg
        alarm = max(cfg.alarm_minutes, cfg.desert_alarm) if desert else cfg.alarm_minutes
        t_alarm = last - alarm
        if t_alarm - d.now < cfg.fee1_min_minutes:
            return None
        self.calibrate()
        sig = (cfg.fee1_sigma or cfg.fee1_clear[-1])
        oid = ob.order["id"]
        price = ob.order.get("priceCents") or 2 * base
        r_fee, r_late = cfg.fee1_rescue
        v_res = r_fee * base + r_late * cfg.late_cost_frac * price
        drive = sum(d.geo.drive(ob.order["legs"][l]["pickup"]["placeId"], ob.order["legs"][l]["delivery"]["placeId"]) for l in legs)
        if cfg.fee1_long_ladder and cfg.fee1_long and drive >= cfg.fee1_long[0]:
            return None  # long cars keep the ladder: long_warn was built on how they book under it (k-f1h5's bad weeks: +12..+83 long declines)
        if cfg.fee1_only and ((last - d.now) / 60 < cfg.fee1_only[0]
                              or d.home_near_delivery(ob.order["legs"][legs[-1]]["delivery"]["placeId"], 30) < cfg.fee1_only[1]):
            return None  # narrow fee1: only cars with time and drivers near the delivery (where its cheap fees are); the rest keep the ladder
        floor = max(cfg.fee1_desert_floor if desert else 0.0, cfg.fee1_long[1] if cfg.fee1_long and drive >= cfg.fee1_long[0] else 0.0)
        grid = [m for m in cfg.fee1_grid if m >= floor] or [max(cfg.fee1_grid)]
        mu1 = self.mu(ob, legs, d.now) + self.delta
        # A car that sat unbooked at fee m0: its residual is above (ln m0 - mu0) / sigma, it books now only above that
        miss = self.prior_miss(oid, legs, d.now)
        e_min = -9.0
        if miss is not None:
            m0 = miss.schedule[0]["feeCents"] / max(1.0, base)
            e_min = (math.log(m0) - self.mu(ob, legs, miss.posted_at) - self.delta) / sig
        tail = 1.0 - Phi(e_min)

        def p_clear(m: float, mu_: float) -> float:
            z = (math.log(m) - mu_) / sig
            return max(0.0, Phi(z) - Phi(e_min)) / max(1e-9, tail)

        t1 = repick_at(d.now, cfg.fee1_repick) if cfg.fee1_repick else t_alarm
        stage2 = (cfg.fee1_repick and t_alarm - t1 >= cfg.fee1_min_minutes + (cfg.fee1_last_call or 0)
                  and self.posts(oid, legs) + 1 < cfg.fee1_max_posts)
        if not stage2:
            t1 = t_alarm
        w1 = self.window(day_minutes(d.now, t1))
        A, going = self.harm(ob.order["legs"][legs[0]]["pickup"]["placeId"]) if cfg.fee1_harm else (0.0, 1.0)
        mu2 = self.mu(ob, legs, t1) + self.delta if stage2 else mu1
        w2 = self.window(day_minutes(t1, t_alarm)) if stage2 else 0.0
        best = None
        for m in grid:
            pc = p_clear(m, mu1)
            p1 = pc * w1
            if stage2:
                # Not booked at m: either it did not clear (residual above m's) or it clears but was slow; the re-pick books it at m2
                # if m2 clears it. Approximation: the re-pick sees the car's residual above max(m's, e_min) with weight of the misses.
                z_m = (math.log(m) - mu1) / sig
                lo = max(e_min, z_m)
                v2 = v_res
                for m2 in grid:
                    if m2 < m:
                        continue
                    z2 = (math.log(m2) - mu2) / sig
                    miss_clear = 1 - Phi(lo)               # P(residual above m's | ...) * tail (unnormalised)
                    slow = pc * (1 - w1) * tail            # cleared at m but did not book inside the window (unnormalised)
                    tot = miss_clear + slow
                    pb = ((max(0.0, Phi(z2) - Phi(lo)) + slow) / tot if tot > 1e-12 else 0.0) * w2
                    v2 = min(v2, pb * m2 * base + (1 - pb) * v_res)
            else:
                v2 = v_res
            e = p1 * m * base + (1 - p1) * v2 + cfg.fee1_harm * A * (m - going) / going
            if best is None or e < best[1] - 1e-9:
                best = (m, e, p1, t1, v2)
        info = {"mu": mu1, "delta": self.delta, "harm": A, "going": going, "miss": miss is not None, "w1": w1}
        return best + (info,)

    def choose(self, ob: "OrderBook", legs: list[int], last: int, base: float, desert: bool) -> Optional[tuple[float, str]]:
        """(fee multiplier, reason) for a new post, or None: too little time for a choice (the ladder and alarm take it)."""
        pl = self.plan(ob, legs, last, base, desert)
        if pl is None:
            return None
        m, e, p1, t1, v2, info = pl
        b = max(1.0, base)
        return m, (f"m={m:.2f} p1={p1:.2f} t1={t1} E={e / b:.3f} V2={v2 / b:.3f} c50={math.exp(info['mu']):.2f} d={info['delta']:+.3f} "
                   f"harm={info['harm'] / b:.2f} going={info['going']:.2f} w1={info['w1']:.2f}{' repick' if info['miss'] else ''}")

    def quote_cost(self, r: dict, opt: dict) -> Optional[tuple[float, float]]:
        """For the quote (MARKET): (fee m, expected fee + rescue cost in cents) of moving this request's car alone if we win this
        option and post it now. Single-leg requests only (None otherwise or with too little time)."""
        from .desk import OrderBook
        d = self.desk
        if len(r["legs"]) != 1:
            return None
        last = d.est_last_pickup(r, opt["deadline"])
        order = {"id": r["id"], "legs": r["legs"], "lastPickupAt": last, "priceCents": opt["listPriceCents"]}
        q = r["legs"][0]["delivery"]["placeId"]
        pl = self.plan(OrderBook(order, d.now), [0], last, float(r["referenceFeeCents"]), bool(d.cfg.desert_n and d.desert(q)))
        return None if pl is None else (pl[0], pl[1])

    # ------------------------------------------------------------------ harm to our other waiting gigs
    def harm_weight(self, gid: str) -> float:
        """What our open gig `gid` loses, in cents, per unit of log(going fee near it): the relative share of its booking chance's
        elasticity to its fee (fee1_rel_share of phi(z) / sigma) times what its failing costs (rescue instead of its fee)."""
        d, cfg = self.desk, self.desk.cfg
        hit = self._w.get(gid)
        if hit and hit[0] == d.now // 60:
            return hit[1]
        from .desk import current_fee
        w = 0.0
        rec = d.gigs[gid]
        ob = d.orders.get(rec.legs[0][0])
        if ob and len({o for o, _ in rec.legs}) == 1 and not rec.escalated:
            legs = [l for _, l in rec.legs]
            base = d.base_fee(ob, legs)
            m = current_fee(rec.schedule, d.now) / max(1.0, base)
            sig = (cfg.fee1_sigma or cfg.fee1_clear[-1])
            z = (math.log(max(0.05, m)) - self.mu(ob, legs, rec.posted_at) - self.delta) / sig
            price = ob.order.get("priceCents") or 2 * base
            r_fee, r_late = cfg.fee1_rescue
            fail = r_fee * base + r_late * cfg.late_cost_frac * price - m * base
            w = cfg.fee1_rel_share * phi(z) / sig * max(0.0, fail)
        self._w[gid] = (d.now // 60, w)
        return w

    def harm(self, p: str) -> tuple[float, float]:
        """(A, going): a new gig at fee m near pickup p costs our open gigs within 60 road min about A * (m - going) / going cents.
        Adding it moves their going fee (the mean) by (m - going) / (n + 1); each loses its harm_weight times that log change."""
        ids: list = []
        near = self.others(p, ids=ids)
        if not near:
            return 0.0, 1.0
        going = sum(near) / len(near)
        return sum(self.harm_weight(g) for g in ids) / (len(ids) + 1), going

    # ------------------------------------------------------------------ this week's offset
    def z0(self, rec: "GigRec") -> Optional[float]:
        """z of a fee1 first post at its posting, without this week's offset."""
        d = self.desk
        ob = d.orders.get(rec.legs[0][0])
        if not ob:
            return None
        legs = [l for _, l in rec.legs]
        m = rec.schedule[0]["feeCents"] / max(1.0, d.base_fee(ob, legs))
        return (math.log(max(0.05, m)) - self.mu(ob, legs, rec.posted_at)) / (d.cfg.fee1_sigma or d.cfg.fee1_clear[-1])

    def close(self, rec: "GigRec", booked: bool, at: int) -> None:
        """A fee1 gig's flat exposure ended (booked, withdrawn for a re-pick, or escalated at the alarm). First posts are this
        week's evidence on the clearing fee (re-picks are conditional on the miss before them: not used)."""
        if rec.id in self.done:
            return
        self.done.add(rec.id)
        try:
            ob = self.desk.orders.get(rec.legs[0][0])
            if not ob or self.prior_miss(ob.order["id"], [l for _, l in rec.legs], rec.posted_at) is not None:
                return
            z = self.z0(rec)
            if z is not None:
                self.obs[rec.id] = (z, rec.posted_at, at if booked else None, at)
        except Exception as exc:  # the offset must never stop the desk
            self.desk.say("ERR", f"fee1 close {type(exc).__name__}: {exc}")

    def booked_after_all(self, gid: str) -> None:
        """A re-pick's withdraw was refused: a driver booked the gig first, so it did clear at its fee."""
        try:
            if gid in self.obs:
                z, posted, _, closed = self.obs[gid]
                self.obs[gid] = (z, posted, closed, closed)
        except Exception as exc:  # never stop the desk
            self.desk.say("ERR", f"fee1 booked_after_all {type(exc).__name__}: {exc}")

    def calibrate(self) -> None:
        """delta: the week's offset of ln(clearing fee), by Newton steps on the probit likelihood of "booked within the first
        fee1_obs_minutes daytime minutes" of our first posts, P = window(W) Phi(z - delta / sigma), with a normal prior; only
        posts whose W has passed (or that booked inside it), so fast bookings do not count before the slow misses can;
        older posts weigh less (half-life fee1_delta[2] min), so the offset follows the week's days. Once per world hour."""
        d, cfg = self.desk, self.desk.cfg
        if d.now // 60 == self.d_at:
            return
        self.d_at = d.now // 60
        sig = (cfg.fee1_sigma or cfg.fee1_clear[-1])
        W = cfg.fee1_obs_minutes
        prior_sd, lim, half = cfg.fee1_delta
        xs = []
        for gid in sorted(self.obs):
            z, posted, booked_at, closed = self.obs[gid]
            if booked_at is not None and day_minutes(posted, booked_at) <= W:
                b = 1
            elif day_minutes(posted, closed) >= W:
                b = 0
            else:
                continue  # closed unbooked before its window was over: no verdict
            xs.append((z, b, 0.5 ** ((d.now - posted) / half)))
        for gid in sorted(d.gigs):  # open first posts that already sat a full window count as misses
            rec = d.gigs[gid]
            if (rec.status == "open" and gid not in self.done and d.fee1_gig(rec)
                    and day_minutes(rec.posted_at, d.now) >= W):
                ob = d.orders.get(rec.legs[0][0])
                if ob and self.prior_miss(ob.order["id"], [l for _, l in rec.legs], rec.posted_at) is None:
                    z = self.z0(rec)
                    if z is not None:
                        xs.append((z, 0, 0.5 ** ((d.now - rec.posted_at) / half)))
        w = self.window(W)
        u = self.delta / sig  # offset in z units: P(booked within W) = w Phi(z - u)
        k = (sig / prior_sd) ** 2
        for _ in range(8):
            g, h = -u * k, -k
            for z, b, wt in xs:
                t = z - u
                f = phi(t)
                if b:
                    r = f / max(1e-9, Phi(t))              # d/du ln(w Phi(t)) = -r
                    g -= wt * r
                    h -= wt * r * (r + t)
                else:
                    r = w * f / max(1e-9, 1 - w * Phi(t))  # d/du ln(1 - w Phi(t)) = r
                    g += wt * r
                    h -= wt * r * (r - t)
            if h >= -1e-9:
                break
            u = max(-lim / sig, min(lim / sig, u - g / h))
        self.delta = max(-lim, min(lim, u * sig))
