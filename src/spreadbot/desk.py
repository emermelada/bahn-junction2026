"""The desk: folds events into state, quotes requests and dispatches won cars.

One object, fed by events, emits actions into `outbox`. The same code runs in practice (advance)
and in the final (stream). Every decision appends one line to `log` with a reason code.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import Config
from .geo import DAY, HOUR, Geo, open_intervals
from .notes_safe import LegNote, read_note_safe
from .policy import Governor, Market, OnTime

OPTION_ORDER = ("same_day", "next_day", "within_3_days")


# (drive minutes under, fee over typical fee) from 3,983 orders of v1aa (lab/frank/pnl.py by drive time).
DRIVE_COST = ((30, 1.65), (45, 1.38), (60, 1.34), (90, 1.26), (120, 1.16), (180, 1.14), (240, 1.10), (360, 1.14), (10**6, 1.28))


EXPENSIVE_COEF = {"log_drive": 1.5401, "log_ref": -2.0677, "log_sup_p30": -0.0331, "log_sup_p80": -0.036, "log_sup_d30": -0.0347,
                  "slack12": -0.1486, "overnight": 0.5602, "same_day": 0.0908, "hour": 0.0092, "late_hour": -0.1168, "friday": 0.023,
                  "premium": 0.663, "private": 0.7154, "note": -0.0284, "load": 13.862, "tradein": -0.5628, "intercept": 10.0344}


def lane_of(r: dict) -> str:
    return r["legs"][0]["pickup"]["placeId"] + ">" + r["legs"][-1]["delivery"]["placeId"]


def business_hours(a: int, b: int) -> float:
    """Request hours (Mon-Fri 08:00-18:00) between world minutes a and b."""
    total = 0
    for d in range(max(0, a // DAY), min(5, b // DAY + 1)):
        lo, hi = max(a, d * DAY + 8 * HOUR), min(b, d * DAY + 18 * HOUR)
        total += max(0, hi - lo)
    return total / 60


def h01(*parts: Any) -> float:
    """Deterministic uniform [0,1) from a key: no global RNG, so a replay decides the same."""
    d = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(d, "big") / 2**64


@dataclass
class GigRec:
    id: str
    stops: list[dict]
    audience: dict
    schedule: list[dict]
    posted_at: int
    status: str = "open"  # open | booked | working | done | withdrawn
    driver: Optional[str] = None
    fee: int = 0
    escalated: bool = False

    @property
    def legs(self) -> list[tuple[str, int]]:
        return [(s["orderId"], s["leg"]) for s in self.stops if s["kind"] == "pickup"]


@dataclass
class OrderBook:
    order: dict
    won_at: int
    first_post_at: Optional[int] = None
    urgent: bool = False
    late_counted: bool = False
    retry_from: dict = field(default_factory=dict)  # leg -> earliest pickup after a failed visit
    manual: bool = False
    plates: set = field(default_factory=set)
    p_ok: float = 0.85
    p_exp: float = 0.0


class Desk:
    def __init__(self, geo: Geo, cfg: Config, level: int, now: int, roster: list[dict]):
        self.geo, self.cfg, self.level, self.now = geo, cfg, level, now
        self.outbox: list[dict] = []
        self.log: list[str] = []
        self.requests: dict[str, dict] = {}
        self.notes: dict[str, list[LegNote]] = {}
        self.quoted: dict[str, dict] = {}  # request id -> prices sent
        self.orders: dict[str, OrderBook] = {}
        self.gigs: dict[str, GigRec] = {}
        self.leg_gig: dict[tuple[str, int], str] = {}
        self.pending_posts: list[tuple[dict, str]] = []  # (post action, reason) awaiting a gig id
        self.trust: dict[str, int] = defaultdict(int)
        self.outcomes: list[tuple[int, str, str, float, bool]] = []  # (at, dealer, option, ratio, won)
        self.revenue_seen: dict[str, int] = {}
        self.refund_seen: set[str] = set()
        self.ledger_total = 0
        self.offers_today: dict[tuple[str, int], int] = defaultdict(int)
        self.open_offers: dict[str, int] = defaultdict(int)  # gig -> open offers
        self.offered: set[tuple[str, str]] = set()  # (gig, driver)
        self.gig_viewers: dict[str, list[str]] = {}  # gig -> drivers who viewed it, in order
        self.bundle_last: dict[str, int] = {}  # order -> last minute to start its bundle
        self.held: dict[str, int] = {}  # order -> minute to stop holding it for a chain partner and post it alone
        self.morning_drops: dict[int, int] = defaultdict(int)
        self.due_count: dict[int, int] = defaultdict(int)
        self.batch_won: dict[str, int] = defaultdict(int)
        self.need_resync = False
        self.cost_pred_sum = 0.0  # this week's bookings: the table's ratio, summed
        self.cost_paid_sum = 0.0  # and the ratio they paid
        self._nearby: dict[str, list[tuple[str, float]]] = {}
        self.fast_book: list[tuple[int, bool]] = []  # (posted at, booked within an hour at the opening fee) per first post
        self.first_posts: dict[str, int] = {}  # gig -> posted at, for first posts still being judged
        self.crunch_day = -1
        self.offer_log: list[tuple[str, str, float, int]] = []  # (gig, driver, fee over base, minute)
        self.positions: dict[str, tuple[str, int]] = {}  # driver -> (place, minute), from our gigs
        self.viewers: dict[str, int] = {}  # driver -> last minute seen in the app
        self.roster = {d["id"]: d for d in roster}
        self.home_count: dict[str, int] = defaultdict(int)
        for d in roster:
            self.home_count[d["homePlaceId"]] += 1
        self.won_count = 0
        self.late_orders: set[str] = set()
        self.ontime_orders: set[str] = set()
        self.dealer_requests: dict[str, int] = defaultdict(int)
        self.n_quoted_outcomes = 0
        self.n_won_quoted = 0
        self.sum_won_price = 0
        self.quote_meta: dict[str, dict] = {}  # request id -> option -> on-time chance at quote time
        self.market = Market(self)
        self.ontime = OnTime(self)
        self.gov = Governor(self)
        self.book_ratios: list[float] = []

    # ------------------------------------------------------------------ helpers
    def say(self, code: str, detail: str = "") -> None:
        self.log.append(f"{self.now}\t{code}\t{detail}")

    def supply_near(self, place: str, radius: float = 30.0) -> int:
        return sum(c for p, c in self.home_count.items() if self.geo.air(p, place) <= radius)

    def note(self, oid: str) -> list[LegNote]:
        if oid not in self.notes:
            req = self.requests.get(oid)
            self.notes[oid] = read_note_safe(req) if req else []
        return self.notes[oid]

    def leg_note(self, oid: str, leg: int) -> LegNote:
        ns = self.note(oid)
        return ns[leg] if leg < len(ns) else LegNote()

    # ------------------------------------------------------------------ events
    def handle(self, e: dict) -> None:
        k = e["kind"]
        try:
            fn = getattr(self, "on_" + k, None)
            if fn:
                fn(e)
        except Exception as exc:  # one bad event must never stop the loop
            self.say("ERR", f"{k} {type(exc).__name__}: {exc}")
            if k == "price_request":
                r = e["request"]
                self.outbox.append({"type": "quote", "requestId": r["id"], "prices": decline_prices(r)})

    def on_price_request(self, e: dict) -> None:
        r = e["request"]
        if r["id"] not in self.requests:
            self.dealer_requests[r["dealerId"]] += 1
        self.requests[r["id"]] = r
        prices, why = self.price(r)
        self.quoted[r["id"]] = prices
        self.outbox.append({"type": "quote", "requestId": r["id"], "prices": prices})
        self.say("QUOTE", f"{r['id']} {why} {prices}")

    def on_order_won(self, e: dict) -> None:
        o = e["order"]
        if o["id"] in self.orders:
            return
        ob = OrderBook(o, e["at"])
        if self.requests.get(o["id"], {}).get("batchId"):
            self.batch_won[self.requests[o["id"]]["batchId"]] += 1
        if self.cfg.hot_open and o["id"] in self.requests:
            ob.p_exp = self.p_expensive(self.requests[o["id"]], o)
        self.due_count[min(self.deadline(o, l) for l in range(len(o["legs"]))) // DAY] += 1 if o["id"] in self.requests else 0
        ob.p_ok = self.quote_meta.get(o["id"], {}).get(o["option"], 0.85)
        self.orders[o["id"]] = ob
        self.won_count += 1
        self.observe_outcome(o["id"], e["at"], True)
        self.dispatch_order(o["id"], "won")

    def on_order_lost(self, e: dict) -> None:
        self.observe_outcome(e["requestId"], e["at"], False)

    def observe_outcome(self, rid: str, at: int, won: bool) -> None:
        """One observation per request: our best offer over list, trust removed, against win or loss."""
        r = self.requests.get(rid)
        q = self.quoted.get(rid, {})
        if not r or not q or self.cfg.experiment_quote:
            return
        ratios = [q[o["kind"]] / o["listPriceCents"] for o in r["options"] if o["kind"] in q and q[o["kind"]] < 3 * o["listPriceCents"]]
        if ratios:
            self.market.observe(at, r["dealerId"], min(ratios) / self.trust_factor(r["dealerId"]), won, r["legs"][0]["pickup"]["placeId"], lane_of(r))
            self.n_quoted_outcomes += 1
            if won:
                self.n_won_quoted += 1
                o = self.orders.get(rid)
                self.sum_won_price += o.order["priceCents"] if o else 0

    def on_order_changed(self, e: dict) -> None:
        o = e["order"]
        ob = self.orders.get(o["id"])
        if not ob:
            return
        ob.order = o
        self.say("CHANGED", f"{o['id']} {e.get('message', {}).get('text', '')[:60]}")
        # Repost open (unbooked) gigs so their windows follow the new plan.
        for leg in self.undelivered(o["id"]):
            gid = self.leg_gig.get((o["id"], leg))
            if gid and self.gigs[gid].status == "open":
                self.withdraw(gid)
        self.dispatch_order(o["id"], "changed")

    def on_order_cancelled(self, e: dict) -> None:
        oid = e["orderId"]
        for g in e.get("gigs", []):
            rec = self.gigs.get(g["gigId"])
            if rec and g["outcome"] in ("withdrawn", "released"):
                rec.status = "withdrawn"
        for key in [k for k in self.leg_gig if k[0] == oid]:
            del self.leg_gig[key]
        self.orders.pop(oid, None)
        self.say("CANCELLED", oid)
        # Other orders' cars of a withdrawn shared gig: post again.
        for g in e.get("gigs", []):
            rec = self.gigs.get(g["gigId"])
            if rec and g["outcome"] == "withdrawn":
                for (o2, leg) in rec.legs:
                    if o2 != oid and o2 in self.orders:
                        self.leg_gig.pop((o2, leg), None)
                        self.dispatch_order(o2, "cancel-sibling")

    def on_gig_booked(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if rec:
            rec.status, rec.driver, rec.fee = "booked", e["driverId"], e["feeCents"]
            t0 = self.first_posts.pop(rec.id, None)
            if t0 is not None:
                self.fast_book.append((t0, e["at"] - t0 <= 60 and e["feeCents"] <= rec.schedule[0]["feeCents"]))
            ob = self.orders.get(rec.legs[0][0])
            if ob:
                self.book_ratios.append(e["feeCents"] / max(1.0, self.gig_base(rec)))
                if len({o for o, _ in rec.legs}) == 1:
                    o = ob.order
                    drive = sum(self.geo.drive(o["legs"][l]["pickup"]["placeId"], o["legs"][l]["delivery"]["placeId"]) for _, l in rec.legs)
                    for limit, mult in DRIVE_COST:
                        if drive < limit:
                            break
                    self.cost_pred_sum += mult
                    self.cost_paid_sum += e["feeCents"] / max(1.0, self.gig_base(rec))
            self.say("BOOKED", f"{rec.id} {e['driverId']} {e['feeCents']}")

    def on_offer_answered(self, e: dict) -> None:
        self.open_offers[e["gigId"]] = max(0, self.open_offers[e["gigId"]] - 1)
        self.say("OFFER_ANS", f"{e['gigId']} {e['driverId']} {e['answer']}")

    def on_gig_dropped(self, e: dict) -> None:
        self._reopen(e["gigId"], "dropped")
        day, h = e["at"] // DAY, (e["at"] % DAY) // 60
        if 5 <= h < 13:
            self.morning_drops[day] += 1
            if self.cfg.crunch_drops and self.morning_drops[day] == self.cfg.crunch_drops:
                self.crunch_day = day
                self.say("CRUNCH", f"day {day}: {self.morning_drops[day]} drops this morning")
                for rec in list(self.gigs.values()):
                    ob = self.orders.get(rec.legs[0][0])
                    if rec.status == "open" and ob and self.last_pickup(ob, [l for _, l in rec.legs]) < (day + 1) * DAY:
                        ob.urgent = True
                        self.escalate_gig(rec, "crunch")

    def on_no_show(self, e: dict) -> None:
        self._reopen(e["gigId"], "no_show")

    def _reopen(self, gid: str, why: str) -> None:
        rec = self.gigs.get(gid)
        if not rec:
            return
        rec.status, rec.driver = "open", None
        self.say("REOPEN", f"{gid} {why}")
        # The gig is in the app again with its old schedule: make sure it can still find a driver.
        self.escalate_gig(rec, why)

    def on_gig_started(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if rec:
            rec.status = "working"

    def on_driver_late(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if not rec:
            return
        self.say("DRIVER_LATE", f"{rec.id} pickupAt={e['pickupAt']}")

    def on_gig_expired(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if not rec:
            return
        rec.status = "withdrawn"
        for key in rec.legs:
            if self.leg_gig.get(key) == rec.id:
                del self.leg_gig[key]
        for oid in {o for o, _ in rec.legs}:
            if oid in self.orders:
                self.orders[oid].urgent = True
                self.dispatch_order(oid, "expired")

    def on_visit_failed(self, e: dict) -> None:
        oid, leg, reason = e["orderId"], e["leg"], e["reason"]
        ob = self.orders.get(oid)
        if self.leg_gig.get((oid, leg)) == e["gigId"]:
            del self.leg_gig[(oid, leg)]
        if not ob:
            return
        if reason in ("not_ready", "closed"):
            ob.retry_from[leg] = self.now + (2 * HOUR if reason == "not_ready" else 30)
        elif reason == "licence":
            ob.manual = True
        elif reason == "no_plates":
            ob.plates.add(leg)
        self.say("FAILED", f"{oid}/{leg} {reason}")
        self.dispatch_order(oid, "failed-" + reason)

    def on_picked_up(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if rec and rec.driver:
            self.positions[rec.driver] = (e["placeId"], e["at"])

    def on_delivered(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if rec and rec.driver:
            self.positions[rec.driver] = (e["placeId"], e["at"])
        ob = self.orders.get(e["orderId"])
        if ob:
            ob.order["deliveredAt"][e["leg"]] = e["at"]
        if self.leg_gig.get((e["orderId"], e["leg"])) == e["gigId"]:
            del self.leg_gig[(e["orderId"], e["leg"])]
        if rec and all(self.orders.get(o) is None or self.orders[o].order["deliveredAt"][l] is not None for o, l in rec.legs):
            rec.status = "done"

    def on_gig_viewed(self, e: dict) -> None:
        self.viewers[e["driverId"]] = e["at"]
        v = self.gig_viewers.setdefault(e["gigId"], [])
        if e["driverId"] not in v:
            v.append(e["driverId"])

    def on_deadline_close(self, e: dict) -> None:
        ob = self.orders.get(e["orderId"])
        if not ob:
            return
        ob.urgent = True
        ob.order["lastPickupAt"] = e["lastPickupAt"]
        self.say("DEADLINE_CLOSE", f"{e['orderId']} lastPickupAt={e['lastPickupAt']}")
        self.dispatch_order(e["orderId"], "deadline_close")
        for leg in self.undelivered(e["orderId"]):
            gid = self.leg_gig.get((e["orderId"], leg))
            if gid and self.gigs[gid].status == "open":
                self.escalate_gig(self.gigs[gid], "deadline_close")

    def on_ledger(self, e: dict) -> None:
        line = e["line"]
        self.ledger_total += line["cents"]
        oid = line.get("orderId")
        if not oid:
            return
        if line["kind"] == "revenue":
            self.revenue_seen[oid] = e["at"]
            ob = self.orders.get(oid)
            dealer = ob.order["dealerId"] if ob else (self.requests.get(oid) or {}).get("dealerId")
            if dealer and oid not in self.refund_seen:
                self.trust[dealer] = min(25, self.trust[dealer] + 1)
                self.ontime_orders.add(oid)
        elif line["kind"] in ("late_refund", "undelivered_penalty"):
            first = oid not in self.refund_seen
            self.refund_seen.add(oid)
            ob = self.orders.get(oid)
            dealer = ob.order["dealerId"] if ob else (self.requests.get(oid) or {}).get("dealerId")
            if dealer and first:
                if oid in self.ontime_orders:  # revenue came first in the same minute: undo the +1
                    self.ontime_orders.discard(oid)
                    self.trust[dealer] = max(0, self.trust[dealer] - 1)
                self.trust[dealer] //= 2
                self.late_orders.add(oid)

    def on_forecast(self, e: dict) -> None:
        self.say("FORECAST", f"{e['from']}-{e['to']} {e['placeIds']}")

    # ------------------------------------------------------------------ pricing
    def trust_factor(self, dealer: str) -> float:
        return 1.0 + (self.trust[dealer] / 100.0 if self.level >= 8 else 0.0)

    def price(self, r: dict) -> tuple[dict, str]:
        cfg = self.cfg
        if self.level <= 3:
            first = r["options"][0]
            return {first["kind"]: first["listPriceCents"]}, "L3-list"
        if cfg.experiment_quote:
            first = r["options"][0]
            ratio = cfg.exp_quote_lo + (cfg.exp_quote_hi - cfg.exp_quote_lo) * h01("q", r["id"])
            return {first["kind"]: int(round(first["listPriceCents"] * ratio))}, f"EXP ratio={ratio:.3f}"
        dealer = r["dealerId"]
        tf = self.trust_factor(dealer)
        day = r["respondBy"] // DAY
        bar = self.gov.bar()
        if cfg.max_per_batch and r.get("batchId") and self.batch_won[r["batchId"]] >= cfg.max_per_batch:
            return decline_prices(r), f"DECLINE batch {r['batchId']} full"
        if self.crunch_day == self.now // DAY:
            bar = max(bar, cfg.theta_tight)
        gate = 0.0
        if cfg.gate_bonus_cents and self.won_count >= 30:
            gate = cfg.gate_bonus_cents * min(1.0, max(0.0, (cfg.gate_target - self.gov.projection()) / cfg.gate_span))
        cal = self.gov.calibration() if cfg.calibrate else 1.0
        drive = sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        cost = r["referenceFeeCents"] * (self.drive_cost_mult(drive) if cfg.drive_cost else self.cost_mult())
        if cfg.bundle_price and self.chainable(r):
            cost *= cfg.bundle_mult  # one of our open gigs ends where this car starts (or the reverse): a driver can take both
        backlog = self.backlog(r["legs"][0]["pickup"]["placeId"])
        t_gain, t_loss = self.trust_value(dealer)
        congestion = cfg.cong_frac * r["referenceFeeCents"] * max(0, backlog - cfg.cong_free)
        prices: dict = {}
        meta: dict = {}
        info = []
        for opt in r["options"]:
            kind = opt["kind"]
            if kind not in cfg.quote_options:
                continue
            if cfg.only_next_if_no_same and kind == "next_day" and "same_day" in prices:
                info.append("next_day:skip(same_day quoted)")
                continue
            p_ok, slack = self.ontime.p_ok(r, opt["deadline"], kind)
            p_ok = min(0.99, p_ok * cal)
            if p_ok < bar or slack < cfg.min_slack_h:
                info.append(f"{kind}:skip(p={p_ok:.2f},s={slack:.1f})")
                continue
            # Load: our cars already due that day against the world's drivers. Lateness grows with it
            # (lab: 2.7% late under 6% of drivers, 8.7% at 9-12%, 12% above 15%), so a busy day's next car costs more.
            load = self.due_load(self.deadline_day(r, opt))
            per_car = cfg.load_flat_cents if cfg.load_flat_cents else r["referenceFeeCents"]
            load_cost = cfg.load_slope * per_car * max(0.0, load - cfg.load_free * self.capacity_factor()) / 0.05
            risk_frac = (1 - p_ok) * cfg.late_cost_frac
            # Dealer trust (level 8): an on-time car raises this dealer's future prices by 1%, a late one halves the count.
            trust_adj = cfg.trust_bonus * ((1 - p_ok) * t_loss - p_ok * t_gain) + cfg.trust_loss_w * (1 - p_ok) * t_loss
            # Under the on-time target, a safe car is worth more than its margin: it dilutes the late ones.
            if gate and p_ok >= cfg.gate_safe_p:
                trust_adj -= gate
            ratio, ev = self.market.best_ratio(dealer, day, opt["listPriceCents"], tf, cost, risk_frac, cfg.shadow_cents + congestion + trust_adj + load_cost, r["legs"][0]["pickup"]["placeId"], lane_of(r))
            if ratio <= 0 or ev < cfg.min_ev_cents:
                info.append(f"{kind}:noev")
                continue
            if cfg.trust_invest and self.investing(dealer, p_ok):
                # Build a big dealer's trust fast: win its safe cars with high probability while each still
                # makes money; once the count is at 25, normal pricing (times 1.25) takes over by itself.
                place = r["legs"][0]["pickup"]["placeId"]
                r_inv = self.market.mu_for(dealer, day, place) - math.log(cfg.invest_pwin / (1 - cfg.invest_pwin)) / cfg.win_slope
                margin_inv = opt["listPriceCents"] * r_inv * tf * (1 - risk_frac) - cost - (cfg.shadow_cents + congestion + load_cost)
                if cfg.min_ratio <= r_inv < ratio and margin_inv > cfg.invest_min_margin_cents:
                    ratio = r_inv
                    info.append("invest")
            prices[kind] = int(round(opt["listPriceCents"] * ratio * tf))
            meta[kind] = p_ok
            info.append(f"{kind}:r={ratio:.2f},p={p_ok:.2f},ev={ev/100:.0f},L={load:.3f}")
        self.quote_meta[r["id"]] = meta
        head = f"bar={bar:.2f} bl={backlog} tg={t_gain/100:.0f} tf={tf:.2f} mu={self.market.mu_for(dealer, day, r["legs"][0]["pickup"]["placeId"]):.3f} cost={cost/100:.0f}"
        if not prices:
            return decline_prices(r), f"DECLINE {head} {' '.join(info)}"
        return prices, f"{head} {' '.join(info)}"

    def deadline_day(self, r: dict, opt: dict) -> int:
        d = opt["deadline"]
        ns = self.note(r["id"])
        if ns and ns[0].deadline:
            d = min(d, ns[0].deadline)
        return d // DAY

    def nearby(self, place: str) -> list[tuple[str, float]]:
        """Places within 80 km (the outage radius in RULES.md), weighted 1 at the place down to 0.3 at 80 km."""
        if place not in self._nearby:
            self._nearby[place] = [(p, 1.0 - 0.7 * self.geo.air(place, p) / 80.0) for p in self.geo.ids if self.geo.air(place, p) <= 80.0]
        return self._nearby[place]

    def capacity_factor(self) -> float:
        """How easily our gigs find drivers this week: the share of first posts booked within an hour at the
        opening fee, over the share we usually see (0.7). More easy bookings, more room per day."""
        if not self.cfg.adaptive_load:
            return 1.0
        done = [ok for (at, ok) in self.fast_book[-60:]]
        if len(done) < 15:
            return 1.0
        rate = (sum(done) + 0.7 * 10) / (len(done) + 10)
        return min(self.cfg.cap_max, max(self.cfg.cap_min, rate / 0.7))

    def due_load(self, day: int) -> float:
        """Our orders due on this day (won, not cancelled), over the number of drivers in the world."""
        n = self.due_count.get(day, 0)
        return n / max(1, len(self.roster))

    def p_expensive(self, r: dict, o: dict) -> float:
        """Chance that a won car ends late or above 1.3x the typical fee (lab/frank/expensive.py: 14,181 orders,
        held-out-seed AUC 0.67). Features as at the win; load counts our cars already due that day."""
        opt = next(x for x in r["options"] if x["kind"] == o["option"])
        f = self.ontime.features(r, opt["deadline"], o["option"])
        L0 = r["legs"][0]
        drive = sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        hour = (r["respondBy"] % DAY) / 60
        x = {"log_drive": math.log(drive + 10), "log_ref": math.log(max(1, r["referenceFeeCents"])),
             "log_sup_p30": math.log1p(self.supply_near(L0["pickup"]["placeId"], 30)), "log_sup_p80": f["log_sup_p80"],
             "log_sup_d30": f["log_sup_d30"], "slack12": f["slack12"], "overnight": f["overnight"], "same_day": f["same_day"],
             "hour": hour, "late_hour": float(hour >= 15), "friday": f["friday"], "premium": f["premium"], "private": f["private"],
             "note": f["note"], "load": self.due_load(o["deadline"] // DAY), "tradein": float(len(r["legs"]) == 2)}
        z = EXPENSIVE_COEF["intercept"] + sum(c * x[k] for k, c in EXPENSIVE_COEF.items() if k != "intercept")
        return 1 / (1 + math.exp(-max(-40.0, min(40.0, z))))

    def investing(self, dealer: str, p_ok: float) -> bool:
        """A dealer worth building trust with: a big share of the requests, count under 25, a safe car."""
        total = sum(self.dealer_requests.values())
        return (self.level >= 8 and total >= 30 and self.trust[dealer] < 25 and p_ok >= self.cfg.invest_p_ok
                and self.dealer_requests[dealer] / total >= self.cfg.invest_share and self.now < 3 * DAY)

    def trust_value(self, dealer: str) -> tuple[float, float]:
        """(gain, loss) in cents: 1% of this dealer's expected revenue for the rest of the week, for one more
        on-time order (while the count is under 25), and the count halved for a late one."""
        if self.level < 8:
            return 0.0, 0.0
        elapsed, remaining = business_hours(0, self.now), business_hours(self.now, 4 * DAY + 18 * HOUR)
        rate = self.dealer_requests[dealer] / max(elapsed, 3.0)
        q = self.n_quoted_outcomes
        win_share = (self.n_won_quoted + 0.4 * 20) / (q + 20)
        avg_price = (self.sum_won_price + 8500 * 10) / (self.n_won_quoted + 10)
        future = rate * remaining * win_share * avg_price
        t = self.trust[dealer]
        lost = t - t // 2
        # Each later on-time order wins one point back, so the loss fades: about sum(1..lost)% of one price,
        # unless the dealer sends too few orders to rebuild it this week.
        loss = min(0.01 * lost * future, 0.01 * lost * (lost + 1) / 2 * avg_price)
        return (0.01 * future if t < 25 else 0.0), loss

    def backlog(self, place: str) -> int:
        """Our gigs near this pickup that no driver holds yet: the live sign that local drivers are used up."""
        n = 0
        for rec in self.gigs.values():
            if rec.status != "open":
                continue
            o = self.orders.get(rec.legs[0][0])
            if not o:
                continue
            p = o.order["legs"][rec.legs[0][1]]["pickup"]["placeId"]
            if self.geo.air(p, place) <= self.cfg.cong_radius and o.order["lastPickupAt"] - self.now < self.cfg.cong_horizon:
                n += 1
        return n

    def drive_cost_mult(self, drive: int) -> float:
        """Expected fee over typical fee by drive time (lab/frank: 3,983 orders of v1aa), scaled by how this
        week's bookings compare with the table. Short hops cost most per typical fee: the trips dominate."""
        base = DRIVE_COST[-1][1]
        for limit, mult in DRIVE_COST:
            if drive < limit:
                base = mult
                break
        pred, paid = self.cost_pred_sum, self.cost_paid_sum
        k = self.cfg.cost_prior_n
        return base * (paid + k) / (pred + k)

    def cost_mult(self) -> float:
        """Expected fee over typical fee: the prior, moved by what our own bookings paid this week."""
        prior, n = self.cfg.cost_prior, self.cfg.cost_prior_n
        xs = self.book_ratios[-150:]
        return (prior * n + sum(xs)) / (n + len(xs))

    # ------------------------------------------------------------------ dispatch
    def undelivered(self, oid: str) -> list[int]:
        ob = self.orders.get(oid)
        if not ob:
            return []
        return [i for i, t in enumerate(ob.order["deliveredAt"]) if t is None]

    def dispatch_order(self, oid: str, why: str) -> None:
        """Posts gigs for the order's undelivered legs that have no live gig."""
        ob = self.orders.get(oid)
        if not ob:
            return
        legs = [l for l in self.undelivered(oid) if (oid, l) not in self.leg_gig and not self._pending(oid, l)]
        if not legs:
            return
        if self.cfg.bundle and self.cfg.hold_minutes and (why == "won" or oid in self.held) and legs == [0] and len(ob.order["legs"]) == 1 and self.simple(ob):
            # Hold the car a while: most cars are won hours before they are ready, and a partner whose
            # pickup is near this car's delivery lets one driver take both for less than two gigs.
            until = self.held.setdefault(oid, self.hold_until(ob))
            if self.try_bundle(ob):
                return
            if self.now < until:
                return
            self.held.pop(oid, None)
        elif self.cfg.bundle and why == "won" and len(ob.order["legs"]) == 1 and self.try_bundle(ob):
            return
        groups = [legs]
        if len(legs) == 2 and self.trade_minutes(ob.order) > 12 * HOUR - 10:
            groups = [[l] for l in legs]
        for g in groups:
            self.post(ob, g, why)

    # ------------------------------------------------------------------ bundles
    def chainable(self, r: dict) -> bool:
        """A request that could join one of our open single-car gigs as a chain (rough check at quote time)."""
        if len(r["legs"]) != 1:
            return False
        L = r["legs"][0]
        if L["pickup"]["privateAddress"] or L["delivery"]["privateAddress"]:
            return False
        p, d = L["pickup"]["placeId"], L["delivery"]["placeId"]
        km = self.cfg.bundle_km
        for oid2 in self.held:
            ob = self.orders.get(oid2)
            if not ob or not self.simple(ob):
                continue
            O = ob.order["legs"][0]
            if ob.order["deadline"] // DAY != r["options"][0]["deadline"] // DAY:
                continue
            if self.geo.air(O["delivery"]["placeId"], p) <= km or self.geo.air(d, O["pickup"]["placeId"]) <= km:
                return True
        for rec in self.gigs.values():
            if rec.status != "open" or rec.escalated or len(rec.legs) != 1 or self.now - rec.posted_at > self.cfg.bundle_window:
                continue
            ob = self.orders.get(rec.legs[0][0])
            if not ob or not self.simple(ob):
                continue
            O = ob.order["legs"][0]
            if ob.order["deadline"] // DAY != r["options"][0]["deadline"] // DAY:
                continue
            if self.geo.air(O["delivery"]["placeId"], p) <= km or self.geo.air(d, O["pickup"]["placeId"]) <= km:
                return True
        return False

    def simple(self, ob: OrderBook) -> bool:
        """One car, dealer sites at both ends, a note that changes nothing: safe to chain."""
        o = ob.order
        if len(o["legs"]) != 1 or ob.urgent or ob.retry_from or ob.manual or ob.plates:
            return False
        L = o["legs"][0]
        if L["pickup"]["privateAddress"] or L["delivery"]["privateAddress"]:
            return False
        n = self.leg_note(o["id"], 0)
        return not (n.ready_at or n.after_payment or n.pickup_hours or n.delivery_hours or n.deadline
                    or n.manual or n.plates or n.summer_tyres or n.uncertain)

    def chain(self, A: OrderBook, B: OrderBook) -> Optional[int]:
        """If one driver can take A's car and then B's car, both on time with room to spare: the last
        minute to start the chain. None if not."""
        cfg, geo = self.cfg, self.geo
        LA, LB = A.order["legs"][0], B.order["legs"][0]
        if geo.air(LA["delivery"]["placeId"], LB["pickup"]["placeId"]) > cfg.bundle_km:
            return None
        dA = geo.drive(LA["pickup"]["placeId"], LA["delivery"]["placeId"])
        tr = geo.drive(LA["delivery"]["placeId"], LB["pickup"]["placeId"])
        dB = geo.drive(LB["pickup"]["placeId"], LB["delivery"]["placeId"])
        if dA + tr + dB > min(12 * HOUR - 30, cfg.bundle_max_drive):
            return None
        start = max(self.now + cfg.bundle_lead, LA["pickup"]["window"]["from"])
        if start - self.now < cfg.bundle_min_lead:
            return None
        a_del = start + dA
        if a_del > self.deadline(A.order, 0) - cfg.bundle_margin:
            return None
        b_pick = max(a_del + tr, LB["pickup"]["window"]["from"])
        if b_pick > LB["pickup"]["window"]["to"] or b_pick + dB > self.deadline(B.order, 0) - cfg.bundle_margin:
            return None
        last = min(self.last_pickup(A, [0]), self.last_pickup(B, [0]) - dA - tr)
        if last - self.now < cfg.bundle_min_slack:
            return None
        return last

    def hold_until(self, ob: OrderBook) -> int:
        cfg = self.cfg
        L = ob.order["legs"][0]
        return min(self.now + cfg.hold_minutes, L["pickup"]["window"]["from"] - cfg.hold_lead, self.last_pickup(ob, [0]) - cfg.hold_slack)

    def try_bundle(self, ob: OrderBook) -> bool:
        if not self.simple(ob):
            return False
        best = None
        for oid2 in list(self.held):
            other = self.orders.get(oid2)
            if not other or other is ob or other.order["status"] == "cancelled" or not self.simple(other):
                continue
            if self.undelivered(oid2) != [0] or (oid2, 0) in self.leg_gig or self._pending(oid2, 0):
                continue
            for first, second in ((ob, other), (other, ob)):
                last = self.chain(first, second)
                if last is not None and (best is None or last > best[0]):
                    best = (last, first, second, None)
        for rec in self.gigs.values():
            if rec.status != "open" or rec.escalated or len(rec.legs) != 1 or self.now - rec.posted_at > self.cfg.bundle_window:
                continue
            other = self.orders.get(rec.legs[0][0])
            if not other or other is ob or not self.simple(other):
                continue
            for first, second in ((ob, other), (other, ob)):
                last = self.chain(first, second)
                if last is not None and (best is None or last > best[0]):
                    best = (last, first, second, rec)
        if not best:
            return False
        last, first, second, rec = best
        if rec is not None:
            self.withdraw(rec.id)
        self.held.pop(first.order["id"], None)
        self.held.pop(second.order["id"], None)
        stops = self.stops_for(first, 0) + self.stops_for(second, 0)
        audience = {"experienced": any(x.order["legs"][0]["car"]["premium"] for x in (first, second)), "manualLicence": False}
        base = (self.base_fee(first, [0]) + self.base_fee(second, [0])) * self.cfg.bundle_mult
        out = [{"at": self.now, "feeCents": int(round(base * self.cfg.fee_open))}]
        prev = out[0]["feeCents"]
        # Unbooked bundles used to sit at the opening fee until they were split, and split cars run late and dear:
        # a bundle raises toward the price of two gigs before it gives up.
        steps = [(h, m * self.cfg.bundle_mult) for h, m in self.cfg.fee_rel] if not self.cfg.bundle_rel else             [(h, m) for h, m in self.cfg.bundle_rel]
        for hours_before, mult in steps:
            fee = max(prev, int(round(base / self.cfg.bundle_mult * mult)))
            out.append({"at": max(self.now + self.cfg.fee_hold, last - int(hours_before * HOUR)), "feeCents": fee})
            prev = fee
        sched = dedupe(sorted(out, key=lambda x: (x["at"], x["feeCents"])))
        action = {"type": "post", "stops": stops, "audience": audience, "schedule": sched}
        self.outbox.append(action)
        self.pending_posts.append((action, "bundle"))
        self.bundle_last[first.order["id"]] = last
        self.bundle_last[second.order["id"]] = last
        self.say("BUNDLE", first.order["id"] + "+" + second.order["id"] + f" last={last} fee0={sched[0]['feeCents']}")
        return True

    def unbundle(self, rec: GigRec, why: str) -> None:
        self.say("UNBUNDLE", f"{rec.id} {why}")
        oids = sorted({o for o, _ in rec.legs})
        self.withdraw(rec.id)
        for oid in oids:
            if oid in self.orders:
                self.dispatch_order(oid, "unbundle-" + why)

    def _pending(self, oid: str, leg: int) -> bool:
        return any(s["orderId"] == oid and s["leg"] == leg for a, _ in self.pending_posts for s in a["stops"])

    def trade_minutes(self, o: dict) -> int:
        a, b = o["legs"][0], o["legs"][1]
        return (self.geo.drive(a["pickup"]["placeId"], a["delivery"]["placeId"]) + self.geo.drive(a["delivery"]["placeId"], b["pickup"]["placeId"])
                + self.geo.drive(b["pickup"]["placeId"], b["delivery"]["placeId"]))

    def post(self, ob: OrderBook, legs: list[int], why: str) -> None:
        o = ob.order
        stops = []
        for leg in legs:
            stops += self.stops_for(ob, leg)
        manual = ob.manual or any(self.leg_note(o["id"], l).manual for l in legs)
        audience = {"experienced": any(o["legs"][l]["car"]["premium"] for l in legs), "manualLicence": manual}
        schedule = self.schedule(ob, legs)
        action = {"type": "post", "stops": stops, "audience": audience, "schedule": schedule}
        if ob.first_post_at is None:
            ob.first_post_at = self.now
        self.outbox.append(action)
        self.pending_posts.append((action, why))
        self.say("POST", f"{o['id']} legs={legs} {why} fee0={schedule[0]['feeCents']} feeN={schedule[-1]['feeCents']} n={len(schedule)}")

    def stops_for(self, ob: OrderBook, leg: int) -> list[dict]:
        o = ob.order
        L = o["legs"][leg]
        n = self.leg_note(o["id"], leg)
        pw = L["pickup"]["window"]
        frm = max(pw["from"], n.ready_at or 0, ob.retry_from.get(leg, 0))
        to = pw["to"]
        if n.pickup_hours and not L["pickup"]["privateAddress"]:
            real = dict(L["pickup"]["hours"] or {"weekdays": [0, 1, 2, 3, 4], "saturday": None})
            real["opens"], real["closes"] = n.pickup_hours
            iv = open_intervals(real, frm, to)
            if iv:
                frm, to = iv[0][0], iv[0][1]
        pick: dict = {"orderId": o["id"], "leg": leg, "kind": "pickup"}
        if leg in ob.plates or n.plates:
            pick["withPlates"] = True
        car = L["car"]
        if car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30 and \
                self.geo.km(L["pickup"]["placeId"], L["delivery"]["placeId"]) > self.cfg.charge_km:
            pick["withCharging"] = True
        if (frm > pw["from"] or to < pw["to"]) and frm < to and to > self.now:
            pick["window"] = {"from": frm, "to": to}
        dw = L["delivery"]["window"]
        deadline = self.deadline(o, leg)
        dto = deadline
        if n.delivery_hours and not L["delivery"]["privateAddress"]:
            real = dict(L["delivery"]["hours"] or {"weekdays": [0, 1, 2, 3, 4], "saturday": None})
            real["opens"], real["closes"] = n.delivery_hours
            iv = open_intervals(real, dw["from"], dto)
            if iv:
                dto = iv[-1][1]
        dele: dict = {"orderId": o["id"], "leg": leg, "kind": "delivery"}
        if dto < dw["to"] and dto > max(self.now, dw["from"]):
            dele["window"] = {"from": dw["from"], "to": dto}
        return [pick, dele]

    def deadline(self, o: dict, leg: int) -> int:
        n = self.leg_note(o["id"], leg)
        d = o["deadline"]
        if n.deadline and n.deadline < d:
            d = n.deadline
        return d

    def gig_base(self, rec: GigRec) -> float:
        """The typical fee of every car in a gig, summed (a bundle carries cars of two orders)."""
        total = 0.0
        for oid, leg in rec.legs:
            r = self.requests.get(oid)
            if r:
                total += r["referenceFeeCents"] / len(r["legs"])
        return total or 5000.0

    def base_fee(self, ob: OrderBook, legs: list[int]) -> float:
        r = self.requests.get(ob.order["id"])
        ref = r["referenceFeeCents"] if r else 5000
        return ref * len(legs) / len(ob.order["legs"])

    def schedule(self, ob: OrderBook, legs: list[int]) -> list[dict]:
        base = self.base_fee(ob, legs)
        cfg, now = self.cfg, self.now
        if cfg.experiment_fee and not ob.urgent:
            ratio = cfg.exp_fee_ratios[int(h01("f", ob.order["id"]) * len(cfg.exp_fee_ratios))]
            return [{"at": now, "feeCents": max(1, int(round(base * ratio)))}]
        last = self.last_pickup(ob, legs)
        if cfg.late_plan and self.is_late(ob, legs):
            # Already late: on-time is lost, only the refund tier and delivery matter. No steep fees.
            return dedupe([{"at": now + int(h * HOUR), "feeCents": max(1, int(round(base * m)))} for h, m in cfg.late_plan])
        if ob.urgent or last - now < 2 * HOUR:
            return steep(now, base, cfg, plan=self.steep_plan_now(ob))
        if cfg.fee_mode == "relative":
            # Steps anchored to lastPickupAt: hold the opening fee while there is time, raise as the pickup nears.
            # The opening fee always shows for at least fee_hold minutes: most views come in the first minutes.
            opening = cfg.fee_open_hot if ob.p_exp >= cfg.hot_p else cfg.fee_open
            out, prev = [{"at": now, "feeCents": int(round(base * opening))}], int(round(base * opening))
            for hours_before, mult in cfg.fee_rel:
                at = max(now + cfg.fee_hold, last - int(hours_before * HOUR))
                fee = max(prev, int(round(base * mult)))
                out.append({"at": at, "feeCents": fee})
                prev = fee
            return dedupe(sorted(out, key=lambda s: (s["at"], s["feeCents"])))
        # Open low, then a few raises spread over the slack, all before the deadline warning (3 h before lastPickupAt).
        span = max(30, last - 3 * HOUR - now)
        out, prev = [], 0
        for frac, mult in cfg.fee_plan:
            fee = max(prev, int(round(base * mult)))
            out.append({"at": now + int(span * frac), "feeCents": fee})
            prev = fee
        return dedupe(out)

    def last_pickup(self, ob: OrderBook, legs: list[int]) -> int:
        """The world's lastPickupAt, made earlier by a note's tighter deadline (the world's does not count it)."""
        o = ob.order
        last = o["lastPickupAt"]
        for l in legs:
            n = self.leg_note(o["id"], l)
            if n.deadline and n.deadline < o["deadline"]:
                L = o["legs"][l]
                last = min(last, n.deadline - self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) - 20)
        return last

    def is_late(self, ob: OrderBook, legs: list[int]) -> bool:
        """No pickup from now on can make the deadline of these legs."""
        o = ob.order
        for l in legs:
            L = o["legs"][l]
            if self.now + self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) > self.deadline(o, l):
                return True
        return False

    def steep_plan_now(self, ob: Optional[OrderBook] = None) -> tuple:
        """How much to pay to save a car: little while the on-time budget is comfortable, a lot near the gate,
        and more for a dealer whose trust a late car would halve."""
        cfg = self.cfg
        if not cfg.gov_steep:
            return cfg.steep_plan
        proj = self.gov.projection()
        level = 0 if proj >= cfg.gov_relaxed else 1 if proj >= cfg.gov_tight else 2
        if cfg.protect_trust_cents and ob is not None:
            loss = self.trust_value(ob.order["dealerId"])[1]
            if loss >= 2 * cfg.protect_trust_cents:
                level = 2
            elif loss >= cfg.protect_trust_cents:
                level = max(level, 1)
        return (cfg.steep_relaxed, cfg.steep_plan, cfg.steep_rescue)[level]

    def escalate_gig(self, rec: GigRec, why: str) -> None:
        if rec.status != "open":
            return
        if len({o for o, _ in rec.legs}) > 1:
            self.unbundle(rec, why)
            return
        legs = rec.legs
        oid = legs[0][0]
        ob = self.orders.get(oid)
        if not ob:
            return
        base = self.base_fee(ob, [l for _, l in legs])
        cur = current_fee(rec.schedule, self.now)
        if self.cfg.late_plan and self.is_late(ob, [l for _, l in legs]):
            return
        sched = steep(self.now, base, self.cfg, floor=cur, plan=self.steep_plan_now(ob))
        rec.schedule = sched
        rec.escalated = True
        self.outbox.append({"type": "reprice", "gigId": rec.id, "schedule": sched})
        self.say("ESCALATE", f"{rec.id} {why} {sched[0]['feeCents']}->{sched[-1]['feeCents']}")
        if self.cfg.use_offers:
            self.send_offers(rec, ob, max(cur, sched[0]["feeCents"]))

    def send_offers(self, rec: GigRec, ob: OrderBook, fee: int) -> None:
        """Direct offers to drivers who live or stand near the first pickup."""
        hour = (self.now % DAY) // 60
        if hour >= 23 or hour < 7:
            return
        first = rec.stops[0]
        place = ob.order["legs"][first["leg"]]["pickup"]["placeId"]
        need_manual, need_exp = rec.audience.get("manualLicence"), rec.audience.get("experienced")
        cands = []
        for did, d in self.roster.items():
            if need_manual and d["licence"] != "manual":
                continue
            if need_exp and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            if self.offers_today[(did, self.now // DAY)] >= 3 or (rec.id, did) in self.offered:
                continue
            where, at = self.positions.get(did, (d["homePlaceId"], -1))
            if at < self.now - 6 * HOUR:
                where = d["homePlaceId"]
            dist = self.geo.air(where, place)
            seen = self.viewers.get(did, -10**9)
            score = dist - (30 if self.now - seen < 12 * HOUR else 0)
            cands.append((score, did))
        cands.sort()
        n = 3 - self.open_offers[rec.id]
        for _, did in cands[:max(0, n)]:
            self.outbox.append({"type": "offer", "gigId": rec.id, "driverId": did, "feeCents": int(fee)})
            self.offers_today[(did, self.now // DAY)] += 1
            self.open_offers[rec.id] += 1
            self.offered.add((rec.id, did))
            self.say("OFFER", f"{rec.id} {did} {fee}")

    def withdraw(self, gid: str) -> None:
        rec = self.gigs[gid]
        rec.status = "withdrawn"
        for key in rec.legs:
            if self.leg_gig.get(key) == gid:
                del self.leg_gig[key]
        self.outbox.append({"type": "withdraw", "gigId": gid})

    # ------------------------------------------------------------------ action results
    def read_results(self, actions: list[dict], results: list[dict]) -> None:
        refused_posts = []
        for a, res in zip(actions, results):
            if a["type"] == "post":
                why = next((w for (pa, w) in self.pending_posts if pa is a), "")
                self.pending_posts = [(pa, w) for (pa, w) in self.pending_posts if pa is not a]
                if res.get("ok"):
                    rec = GigRec(res["id"], a["stops"], a["audience"], a["schedule"], self.now)
                    self.gigs[rec.id] = rec
                    for key in rec.legs:
                        self.leg_gig[key] = rec.id
                    self.say("GIG", f"{rec.id} {a['stops'][0]['orderId']} {why} fee0={a['schedule'][0]['feeCents']}")
                    if why == "won":
                        self.first_posts[rec.id] = self.now
                else:
                    refused_posts.append((a, res.get("reason", "")))
            elif not res.get("ok"):
                self.say("REFUSED", f"{a['type']} {a.get('gigId', a.get('requestId', ''))} {res.get('reason', '')[:120]}")
                if a["type"] == "withdraw" and a["gigId"] in self.gigs:
                    # A driver booked it first (or it started): the gig is live, so its cars must not be posted again.
                    rec = self.gigs[a["gigId"]]
                    rec.status = "booked"
                    for key in rec.legs:
                        if key[0] in self.orders and self.orders[key[0]].order["deliveredAt"][key[1]] is None:
                            self.leg_gig[key] = rec.id
                    self.pending_posts = [(pa, w) for (pa, w) in self.pending_posts if not any((st["orderId"], st["leg"]) in rec.legs for st in pa["stops"])]
                    self.outbox[:] = [x for x in self.outbox if not (x["type"] == "post" and any((st["orderId"], st["leg"]) in rec.legs for st in x["stops"]))]
        for a, reason in refused_posts:
            self.say("POST_REFUSED", f"{a['stops'][0]['orderId']} {reason[:160]}")
            self.repair_post(a, reason)

    def resync(self, snapshot: dict) -> None:
        """Takes gig statuses from the world's snapshot: our books can drift when an action loses a race."""
        live = {}
        for g in snapshot["gigs"]:
            rec = self.gigs.get(g["id"])
            if rec is None:
                rec = GigRec(g["id"], g["stops"], g["audience"], g["schedule"], g["postedAt"])
                self.gigs[rec.id] = rec
            rec.status, rec.driver = g["status"], g.get("driverId")
            if g["status"] in ("open", "booked", "working"):
                for key in rec.legs:
                    live[key] = rec.id
        pending = {(st["orderId"], st["leg"]) for pa, _ in self.pending_posts for st in pa["stops"]}
        for key in list(self.leg_gig):
            if key not in live and key not in pending:
                del self.leg_gig[key]
        self.leg_gig.update(live)

    def repair_post(self, a: dict, reason: str) -> None:
        """A refused post: split multi-car gigs, or drop own windows, and try again next step."""
        if "already in a live gig" in reason:
            self.need_resync = True
            return
        legs = sorted({(s["orderId"], s["leg"]) for s in a["stops"]})
        oid = legs[0][0]
        ob = self.orders.get(oid)
        if not ob:
            return
        if len(legs) > 1:
            for _, l in legs:
                self.post(ob, [l], "split")
            return
        stops = [{k: v for k, v in s.items() if k != "window"} for s in a["stops"]]
        if stops != a["stops"]:
            action = {**a, "stops": stops}
            self.outbox.append(action)
            self.pending_posts.append((action, "nowindow"))
            self.say("REPOST_NOWINDOW", oid)

    # ------------------------------------------------------------------ periodic
    def tick(self) -> None:
        """Called once per step. Never raises: a bug in one part must not stop the desk."""
        try:
            self._tick()
        except Exception as exc:
            self.say("ERR", f"tick {type(exc).__name__}: {exc}")

    def _tick(self) -> None:
        """Posts anything missing, unbundles and escalates on time, offers unbooked gigs if enabled."""
        for gid, t0 in list(self.first_posts.items()):
            if self.now - t0 > 60:
                self.fast_book.append((t0, False))
                del self.first_posts[gid]
        for oid in list(self.orders):
            ob = self.orders[oid]
            if ob.order["status"] == "cancelled":
                continue
            self.dispatch_order(oid, "tick")
        if self.cfg.bundle:
            for rec in list(self.gigs.values()):
                if rec.status == "open" and len({o for o, _ in rec.legs}) > 1:
                    last = min(self.bundle_last.get(o, 0) for o, _ in rec.legs)
                    if last - self.now < self.cfg.unbundle_minutes:
                        self.unbundle(rec, "timeout")
        if self.cfg.view_raise_n:
            # Many drivers looked and none booked: the fee is short of the clearing fee. Raise once, now,
            # instead of waiting for the clock (a late raise finds drivers whose day is already planned).
            for rec in list(self.gigs.values()):
                if rec.status != "open" or rec.escalated or getattr(rec, "view_raised", False):
                    continue
                if len(self.gig_viewers.get(rec.id, ())) >= self.cfg.view_raise_n and self.now - rec.posted_at >= self.cfg.view_raise_after:
                    fee = int(round(self.gig_base(rec) * self.cfg.view_raise_mult))
                    cur = current_fee(rec.schedule, self.now)
                    if fee > cur:
                        sched = [x for x in rec.schedule if x["at"] > self.now and x["feeCents"] > fee]
                        rec.schedule = dedupe([{"at": self.now, "feeCents": fee}] + sched)
                        self.outbox.append({"type": "reprice", "gigId": rec.id, "schedule": rec.schedule})
                        self.say("VIEWRAISE", f"{rec.id} views={len(self.gig_viewers[rec.id])} {cur}->{fee}")
                    rec.view_raised = True
        if self.cfg.own_alarm:
            for rec in list(self.gigs.values()):
                if rec.status != "open" or rec.escalated:
                    continue
                ob = self.orders.get(rec.legs[0][0])
                if ob and self.last_pickup(ob, [l for _, l in rec.legs]) - self.now < self.cfg.alarm_minutes:
                    ob.urgent = True
                    self.escalate_gig(rec, "alarm")
        if self.cfg.viewer_offers:
            self.offer_viewers()

    def offer_viewers(self) -> None:
        """A driver who viewed our gig and did not book is active today and close by; in the app they may be
        waiting for a raise, but a direct offer they take as soon as it pays them."""
        cfg = self.cfg
        hour = (self.now % DAY) // 60
        if hour >= 23 or hour < 7:
            return
        for rec in list(self.gigs.values()):
            if rec.status != "open" or self.now - rec.posted_at < cfg.offer_after or self.open_offers[rec.id] >= 3:
                continue
            viewers = self.gig_viewers.get(rec.id, [])
            if not viewers:
                continue
            ob = self.orders.get(rec.legs[0][0])
            if not ob or (cfg.late_plan and self.is_late(ob, [l for _, l in rec.legs])):
                continue
            first = rec.stops[0]
            place = ob.order["legs"][first["leg"]]["pickup"]["placeId"]
            base = self.base_fee(ob, [l for _, l in rec.legs])
            fee = max(current_fee(rec.schedule, self.now), int(round(base * (cfg.offer_mult_urgent if ob.urgent else cfg.offer_mult))))
            cands = []
            for did in viewers:
                d = self.roster.get(did)
                if not d or (rec.id, did) in self.offered or self.offers_today[(did, self.now // DAY)] >= 3:
                    continue
                if rec.audience.get("manualLicence") and d["licence"] != "manual":
                    continue
                if rec.audience.get("experienced") and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                    continue
                where, at = self.positions.get(did, (d["homePlaceId"], -1))
                if at < self.now - 6 * HOUR:
                    where = d["homePlaceId"]
                dist = self.geo.air(where, place)
                if dist > cfg.offer_max_km:
                    continue
                cands.append((dist, did))
            cands.sort()
            for _, did in cands[: 3 - self.open_offers[rec.id]]:
                self.outbox.append({"type": "offer", "gigId": rec.id, "driverId": did, "feeCents": int(fee)})
                self.offers_today[(did, self.now // DAY)] += 1
                self.open_offers[rec.id] += 1
                self.offered.add((rec.id, did))
                self.offer_log.append((rec.id, did, fee / base, self.now))
                self.say("VOFFER", f"{rec.id} {did} {fee} x{fee/base:.2f}")


def steep(now: int, base: float, cfg: Config, floor: int = 0, plan: tuple = ()) -> list[dict]:
    out, prev = [], floor
    for i, m in enumerate(plan or cfg.steep_plan):
        fee = max(prev, int(round(base * m)))
        out.append({"at": now + i * cfg.steep_step, "feeCents": max(1, fee)})
        prev = fee
    return dedupe(out)


def dedupe(steps: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in steps:
        if out and s["at"] <= out[-1]["at"]:
            s = {"at": out[-1]["at"] + 1, "feeCents": s["feeCents"]}
        if out and s["feeCents"] <= out[-1]["feeCents"]:
            continue
        out.append(s)
    return out[:48]


def current_fee(schedule: list[dict], now: int) -> int:
    fee = schedule[0]["feeCents"]
    for s in schedule:
        if s["at"] <= now:
            fee = s["feeCents"]
    return fee


def decline_prices(r: dict) -> dict:
    o = r["options"][0]
    return {o["kind"]: o["listPriceCents"] * 5}
