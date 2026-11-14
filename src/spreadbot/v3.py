"""V3: the volume engine. Three decisions replace c3's; the desk's books, notes, holds, restarts and rescue stay.

1. Quote: win every car whose expected margin covers its own fleet cost. A late car costs its refund, a little
   goodwill, and a barrier price that is near zero while the week's projected on-time share is safe and steep near
   the target. No load shadow price, no governor bar: those charged twice for the same scarcity (Halal: reserve
   0.3 -> 0 gave 207 -> 342 orders). Every option is quoted at the same euro margin, so whichever one the dealer
   takes pays the same (dealers buy the option with the largest threshold minus price).
2. Fee: one flat fee per gig, chosen from FEE_GRID to minimise fee + P(late | fee) x cost of a late car. Drivers learn
   that rising fees rise and wait for them (organisers' /how; Halal's starter week), and above ~1.15x typical money
   buys no more bookings. P(late | fee) = our on-time model (fitted on c3's ladder, effective fee ~1.15x) scaled by
   Halal's measured booking curve.
3. Pairs and sitting cars come from flags (bundle_mult 0.70, repair pairs 0.85, second look) set by the v3 preset.
"""
from __future__ import annotations

from .desk import Desk, OrderBook, decline_prices, dedupe, lane_of
from .geo import DAY, HOUR

# Halal, randomised flat fees on 8 weeks: share of cars booked before the deadline warning at a flat fee (x typical).
# A car booked before the warning is on time 96% of the time, one that is not 25%: late share = 1 - (0.25 + 0.71 B).
BOOK_CURVE = ((0.70, 0.39), (0.85, 0.61), (1.00, 0.81), (1.15, 0.91), (1.30, 0.91), (1.50, 0.91))


def booked_share(m: float) -> float:
    pts = BOOK_CURVE
    if m <= pts[0][0]:
        return max(0.0, pts[0][1] * m / pts[0][0])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if m <= x1:
            return y0 + (y1 - y0) * (m - x0) / (x1 - x0)
    return pts[-1][1]


def late_ratio(m: float, anchor: float = 1.05) -> float:
    """Late share at flat fee m over the late share at the anchor fee (c3's opening fee, where its on-time model was fitted)."""
    late = lambda x: 1 - (0.25 + 0.71 * booked_share(x))  # noqa: E731
    return late(m) / late(anchor)


class V3Desk(Desk):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.v3_fee: dict[str, dict[str, float]] = {}  # request id -> option -> fee multiple chosen at the quote

    def barrier_cents(self) -> float:
        """Price of one more expected late car: ~0 while the projected on-time share is far above the target,
        v3_barrier at the target, 16x that at twice the allowed late share (Halal's barrier, alignas' sla_pressure)."""
        c = self.cfg
        used = (1 - self.v3_projection()) / max(1e-6, 1 - c.v3_target)
        return c.v3_barrier_cents * min(2.0, max(0.0, used)) ** 4

    def v3_projection(self) -> float:
        """The governor's projection with a prior of v3_prior_n orders on time at the target: four early wins at
        0.85 must not read as an 85% week and shut the desk for a day (smoke dev-07: Monday 241 of 252 declined)."""
        d, c = self, self.cfg
        n = len(d.ontime_orders) + len(d.late_orders) + sum(1 for o in d.orders if o not in d.ontime_orders and o not in d.late_orders)
        return (d.gov.projection() * n + c.v3_target * c.v3_prior_n) / (n + c.v3_prior_n)

    def p_late(self, p_ok: float, m: float) -> float:
        return min(0.95, (1 - p_ok) * late_ratio(m, self.cfg.v3_anchor))

    def best_fee(self, p_ok: float, typical: float, price: float, lam: float) -> tuple[float, float]:
        """(fee multiple, P(late)) minimising fee + P(late) x (refund + goodwill + barrier)."""
        c = self.cfg
        late_cost = c.v3_refund_frac * price + c.v3_late_cents + lam
        best = None
        for m in c.v3_fee_grid:
            pl = self.p_late(p_ok, m)
            total = m * typical + pl * late_cost
            if best is None or total < best[0]:
                best = (total, m, pl)
        return best[1], best[2]

    def price(self, r: dict) -> tuple[dict, str]:
        cfg = self.cfg
        if self.level <= 3 or cfg.experiment_quote:
            return super().price(r)
        dealer = r["dealerId"]
        tf = self.trust_factor(dealer)
        day = r["respondBy"] // DAY
        if cfg.max_per_batch and r.get("batchId") and self.batch_won[r["batchId"]] >= cfg.max_per_batch:
            return decline_prices(r), f"DECLINE batch {r['batchId']} full"
        place, lane = r["legs"][0]["pickup"]["placeId"], lane_of(r)
        lam = self.barrier_cents()
        proj = self.v3_projection()
        typical = float(r["referenceFeeCents"])
        cand = {}  # kind -> (price, cost at that price, ev, p_ok, m)
        info = []
        for opt in r["options"]:
            kind = opt["kind"]
            if kind not in cfg.quote_options:
                continue
            p_ok, slack = self.ontime.p_ok(r, opt["deadline"], kind)
            if slack < cfg.min_slack_h:
                info.append(f"{kind}:skip(s={slack:.1f})")
                continue
            guess = opt["listPriceCents"] * self.market.mu_for(dealer, day, place, lane) * tf
            m, pl = self.best_fee(p_ok, typical, guess, lam)
            if proj < cfg.v3_floor and pl > cfg.v3_floor_pl:
                info.append(f"{kind}:skip(floor pl={pl:.2f})")  # always ranked first: near the gate only safe cars
                continue
            fee = m * typical
            risk_frac = cfg.v3_refund_frac * pl
            shadow = pl * (cfg.v3_late_cents + lam)
            ratio, ev = self.market.best_ratio(dealer, day, opt["listPriceCents"], tf, fee, risk_frac, shadow, place, lane)
            if ratio <= 0 or ev < cfg.min_ev_cents:
                info.append(f"{kind}:noev(m={m:.2f},pl={pl:.2f})")
                continue
            price = opt["listPriceCents"] * ratio * tf
            cost = fee + risk_frac * price + shadow
            cand[kind] = (price, cost, ev, 1 - pl, m)
            info.append(f"{kind}:r={ratio:.2f},m={m:.2f},pl={pl:.2f},ev={ev / 100:.0f}")
        head = f"V3 lam={lam / 100:.0f} proj={proj:.3f} tf={tf:.2f} mu={self.market.mu_for(dealer, day, place, lane):.3f}"
        if not cand:
            return decline_prices(r), f"DECLINE {head} {' '.join(info)}"
        best = max(cand, key=lambda k: cand[k][2])
        margin = cand[best][0] - cand[best][1]
        lists = {o["kind"]: o["listPriceCents"] for o in r["options"]}
        prices = {}
        for kind, (price, cost, ev, p_ok, m) in cand.items():
            # Equal margin: the dealer picks by its own euros for speed, and every pick pays us the same.
            p = price if kind == best else max(cost + margin, lists[kind] * cfg.min_ratio * tf)
            prices[kind] = int(round(p))
        self.quote_meta[r["id"]] = {k: v[3] for k, v in cand.items()}
        self.v3_fee[r["id"]] = {k: v[4] for k, v in cand.items()}
        return prices, f"{head} best={best} {' '.join(info)}"

    def schedule(self, ob: OrderBook, legs: list[int]) -> list[dict]:
        """One flat fee, chosen now with the live barrier; the rescue (urgent, late, < 2 h) stays c3's."""
        last = self.last_pickup(ob, legs)
        if ob.urgent or last - self.now < 2 * HOUR or (self.cfg.late_plan and self.is_late(ob, legs)):
            return super().schedule(ob, legs)
        base = self.base_fee(ob, legs)
        o = ob.order
        r = self.requests.get(o["id"])
        p_ok = ob.p_ok
        if r is not None:
            opt = next((x for x in r["options"] if x["kind"] == o["option"]), None)
            if opt is not None:
                p_ok = self.ontime.p_ok(r, opt["deadline"], o["option"])[0]
        m, pl = self.best_fee(p_ok, base, float(o.get("priceCents", 0) or 0), self.barrier_cents())
        self.say("V3FEE", f"{o['id']} legs={legs} m={m:.2f} pl={pl:.2f}")
        out, prev = [{"at": self.now, "feeCents": max(1, int(round(base * m)))}], int(round(base * m))
        for hours_before, mult in self.cfg.fee_rel:
            # Late raises anchored to the last pickup (c3's): drivers wait only near the pickup, and they book the hard cars.
            fee = max(prev, int(round(base * mult)))
            out.append({"at": max(self.now + self.cfg.fee_hold, last - int(hours_before * HOUR)), "feeCents": fee})
            prev = fee
        return dedupe(sorted(out, key=lambda x: (x["at"], x["feeCents"])))

    def on_order_won(self, e: dict) -> None:
        super().on_order_won(e)
        ob = self.orders.get(e["order"]["id"])
        meta = self.quote_meta.get(e["order"]["id"], {})
        if ob is not None and e["order"]["option"] in meta:
            ob.p_ok = meta[e["order"]["option"]]  # the governor projects with the chance at the fee we will pay


def make_desk(geo, cfg, level: int, now: int, roster: list[dict]) -> Desk:
    """The engine the config names: c3's desk, or V3 on top of it."""
    cls = V3Desk if cfg.engine == "v3" else Desk
    return cls(geo, cfg, level, now, roster)
