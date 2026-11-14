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
from .policy import Governor, Market, OnTime, barrier_cents

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
    repair: bool = False    # a pair that took in one of our sitting singles (repair_split applies)
    relooked: bool = False  # the second look already raised it once

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


V5_PAIR2_SLACK = 360  # v5_pair2: a partner needs this many min to its last pickup (the 3 h warning + a pair's extra drive)
PAIR_END_RADIUS = 30  # pair_end / pair_long_empty: a chain end's supply = drivers living <= this many road min of it (PAIRS.md's nd30)
V5_SHORT_H = 8  # v5_short_open: ladder singles under this many hours to the last pickup (6-8 h cars paid 1.13x, 0-6 h 1.27x)


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
        self.held: dict[str, int] = {}  # order -> release minute (evening release)
        self._brake_at, self._brake_u, self._brake_x = -1, 0, 0.0  # backlog_brake cache (minute, cars, excess)
        self.chain_held: dict[str, int] = {}  # order -> minute to stop holding it for a chain partner and post it alone (chain planner)
        self.bundle_soon: set[str] = set()  # orders in a chain posted at short notice (split later, at bundle_soon_slack)
        self.morning_drops: dict[int, int] = defaultdict(int)
        self.night_drops: dict[int, int] = defaultdict(int)  # drops 00:00-01:00 per day (flu nights)
        self.flu_days: set = set()
        self.long_warns: list[int] = []  # minutes of deadline warnings on our long-drive orders (long_warn)
        self.long_warn_ids: list[tuple[int, str]] = []  # (minute, order) of the same warnings (long_warn_distinct)
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
        self._near_q: dict[tuple[str, int], int] = {}
        self.home_offered: set = set()  # gigs that already had their offer_home round
        self.pair_blocks: dict[str, tuple] = {}  # order -> (chains refused by the end guards, reason, drive, nd30) at the current decision
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
        self.gig_open: dict[str, int] = {}     # gig -> its first posted fee (relooks and escalations replace the schedule)
        self.bo_ratios: list[float] = []       # booked fee / first posted fee, per booking: this week's ladder climb
        self.gov_logged = -1
        self.warned: set[str] = set()  # orders that had a deadline warning
        self._strict_cfg: Optional[Config] = None
        self._fee1 = None  # Fee1 engine (fee1.py), built on first use when cfg.fee1
        self.scarce = False  # scarcity switch: this week drivers are scarce (FLEET's cheap openings read it too)
        self.scarce_hour = -1  # last hour boundary (minute // 60) the scarcity rule was checked at
        self.book_log: list[tuple[int, float]] = []  # (minute, booked fee / typical) of single-order gigs (scarcity)
        self.warn_log: list[tuple[int, str]] = []  # (minute, order) of deadline warnings (scarcity)
        self.won_log: list[int] = []  # minutes of our wins (scarcity)
        self.admitted: set[str] = set()  # requests quoted by safe_admit
        self.admits: dict[int, int] = defaultdict(int)  # day of quote -> safe_admit quotes (rebuilt by the replay of price requests)
        self._vol_off = False  # vol_guard tripped: no extra volume for the rest of the week

    # ------------------------------------------------------------------ helpers
    def say(self, code: str, detail: str = "") -> None:
        self.log.append(f"{self.now}\t{code}\t{detail}")

    @property
    def fee1(self):
        if self._fee1 is None:
            from .fee1 import Fee1
            self._fee1 = Fee1(self)
        return self._fee1

    def fee1_gig(self, rec: "GigRec") -> bool:
        """A gig on one fee chosen by fee1: one order, a one-step schedule, not escalated (stateless, so it survives a restart)."""
        return (bool(self.cfg.fee1) and not rec.escalated and len(rec.schedule) == 1 and len({o for o, _ in rec.legs}) == 1
                and not getattr(rec, "view_raised", False))

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
        if self.cfg.scarcity and not self.scarce:
            try:
                self.check_scarcity(e.get("at", self.now))
            except Exception as exc:
                self.say("ERR", f"scarcity {type(exc).__name__}: {exc}")
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
        self.won_log.append(e["at"])
        self.observe_outcome(o["id"], e["at"], True)
        if self.cfg.hold:
            rel = self.release_at(ob)
            if rel is not None:
                self.held[o["id"]] = rel
                self.say("HOLD", f"{o['id']} until {rel}")
                return
        self.dispatch_order(o["id"], "won")

    def on_order_lost(self, e: dict) -> None:
        self.observe_outcome(e["requestId"], e["at"], False)

    def observe_outcome(self, rid: str, at: int, won: bool) -> None:
        """One observation per request: our best offer over list, trust removed, against win or loss."""
        r = self.requests.get(rid)
        q = self.quoted.get(rid, {})
        if not r or not q or self.cfg.experiment_quote:
            return
        fastest = r["options"][0]
        if self.cfg.learn_fastest and not (fastest["kind"] in q and q[fastest["kind"]] < 3 * fastest["listPriceCents"]):
            return  # a loss here says the dealer wanted speed, not that our price was high
        ratios = [q[o["kind"]] / o["listPriceCents"] for o in r["options"] if o["kind"] in q and q[o["kind"]] < 3 * o["listPriceCents"]]
        if self.cfg.menu and ratios:
            # Menu pricing learns the lowest price + speed offset, in units of the fastest option's list.
            s0 = self.market.speed_offset(fastest["kind"])
            ratios = [min((q[o["kind"]] + (self.market.speed_offset(o["kind"]) - s0) * self.trust_factor(r["dealerId"])) / fastest["listPriceCents"]
                          for o in r["options"] if o["kind"] in q and q[o["kind"]] < 3 * o["listPriceCents"])]
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
            if rec.status == "open" and self.fee1_gig(rec):
                self.fee1.close(rec, True, e["at"])
            rec.status, rec.driver, rec.fee = "booked", e["driverId"], e["feeCents"]
            t0 = self.first_posts.pop(rec.id, None)
            if t0 is not None:
                self.fast_book.append((t0, e["at"] - t0 <= 60 and e["feeCents"] <= rec.schedule[0]["feeCents"]))
            ob = self.orders.get(rec.legs[0][0])
            if ob:
                self.book_ratios.append(e["feeCents"] / max(1.0, self.gig_base(rec)))
                if rec.id in self.gig_open:
                    self.bo_ratios.append(e["feeCents"] / max(1, self.gig_open[rec.id]))
                if len({o for o, _ in rec.legs}) == 1:
                    self.book_log.append((e["at"], e["feeCents"] / max(1.0, self.gig_base(rec))))
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
        if h == 0 and self.cfg.flu_drops:
            self.night_drops[day] += 1
            if self.night_drops[day] == self.cfg.flu_drops:
                # A flu night: drivers give back that day's bookings at once; cars due that day end late ~1.9x as often.
                self.flu_days.add(day)
                n = 0
                for oid in sorted(self.orders):
                    ob = self.orders[oid]
                    if oid in self.ontime_orders or oid in self.late_orders:
                        continue
                    if max(self.deadline(ob.order, l) for l in range(len(ob.order["legs"]))) // DAY == day:
                        ob.p_ok = max(0.0, 1 - (1 - ob.p_ok) * self.cfg.flu_mult); n += 1
                self.say("FLU", f"day {day}: {self.night_drops[day]} drops 00-01h; {n} open orders due today reweighted")
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
        if self.cfg.bundle_keep and len({o for o, _ in rec.legs}) > 1:
            # A dropped pair notifies again in the app. With time to spare, keep the pair (one driver, two cars)
            # and raise it a little, instead of two singles at once; the unbundle timer still splits it later.
            last = min(self.bundle_last.get(o, 0) for o, _ in rec.legs)
            if last - self.now > self.cfg.unbundle_minutes + 2 * HOUR:
                fee = max(current_fee(rec.schedule, self.now), int(round(self.gig_base(rec) * self.cfg.bundle_keep)))
                rec.schedule = dedupe([{"at": self.now, "feeCents": fee}] + [x for x in rec.schedule if x["at"] > self.now and x["feeCents"] > fee])
                self.outbox.append({"type": "reprice", "gigId": rec.id, "schedule": rec.schedule})
                self.say("KEEP_BUNDLE", f"{gid} fee={fee}")
                return
        if self.cfg.drop_calm_hours and why == "dropped" and len({o for o, _ in rec.legs}) == 1:
            ob = self.orders.get(rec.legs[0][0])
            legs = [l for _, l in rec.legs]
            if ob and not ob.urgent and self.last_pickup(ob, legs) - self.now > self.cfg.drop_calm_hours * HOUR:
                # Plenty of time left: post it again at the opening fee. A new post notifies nearby drivers (~10 views
                # in 30 min); escalating paid 1.24-1.31x typical for drops with > 16 h left that were only 2-4% late.
                self.withdraw(gid)
                self.dispatch_order(ob.order["id"], "drop-repost")
                self.say("DROP_REPOST", f"{gid} {ob.order['id']} left={(self.last_pickup(ob, legs) - self.now) // 60}h")
                return
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
            if self.cfg.backhaul:
                end = self.gig_end(rec, e["orderId"], e.get("leg", 0), e["placeId"], e["at"])
                if end:
                    self.backhaul(rec.driver, rec, *end)

    def on_delivered(self, e: dict) -> None:
        rec = self.gigs.get(e["gigId"])
        if rec and rec.driver:
            self.positions[rec.driver] = (e["placeId"], e["at"])
            last = rec.stops[-1]
            if self.cfg.backhaul and last["orderId"] == e["orderId"] and last["leg"] == e["leg"] and last["kind"] == "delivery":
                self.backhaul(rec.driver, rec, e["placeId"], e["at"])
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
        self.warned.add(e["orderId"])
        self.warn_log.append((e["at"], e["orderId"]))
        if self.cfg.long_warn:
            o = ob.order
            if sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in o["legs"]) >= self.cfg.long_warn[0]:
                self.long_warns.append(e["at"])
                self.long_warn_ids.append((e["at"], e["orderId"]))
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
        barrier = barrier_cents(self.gov.projection(), len(self.orders), cfg.late_barrier) if cfg.late_barrier else 0.0
        brake = 1.45 * min(1.0, cfg.backlog_brake[4] * self.brake_excess() ** 2) if cfg.backlog_brake else 0.0
        drive = sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        if cfg.long_warn and drive >= cfg.long_warn[0]:
            recent = sum(1 for t in self.long_warns if t >= self.now - cfg.long_warn[2])
            if cfg.long_warn_distinct:
                # Count cars, not warning events: a car re-planned after a missed collection is warned again and again
                # (ARCHIVE D_LONGWARN.md: dev-40, one car warned 5x drove 85 declines).
                recent = len({o for t, o in self.long_warn_ids if t >= self.now - cfg.long_warn[2]})
            if recent >= cfg.long_warn[1]:
                # Our long cars are going unbooked this week: a new long car would wait for drivers who are not there.
                return decline_prices(r), f"DECLINE long {drive} min: {recent} long cars warned in {cfg.long_warn[2]} min"
        if self.scarce and cfg.scarcity_long and drive >= cfg.scarcity_long:
            # A scarce week: long cars wait for drivers who are not there (long_warn's class, decided for the whole week).
            return decline_prices(r), f"DECLINE scarce long {drive} min"
        cost = r["referenceFeeCents"] * (cfg.quote_cost_hold or (self.drive_cost_mult(drive) if cfg.drive_cost else self.cost_mult()))
        if cfg.quote_cost_hold and cfg.quote_cost_floor:
            # fee1's savings stop the quote's fall below the hold, nothing more: never under the base's quote, and a week where
            # drivers cost more (scarcity, or Monday's prior) still raises it.
            cost = max(cost, r["referenceFeeCents"] * self.cost_mult())
        if cfg.hold_price and self.pairs_with_held(r):
            cost *= cfg.bundle_mult  # a held car for the same day starts or ends near this one: the evening release pairs them
        elif cfg.bundle_price and self.chainable(r):
            cost *= cfg.bundle_mult  # one of our open gigs ends where this car starts (or the reverse): a driver can take both
        backlog = self.backlog(r["legs"][0]["pickup"]["placeId"])
        t_gain, t_loss = self.trust_value(dealer)
        congestion = cfg.cong_frac * r["referenceFeeCents"] * max(0, backlog - cfg.cong_free)
        prices: dict = {}
        meta: dict = {}
        info = []
        cands: list = []
        admits: list = []  # safe_admit candidates (kind, opt, p_ok, load, ratio, ev, cost), used only if nothing else is quoted
        for opt in r["options"]:
            kind = opt["kind"]
            if kind not in cfg.quote_options:
                continue
            if cfg.only_next_if_no_same and kind == "next_day" and "same_day" in prices:
                info.append("next_day:skip(same_day quoted)")
                continue
            p_ok, slack = self.ontime.p_ok(r, opt["deadline"], kind)
            p_ok = min(0.99, p_ok * cal)
            if self.flu_days and self.deadline_day(r, opt) in self.flu_days:
                p_ok = max(0.0, 1 - (1 - p_ok) * cfg.flu_mult)  # due on a flu day (see on_gig_dropped)
            if p_ok < bar or slack < cfg.min_slack_h:
                info.append(f"{kind}:skip(p={p_ok:.2f},s={slack:.1f})")
                continue
            # Load: our cars already due that day against the world's drivers. Lateness grows with it
            # (lab: 2.7% late under 6% of drivers, 8.7% at 9-12%, 12% above 15%), so a busy day's next car costs more.
            dday = self.deadline_day(r, opt)
            load = self.due_load(dday)
            if cfg.load_cap and load >= cfg.load_cap:
                info.append(f"{kind}:skip(load={load:.3f})")  # a day this full makes its cars late (12-13% at 0.14+ vs 4-6% under 0.12)
                continue
            free = cfg.load_free_mon2 if (cfg.load_free_mon2 and dday >= 7 and (not cfg.mon2_max_drive or drive < cfg.mon2_max_drive)) else cfg.load_free
            per_car = cfg.load_flat_cents if cfg.load_flat_cents else r["referenceFeeCents"]
            slope = cfg.load_slope
            if cfg.load_desert_n and self.home_near_delivery(r["legs"][-1]["delivery"]["placeId"], 60) <= cfg.load_desert_n:
                # Few drivers live near the delivery: an extra car there takes one of the few drivers our other cars need.
                free, slope = cfg.load_free, cfg.load_desert_slope
            load_cost = slope * per_car * max(0.0, load - free * self.capacity_factor()) / 0.05
            risk_frac = (1 - p_ok) * cfg.late_cost_frac * self.pl_factor(drive)
            if self.scarce:
                risk_frac *= cfg.scarcity_risk  # a scarce week's late risk is above the model's: risky classes quoted up
            short = 0.0
            if cfg.short_fee and drive >= cfg.short_fee[1]:
                lead_h = (self.est_last_pickup(r, opt["deadline"]) - r["respondBy"]) / 60
                if lead_h < cfg.short_fee[0]:
                    short = cost * (cfg.short_fee[2] - 1)  # a long car won at short notice pays well over the usual fee
                    info.append(f"sfee={kind}/{lead_h:.1f}h")
            load_cost += short
            # late_barrier: what this car's lateness risk costs the week's on-time share. late_barrier_free: a car at most this likely
            # to be late pays nothing (it dilutes the late ones: dev-05, v5La's barrier charged safe cars too and won 0 orders Tue-Fri).
            free_late = cfg.late_barrier_free if not (cfg.late_barrier_free_load and load >= cfg.late_barrier_free_load) else 0.0
            load_cost += max(0.0, 1 - p_ok - free_late) * barrier  # (a crowded deadline day: no free share, its safe cars go late too)
            load_cost += brake * (520 + 135 * drive / 60 + 0.24 * r["referenceFeeCents"])  # backlog_brake (RoutePulse's unit, cents)
            # Dealer trust (level 8): an on-time car raises this dealer's future prices by 1%, a late one halves the count.
            trust_adj = cfg.trust_bonus * ((1 - p_ok) * t_loss - p_ok * t_gain) + cfg.trust_loss_w * (1 - p_ok) * t_loss
            # Under the on-time target, a safe car is worth more than its margin: it dilutes the late ones.
            if gate and p_ok >= cfg.gate_safe_p and not (cfg.gate_load_max and load >= cfg.gate_load_max):
                trust_adj -= gate  # (gate_load_max: only on days with room, or the bonus overloads them; dev-17 Mon2 0.17 -> 0.23)
            if cfg.menu:
                cands.append((kind, opt["listPriceCents"], self.market.speed_offset(kind), risk_frac, cfg.shadow_cents + congestion + trust_adj + load_cost))
                meta[kind] = p_ok
                info.append(f"{kind}:p={p_ok:.2f},L={load:.3f}")
                continue
            c_opt = cost
            if cfg.quote_move_cost:
                # The fee rule opens cheap where drivers live near the delivery and the pickup is far off: quote that cost.
                c_opt = cost * self.move_cost(r, opt) / max(1.0, r["referenceFeeCents"] * self.cost_mult())
            ratio, ev = self.market.best_ratio(dealer, day, opt["listPriceCents"], tf, c_opt, risk_frac, cfg.shadow_cents + congestion + trust_adj + load_cost, r["legs"][0]["pickup"]["placeId"], lane_of(r))
            if ratio <= 0 or ev < cfg.min_ev_cents:
                adm = self.safe_admit(r, opt, p_ok, drive, dday, load, dealer, day, tf, risk_frac, cfg.shadow_cents + congestion + trust_adj + load_cost)
                if adm is None:
                    info.append(f"{kind}:noev")
                    continue
                # Admits wait for the end of the loop: they count only when no option of this request makes margin as it is
                # (MARKET review: 40% of admits sat next to a normal quote, so an admit could undercut our own normal option).
                admits.append((kind, opt, p_ok, load) + tuple(adm))
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
        if admits and not prices:
            for kind, opt, p_ok, load, ratio, ev, c_adm in admits:
                prices[kind] = int(round(opt["listPriceCents"] * ratio * tf))
                meta[kind] = p_ok
                info.append(f"{kind}:admit(r={ratio:.2f},p={p_ok:.2f},ev={ev/100:.0f},c={c_adm/100:.0f},L={load:.3f})")
            if r["id"] not in self.admitted:  # one count per request (a rejoin quotes open requests again)
                self.admitted.add(r["id"])
                self.admits[self.now // DAY] += 1
        if cfg.menu and cands:
            place = r["legs"][0]["pickup"]["placeId"]
            fast = r["options"][0]
            prices, ev = self.market.best_menu(dealer, day, fast["listPriceCents"], tf, cost, cands, place, lane_of(r))
            if ev < cfg.min_ev_cents:
                prices = {}
                info.append("menu:noev")
            else:
                info.append(f"menu:ev={ev/100:.0f} " + ",".join(f"{k}={v/next(o['listPriceCents'] for o in r['options'] if o['kind'] == k):.2f}" for k, v in prices.items()))
            meta = {k: v for k, v in meta.items() if k in prices}
        if cfg.s_cap_cents and "same_day" in prices and "next_day" in prices and prices["same_day"] > prices["next_day"] + cfg.s_cap_cents - 100:
            # Past the dealer's euros for speed it takes next_day for less: sell same_day just inside that gap instead.
            info.append(f"scap {prices['same_day']}->{prices['next_day'] + cfg.s_cap_cents - 100}")
            prices["same_day"] = prices["next_day"] + cfg.s_cap_cents - 100
        if cfg.steer and "same_day" in prices and "next_day" in prices:
            # Steer dealers to next_day: it pays more per car, can wait for the evening release and pair, and a
            # pickup the day before the deadline costs less than one on the deadline day.
            s, n = prices["same_day"], prices["next_day"]
            if cfg.steer_down:
                prices["next_day"] = min(n, max(int(round(s * cfg.steer)), int(next(o["listPriceCents"] for o in r["options"] if o["kind"] == "next_day") * cfg.min_ratio)))
            else:
                prices["same_day"] = max(s, int(round(n / cfg.steer)))
            info.append(f"steer {s}/{n}->{prices['same_day']}/{prices['next_day']}")
        self.quote_meta[r["id"]] = meta
        head = f"bar={bar:.2f} bl={backlog} tg={t_gain/100:.0f} tf={tf:.2f} mu={self.market.mu_for(dealer, day, r["legs"][0]["pickup"]["placeId"]):.3f} cost={cost/100:.0f}"
        if cfg.late_barrier:
            head += f" lb={barrier/100:.0f}"  # late_barrier: euros per expected late car right now
        if cfg.backlog_brake:
            head += f" bk={self._brake_u}/{brake:.2f}"  # backlog_brake: driverless cars due soon / charge in units
        if not prices:
            return decline_prices(r), f"DECLINE {head} {' '.join(info)}"
        return prices, f"{head} {' '.join(info)}"

    def safe_admit(self, r: dict, opt: dict, p_ok: float, drive: int, dday: int, load: float, dealer: str, day: int, tf: float,
                   risk_frac: float, extra: float) -> Optional[tuple[float, float, float]]:
        """A safe car the quote cost declines for no margin: (ratio, ev, cost) at the true fleet cost, or None. Admits only, never
        reprices a car we quote anyway (MARKET: quoting everything at the lower cost was -396/wk at equal orders, the load charge binds)."""
        cfg = self.cfg
        if not cfg.safe_admit or self.scarce or cfg.menu:
            return None
        p_min, mult, max_load = cfg.safe_admit
        q = r["legs"][-1]["delivery"]["placeId"]
        if p_ok < p_min or drive >= cfg.safe_admit_drive or load >= max_load or (dday == 4 and not cfg.safe_admit_fri):
            return None
        if cfg.desert_n and self.desert(q):
            return None
        c = r["referenceFeeCents"] * mult
        if cfg.safe_admit_fee1 and cfg.fee1:
            fq = self.fee1.quote_cost(r, opt)
            if fq is not None:
                c = min(c, fq[1])  # fee1's own expected fee + rescue cost of moving this car alone
        ratio, ev = self.market.best_ratio(dealer, day, opt["listPriceCents"], tf, c, risk_frac, extra, r["legs"][0]["pickup"]["placeId"], lane_of(r))
        if ratio <= 0 or ev < cfg.min_ev_cents:
            return None
        return ratio, ev, c

    def switch_cfg(self, kw: dict) -> None:
        """From now on the week runs on cfg with these overrides: price(), due_load() and dispatch read self.cfg; the market's copy and
        a strict governor's cached config follow (the replay flips at the same event, so a restart rebuilds the same config)."""
        old = self.cfg
        self.base_cfg = old
        self.cfg = old.with_(**kw)
        for part in (self.market, self.ontime, self.gov):
            if getattr(part, "cfg", None) is old:
                part.cfg = self.cfg
        if self._strict_cfg is not None:
            self._strict_cfg = self._strict_cfg.with_(**kw)

    def check_scarcity(self, t: int) -> None:
        """The week-level switch: at each hour boundary H from scarcity_from to scarcity_until that time t has passed, the last 24 h
        before H (events at < H only, so a replay flips at the same H) are scarce if booked single-gig fee/typical >= fee_typ or warned
        cars / won cars >= warned_share. Sticky: once scarce, scarce for the week."""
        cfg = self.cfg
        hi = min(t, cfg.scarcity_until) // 60
        start = min(cfg.scarcity_from, cfg.scarcity_z[6]) if len(cfg.scarcity_z) > 6 else cfg.scarcity_from
        h = max(self.scarce_hour + 1, -(-start // 60))
        while h <= hi and not self.scarce:
            self.scarce_hour = h
            H = h * 60
            fees = [x for at, x in self.book_log if H - DAY <= at < H]
            won = sum(1 for at in self.won_log if H - DAY <= at < H)
            warned = len({o for at, o in self.warn_log if H - DAY <= at < H})
            fee = sum(fees) / len(fees) if len(fees) >= cfg.scarcity_min_n else 0.0
            share = warned / won if won >= cfg.scarcity_min_n else 0.0
            f_lim, w_lim = cfg.scarcity
            if cfg.scarcity_z:
                # Standardized sum of both Tuesday signals against normal weeks (PROBE's 228 labelled weeks: z >= 2.5 flags 35% of
                # bad weeks at 4% false alarms; fee AND warned at best 28% / 4%, fee OR warned 37% / 11%; research/re/fleet/scar_rules.out).
                mf, sf, mw, sw, thr = cfg.scarcity_z[:5]
                if H < cfg.scarcity_from:
                    # Early tier (scarcity_z[5] from minute scarcity_z[6]): only an extreme week flips before Tuesday midnight. nf-04's z was
                    # 8.4 at Tue 12:00 and 16.6 at Tue 18:00; no normal tuning week passed 5.6 by Tue 18:00 (research/re/fleet/zcurve.py).
                    thr = cfg.scarcity_z[5]
                hit = fee > 0 and won >= cfg.scarcity_min_n and (fee - mf) / sf + (share - mw) / sw >= thr
            else:
                hit = fee >= f_lim or share >= w_lim
            if hit:
                self.scarce = True
                self.say("SCARCE", f"at {H}: fee/typ={fee:.3f} (n={len(fees)}, >= {f_lim}) warned/won={warned}/{won}={share:.3f} (>= {w_lim})"
                         f": no safe_admit, long >= {cfg.scarcity_long} declined, risk x{cfg.scarcity_risk}, set {dict(cfg.scarce_set)}")
                if cfg.scarce_set:
                    self.switch_cfg(dict(cfg.scarce_set))
            h += 1
        self.scarce_hour = max(self.scarce_hour, hi)

    def pl_factor(self, drive: int) -> float:
        """Calibration of the on-time model by drive time (pl_cal): it over-predicts lateness of 1-6 h drives and
        under-predicts it beyond 6 h (lab/build/fit_late.py)."""
        for limit, f in self.cfg.pl_cal:
            if drive < limit:
                return f
        return 1.0

    def deadline_day(self, r: dict, opt: dict) -> int:
        d = opt["deadline"]
        ns = self.note(r["id"])
        if ns and ns[0].deadline:
            d = min(d, ns[0].deadline)
        return d // DAY

    def est_last_pickup(self, r: dict, deadline: int) -> int:
        """lastPickupAt before the win: the latest pickup inside the pickup's hours (or slot) that reaches the delivery while
        it is open, by the deadline (a note's tighter one included). Matches the world's on 85% of won cars to the minute,
        97% within 30 min; deadline - drive alone misses a quarter of the cars under 8 h (research/re/market/SHORT_NOTICE.md)."""
        L0 = r["legs"][0]
        drive = sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        n = self.leg_note(r["id"], 0)
        if n.deadline:
            deadline = min(deadline, n.deadline)
        dw, pw = L0["delivery"]["window"], L0["pickup"]["window"]
        priv_d, priv_p = L0["delivery"]["privateAddress"], L0["pickup"]["privateAddress"]
        dend = min(deadline, dw["to"]) if priv_d else deadline
        iv = open_intervals(None if priv_d else L0["delivery"]["hours"], dend - 4 * DAY, dend)
        if iv:
            dend = iv[-1][1]
        pend = min(dend - drive, pw["to"])
        iv = open_intervals(None if priv_p else L0["pickup"]["hours"], pend - 4 * DAY, pend)
        return iv[-1][1] if iv else pend

    def nearby(self, place: str) -> list[tuple[str, float]]:
        """Places within 80 km (the outage radius in RULES.md), weighted 1 at the place down to 0.3 at 80 km."""
        if place not in self._nearby:
            self._nearby[place] = [(p, 1.0 - 0.7 * self.geo.air(place, p) / 80.0) for p in self.geo.ids if self.geo.air(place, p) <= 80.0]
        return self._nearby[place]

    def capacity_factor(self) -> float:
        """How easily our gigs find drivers this week: the share of first posts booked within an hour at the
        opening fee, over the share we usually see (0.7). More easy bookings, more room per day."""
        f = 1.0
        if self.cfg.backlog_brake and self.cfg.backlog_brake[5]:
            _, _, _, _, _, hw, hmin = self.cfg.backlog_brake
            f = min(1.0, max(hmin, 1.0 - hw * min(1.4, self.brake_excess())))  # drivers are not taking our cars: less room per day
        if not self.cfg.adaptive_load:
            return f
        done = [ok for (at, ok) in self.fast_book[-60:]]
        if len(done) < 15:
            return f
        rate = (sum(done) + 0.7 * 10) / (len(done) + 10)
        return f * min(self.cfg.cap_max, max(self.cfg.cap_min, rate / 0.7))

    def unbooked_due(self) -> int:
        """Our won cars still without a driver whose last pickup is within the brake's horizon (backlog_brake)."""
        horizon = self.cfg.backlog_brake[3] * HOUR
        n = 0
        for oid in sorted(self.orders):
            if oid in self.ontime_orders or oid in self.late_orders:
                continue
            ob = self.orders[oid]
            legs = [l for l, t in enumerate(ob.order["deliveredAt"]) if t is None]
            if not legs or all((g := self.leg_gig.get((oid, l))) and self.gigs[g].status in ("booked", "working", "done") for l in legs):
                continue
            if self.last_pickup(ob, legs) - self.now <= horizon:
                n += 1
        return n

    def brake_excess(self) -> float:
        """How far our driverless backlog is over its soft limit, in units of scale (backlog_brake); cached per world minute."""
        if self._brake_at != self.now:
            soft_frac, soft_min, scale, *_ = self.cfg.backlog_brake
            self._brake_u = self.unbooked_due()
            soft = max(soft_min, soft_frac * len(self.roster))
            self._brake_x = max(0.0, (self._brake_u - soft) / scale)
            self._brake_at = self.now
        return self._brake_x

    def volume_ok(self) -> bool:
        """vol_guard (min orders, warned share, fee/typical): the week is not spiralling. Once 'warned share' of our orders had a
        deadline warning, or our last 60 bookings paid 'fee/typical' on average, extra volume stops for the rest of the week (sticky).
        nf-04-type weeks (warned 21%, fee 1.30x) tipped under 0.90 with every volume arm; normal weeks stay <= 5.7% / 1.06x by Thursday."""
        g = self.cfg.vol_guard
        if not g:
            return True
        if self._vol_off:
            return False
        n_min, w_max, f_max = g
        if self.won_count >= n_min:
            xs = self.book_ratios[-60:]
            if len(self.warned) / max(1, self.won_count) >= w_max or (len(xs) >= 30 and sum(xs) / len(xs) >= f_max):
                self._vol_off = True
                self.say("VOL_OFF", f"warned {len(self.warned)}/{self.won_count}, fee/typ {sum(xs) / max(1, len(xs)):.2f}: no extra volume this week")
                return False
        return True

    def due_load(self, day: int) -> float:
        """Our orders due on this day (won, not cancelled), over the number of drivers in the world."""
        n = self.due_count.get(day, 0)
        if self.cfg.load_bundle_w < 1.0 and self.volume_ok():
            chained = 0
            for rec in self.gigs.values():
                oids = {o for o, _ in rec.legs}
                if len(oids) > 1 and rec.status in (("booked", "working") if self.cfg.load_bundle_booked else ("open", "booked", "working")):
                    for o in oids:
                        ob = self.orders.get(o)
                        if ob and min(self.deadline(ob.order, l) for l in range(len(ob.order["legs"]))) // DAY == day:
                            chained += 1
            n -= (1 - self.cfg.load_bundle_w) * chained
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

    def move_cost(self, r: dict, opt: dict) -> float:
        """Expected driver fee in cents for a request's option: typical fee x this week's fee level, scaled by the opening
        fee_open_rule would give it (cheap where drivers live near the delivery and the pickup is far off). For the quote."""
        drive = sum(self.geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in r["legs"])
        cost = r["referenceFeeCents"] * (self.drive_cost_mult(drive) if self.cfg.drive_cost else self.cost_mult())
        if (self.cfg.fee_open_rule or self.cfg.fee_open_day) and len(r["legs"]) == 1:
            L = r["legs"][0]
            last = min(opt["deadline"], L["pickup"]["window"]["to"] + drive) - drive
            left = (last - self.now) / HOUR
            nd = self.home_near_delivery(L["delivery"]["placeId"])
            day_mult = self.day_open(left, nd)
            if day_mult:
                return cost * day_mult / self.cfg.fee_open
            for hours, n, mult in self.cfg.fee_open_rule:
                if left >= hours and nd >= n:
                    cost *= mult / self.cfg.fee_open
                    break
        return cost

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
        if oid in self.held:
            if self.held[oid] > self.now:
                return
            del self.held[oid]
        legs = [l for l in self.undelivered(oid) if (oid, l) not in self.leg_gig and not self._pending(oid, l)]
        if not legs:
            return
        if self.cfg.bundle and self.cfg.hold_minutes and (why == "won" or oid in self.chain_held) and legs == [0] and len(ob.order["legs"]) == 1 and self.simple(ob):
            # Chain planner: hold the car a while. Most cars are won hours before they are ready, and a partner whose
            # pickup is near this car's delivery lets one driver take both for less than two gigs.
            until = self.chain_held.setdefault(oid, self.hold_until(ob))
            if self.try_bundle(ob):
                return
            if self.now < until:
                return
            self.chain_held.pop(oid, None)
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
        for oid2 in self.chain_held:
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

    def pairs_with_held(self, r: dict) -> bool:
        """A one-car dealer-to-dealer request whose pickup day has a held car that ends near its pickup or starts
        near its delivery (rough check at quote time; the release runs the full check)."""
        if len(r["legs"]) != 1 or not self.held:
            return False
        L = r["legs"][0]
        if L["pickup"]["privateAddress"] or L["delivery"]["privateAddress"]:
            return False
        p, d, day = L["pickup"]["placeId"], L["delivery"]["placeId"], L["pickup"]["window"]["from"] // DAY
        km = self.cfg.hold_km or self.cfg.bundle_km
        for oid in sorted(self.held):
            ob = self.orders.get(oid)
            if not ob or len(ob.order["legs"]) != 1:
                continue
            O = ob.order["legs"][0]
            if O["pickup"]["window"]["from"] // DAY != day:
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
        if cfg.bundle_empty_end and dA + tr + dB > cfg.bundle_empty_end[0] and                 self.home_near_delivery(LB["delivery"]["placeId"]) < cfg.bundle_empty_end[1]:
            return None  # a long chain ending where few drivers live: 45% booked in 60 min, 18.5% warned (PAIRS.md)
        start = max(self.now + cfg.bundle_lead, LA["pickup"]["window"]["from"])
        soon = start - self.now < cfg.bundle_soon_lead
        if start - self.now < cfg.bundle_min_lead and not soon:
            return None
        a_del = start + dA
        if a_del > self.deadline(A.order, 0) - cfg.bundle_margin:
            return None
        b_pick = max(a_del + tr, LB["pickup"]["window"]["from"])
        if b_pick > LB["pickup"]["window"]["to"] or b_pick + dB > self.deadline(B.order, 0) - cfg.bundle_margin:
            return None
        last = min(self.last_pickup(A, [0]), self.last_pickup(B, [0]) - dA - tr)
        if last - self.now < (cfg.bundle_soon_slack + 60 if soon else cfg.bundle_min_slack):
            return None
        if self.pair_blocked(dA + tr + dB, LB["delivery"]["placeId"], [A, B]):
            return None
        return last

    # ------------------------------------------------------------------ chain planner (hold_minutes)
    def hold_until(self, ob: OrderBook) -> int:
        cfg = self.cfg
        L = ob.order["legs"][0]
        return min(self.now + cfg.hold_minutes, L["pickup"]["window"]["from"] - cfg.hold_lead, self.last_pickup(ob, [0]) - cfg.hold_slack)

    def chain_key(self, last: int, first: OrderBook, second: OrderBook) -> float:
        """Rank of a feasible pair among a car's candidate partners (higher wins). Base, in minutes: the latest chain start
        (most slack), or minus the chain's drive with bundle_short. With pair_end, end_score() adds the end's drivers."""
        if not self.cfg.bundle_short:
            base = last
        else:
            A, B = first.order["legs"][0], second.order["legs"][0]
            g = self.geo
            base = -(g.drive(A["pickup"]["placeId"], A["delivery"]["placeId"]) + g.drive(A["delivery"]["placeId"], B["pickup"]["placeId"])
                     + g.drive(B["pickup"]["placeId"], B["delivery"]["placeId"]))
        return self.end_score(base, second.order["legs"][0]["delivery"]["placeId"])

    def end_score(self, base: float, end: str) -> float:
        """pair_end (R1): a candidate chain's score, in hours = base / 60 + w x ln(1 + nd30(end)), where base is the old key in
        minutes (higher better) and nd30 counts drivers living <= 30 road min of the chain's final delivery. Pairs book by their
        end (AUC .65-.68; hop .51, start .52; PAIRS.md), so the end decides and the old key breaks near-ties. Off: base unchanged."""
        if not self.cfg.pair_end:
            return base
        return base / 60.0 + self.cfg.pair_end[0] * math.log1p(self.home_near_delivery(end, PAIR_END_RADIUS))

    def pair_blocked(self, drive: int, end: str, seq: list) -> bool:
        """The end guards on a chain that fits in time (chain(), chain_seq()): R2 pair_long_empty (long chain into an empty town)
        and pair_end's min_nd. Blocked chains are noted per car for the caller's PAIR_BLOCK line (pair_block_note)."""
        cfg = self.cfg
        if not cfg.pair_long_empty and not (cfg.pair_end and cfg.pair_end[1] > 0):
            return False
        nd = self.home_near_delivery(end, PAIR_END_RADIUS)
        why = ""
        if cfg.pair_long_empty and drive > cfg.pair_long_empty[0] and nd <= cfg.pair_long_empty[1]:
            why = "long-empty"
        elif cfg.pair_end and cfg.pair_end[1] > 0 and nd < cfg.pair_end[1]:
            why = "end-min"
        if not why:
            return False
        for x in seq:
            n, w0, d0, nd0 = self.pair_blocks.get(x.order["id"], (0, why, drive, nd))
            self.pair_blocks[x.order["id"]] = (n + 1, w0, d0, nd0)
        return True

    def pair_block_note(self, singles: list) -> None:
        """One PAIR_BLOCK line per car posted alone at this decision that had a fitting partner the end guards refused."""
        for ob in singles:
            b = self.pair_blocks.get(ob.order["id"])
            if b:
                self.say("PAIR_BLOCK", f"{ob.order['id']} single: {b[1]} x{b[0]} (first: drive={b[2]} nd30={b[3]})")
        self.pair_blocks.clear()

    def chain_seq(self, seq: list[OrderBook]) -> Optional[int]:
        """chain() for any number of cars: one driver takes them in this order, all on time with room to spare."""
        cfg, geo = self.cfg, self.geo
        Ls = [x.order["legs"][0] for x in seq]
        t = start = max(self.now + cfg.bundle_lead, Ls[0]["pickup"]["window"]["from"])
        if start - self.now < cfg.bundle_min_lead:
            return None
        drive, last = 0, None
        for i, (x, L) in enumerate(zip(seq, Ls)):
            if i:
                prev = Ls[i - 1]["delivery"]["placeId"]
                if geo.air(prev, L["pickup"]["placeId"]) > cfg.bundle_km:
                    return None
                tr = geo.drive(prev, L["pickup"]["placeId"])
                t, drive = t + tr, drive + tr
                t = max(t, L["pickup"]["window"]["from"])
                if t > L["pickup"]["window"]["to"]:
                    return None
            lp = self.last_pickup(x, [0]) - (t - start)  # latest chain start that still reaches this pickup in time
            last = lp if last is None else min(last, lp)
            d = geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"])
            t, drive = t + d, drive + d
            if t > self.deadline(x.order, 0) - cfg.bundle_margin:
                return None
        if drive > min(12 * HOUR - 30, cfg.bundle_max_drive) or last - self.now < cfg.bundle_min_slack:
            return None
        if self.pair_blocked(drive, Ls[-1]["delivery"]["placeId"], seq):
            return None
        return last

    def try_extend(self, ob: OrderBook) -> bool:
        """Add this car to one of our open two-car chains, in front or behind, if one driver can still take all three."""
        if not self.simple(ob):
            return False
        best = None
        for rec in self.gigs.values():
            oids = [o for o, _ in rec.legs]
            if rec.status != "open" or rec.escalated or len(oids) != 2 or len(set(oids)) != 2 or self.now - rec.posted_at > self.cfg.bundle_window:
                continue
            pair = [self.orders.get(o) for o in oids]
            if any(x is None or x is ob for x in pair):
                continue
            for seq in ([ob] + pair, pair + [ob]):
                last = self.chain_seq(seq)
                if last is None:
                    continue
                key = self.end_score(last, seq[-1].order["legs"][0]["delivery"]["placeId"])
                if best is None or key > best[0]:
                    best = (key, last, seq, rec)
        if not best:
            return False
        _, last, seq, rec = best
        self.withdraw(rec.id)
        self.chain_held.pop(ob.order["id"], None)
        stops = [st for x in seq for st in self.stops_for(x, 0)]
        audience = {"experienced": any(x.order["legs"][0]["car"]["premium"] for x in seq), "manualLicence": False}
        base = sum(self.base_fee(x, [0]) for x in seq)
        out = [{"at": self.now, "feeCents": int(round(base * self.cfg.bundle3_mult * self.cfg.fee_open))}]
        prev = out[0]["feeCents"]
        for hours_before, mult in self.cfg.fee_rel:
            fee = max(prev, int(round(base * self.cfg.bundle3_mult * mult)))
            out.append({"at": max(self.now + self.cfg.fee_hold, last - int(hours_before * HOUR)), "feeCents": fee})
            prev = fee
        sched = dedupe(sorted(out, key=lambda x: (x["at"], x["feeCents"])))
        action = {"type": "post", "stops": stops, "audience": audience, "schedule": sched}
        self.outbox.append(action)
        self.pending_posts.append((action, "bundle3"))
        for x in seq:
            self.bundle_last[x.order["id"]] = last
        self.say("BUNDLE3", "+".join(x.order["id"] for x in seq) + f" last={last} fee0={sched[0]['feeCents']}")
        return True

    def try_bundle(self, ob: OrderBook) -> bool:
        if not self.simple(ob):
            return False
        self.pair_blocks.clear()
        if self.cfg.bundle3 and self.try_extend(ob):
            return True
        best = None
        for oid2 in list(self.chain_held):
            other = self.orders.get(oid2)
            if not other or other is ob or other.order["status"] == "cancelled" or not self.simple(other):
                continue
            if self.undelivered(oid2) != [0] or (oid2, 0) in self.leg_gig or self._pending(oid2, 0):
                continue
            for first, second in ((ob, other), (other, ob)):
                last = self.chain(first, second)
                if last is not None and (best is None or self.chain_key(last, first, second) > self.chain_key(best[0], best[1], best[2])):
                    best = (last, first, second, None)
        for rec in self.gigs.values():
            old = self.now - rec.posted_at > self.cfg.bundle_window
            if rec.status != "open" or rec.escalated or len(rec.legs) != 1 or (old and not self.cfg.repair_pairs):
                continue
            other = self.orders.get(rec.legs[0][0])
            if not other or other is ob or not self.simple(other):
                continue
            for first, second in ((ob, other), (other, ob)):
                last = self.chain(first, second)
                if last is not None and old and not self.repair_ok(first, second):
                    continue  # repair: an older single still unbooked; take it into a pair only if the pair books well
                if last is not None and (best is None or self.chain_key(last, first, second) > self.chain_key(best[0], best[1], best[2])):
                    best = (last, first, second, rec)
        if not best:
            self.pair_block_note([ob])
            return False
        self.pair_blocks.clear()
        last, first, second, rec = best
        repair = rec is not None and self.now - rec.posted_at > self.cfg.bundle_window
        if rec is not None:
            self.withdraw(rec.id)
        self.chain_held.pop(first.order["id"], None)
        self.chain_held.pop(second.order["id"], None)
        self.post_bundle(first, second, last, why="repair" if repair else "bundle")
        return True

    def repair_ok(self, first: OrderBook, second: OrderBook) -> bool:
        """A pair built from an older open single: short enough and far enough ahead to book (k18 chain log)."""
        A, B, g = first.order["legs"][0], second.order["legs"][0], self.geo
        drive = (g.drive(A["pickup"]["placeId"], A["delivery"]["placeId"]) + g.drive(A["delivery"]["placeId"], B["pickup"]["placeId"])
                 + g.drive(B["pickup"]["placeId"], B["delivery"]["placeId"]))
        start = max(self.now + self.cfg.bundle_lead, A["pickup"]["window"]["from"])
        return drive <= self.cfg.repair_drive and start - self.now >= self.cfg.repair_lead

    # ------------------------------------------------------------------ evening release
    def release_at(self, ob: OrderBook) -> Optional[int]:
        """When to post a car picked up on a later day: hold_hour on the day before its first pickup day.
        Drivers book most gigs the day before (most know only their next day), and cars held together can be
        paired: one driver, two cars, no ticket home in between. None: post now."""
        o = ob.order
        if not (self.cfg.hold_all or self.simple(ob)):
            return None
        frm = max(max(self.leg_note(o["id"], l).ready_at or 0, L["pickup"]["window"]["from"]) for l, L in enumerate(o["legs"]))
        rel = (frm // DAY - 1) * DAY + self.cfg.hold_hour * 60
        if self.cfg.hold_weekend and self.last_pickup(ob, list(range(len(o["legs"])))) // DAY == 7:
            rel = max(rel, 6 * DAY + self.cfg.hold_hour * 60)  # due on the last Monday: book it on Sunday for Monday
        if self.cfg.hold_min_left and self.last_pickup(ob, list(range(len(o["legs"])))) - rel < self.cfg.hold_min_left:
            return None  # too little time between the release and the last pickup: drivers need the evening and morning to book it
        if rel > self.now:
            return rel
        if self.cfg.batch_hours:
            # Batch dispatch: a car the evening release would post at once waits for the next batch, so it is paired against the whole
            # pool (held cars + our open singles) instead of booking alone in minutes (PAIRS_MISSED: 66% of missed pairs = partner
            # already booked; 180-266 cars/wk are posted at the win). Only while batch_min_left remains after the batch.
            last = self.last_pickup(ob, list(range(len(o["legs"]))))
            day = self.now // DAY
            for d in (day, day + 1):
                for h in sorted(self.cfg.batch_hours):
                    t = d * DAY + h * 60
                    if t > self.now + 5:
                        return t if last - t >= self.cfg.batch_min_left else None
        return None

    def release_held(self) -> None:
        """Posts the cars whose release has come: pairs first (a max greedy matching), then singles."""
        due = sorted(oid for oid, t in self.held.items() if t <= self.now)
        if not due:
            return
        for oid in due:
            del self.held[oid]
        cfg = self.cfg
        def free(o: str) -> bool:  # no live or pending gig (after a restart, a held car may already be posted)
            return o in self.orders and self.orders[o].order["status"] != "cancelled" and                 not any((o, l) in self.leg_gig or self._pending(o, l) for l in range(len(self.orders[o].order["legs"])))
        A = [self.orders[o] for o in due if free(o)]
        later = [self.orders[o] for o in sorted(self.held) if free(o)]  # still held: cars for the same day
        open_recs = {}
        if cfg.hold_open:
            for rec in self.gigs.values():
                if rec.status == "open" and not rec.escalated and len(rec.legs) == 1:
                    ob = self.orders.get(rec.legs[0][0])
                    if ob and self.simple(ob):
                        open_recs[ob.order["id"]] = rec
        cands = A + later + [self.orders[o] for o in sorted(open_recs)]
        km = cfg.bundle_km
        if cfg.hold_km:
            self.cfg = cfg.with_(bundle_km=cfg.hold_km)
        edges = []
        self.pair_blocks.clear()
        try:
            for a in A:
                if not self.simple(a):
                    continue
                for b in cands:
                    if b is a or not self.simple(b):
                        continue
                    for first, second in ((a, b), (b, a)):
                        last = self.chain(first, second)
                        if last is not None:
                            L1, L2 = first.order["legs"][0], second.order["legs"][0]
                            tr = self.geo.drive(L1["delivery"]["placeId"], L2["pickup"]["placeId"])
                            # Greedy order: shortest hop first; with pair_end the end's score first (base = -hop), hop then slack break ties.
                            key = -self.end_score(-tr, L2["delivery"]["placeId"]) if cfg.pair_end else 0.0
                            edges.append((key, tr, -last, first.order["id"], second.order["id"], last))
        finally:
            self.cfg = cfg
        used: set = set()
        for _, tr, _, f, s, last in sorted(edges):
            if f in used or s in used:
                continue
            used.update((f, s))
            for x in (f, s):
                self.held.pop(x, None)
                if x in open_recs:
                    self.withdraw(open_recs[x].id)
            self.post_bundle(self.orders[f], self.orders[s], last, why="release")
        self.pair_block_note([a for a in A if a.order["id"] not in used])
        for a in A:
            if a.order["id"] not in used:
                self.dispatch_order(a.order["id"], "release")

    def post_bundle(self, first: OrderBook, second: OrderBook, last: int, why: str = "bundle") -> None:
        stops = self.stops_for(first, 0) + self.stops_for(second, 0)
        audience = {"experienced": any(x.order["legs"][0]["car"]["premium"] for x in (first, second)), "manualLicence": False}
        cfg = self.cfg
        typical = self.base_fee(first, [0]) + self.base_fee(second, [0])
        mult = cfg.repair_mult if why == "repair" and cfg.repair_mult else cfg.bundle_mult
        if cfg.bundle_soon_lead and max(self.now + cfg.bundle_lead, first.order["legs"][0]["pickup"]["window"]["from"]) - self.now < cfg.bundle_soon_lead:
            mult = cfg.bundle_soon_mult  # starts soon: drivers' days are mostly planned, pay nearly two gigs' worth
            self.bundle_soon.update((first.order["id"], second.order["id"]))
        opening = mult * cfg.fee_open
        if why == "pair2" and cfg.v5_pair2_fee:
            opening = cfg.v5_pair2_fee  # second-attempt pair at a fixed share of the two typical fees (Franco: 0.92-0.96 vs ~1.03 alone)
        if cfg.bundle_open_dense and last - self.now >= cfg.bundle_open_dense[0] * HOUR and                 self.home_near_delivery(second.order["legs"][0]["delivery"]["placeId"]) >= cfg.bundle_open_dense[1]:
            opening = min(opening, cfg.bundle_open_dense[2])  # the chain ends where many drivers live: their ride home is free
        out = [{"at": self.now, "feeCents": int(round(typical * opening))}]
        if cfg.bundle_climb and why != "repair" and last - self.now >= cfg.bundle_climb_slack * HOUR:
            # Open low, climb to the usual opening: the first drivers who look take it cheaper, the rest see the usual fee soon.
            climb = [{"at": self.now + m, "feeCents": int(round(typical * min(share, opening)))} for m, share in cfg.bundle_climb]
            end = cfg.bundle_climb[-1][0] + (cfg.bundle_climb[-1][0] - cfg.bundle_climb[-2][0] if len(cfg.bundle_climb) > 1 else 25)
            out = climb + [{"at": self.now + end, "feeCents": out[0]["feeCents"]}]
        prev = out[-1]["feeCents"]
        # Raises: fee_rel scaled by the bundle discount, or bundle_rel as shares of the two typical fees.
        steps = list(cfg.bundle_rel) if cfg.bundle_rel else [(h, m * mult) for h, m in cfg.fee_rel]
        for hours_before, share in steps:
            fee = max(prev, int(round(typical * share)))
            out.append({"at": max(self.now + cfg.fee_hold, last - int(hours_before * HOUR)), "feeCents": fee})
            prev = fee
        sched = dedupe(sorted(out, key=lambda x: (x["at"], x["feeCents"])))
        action = {"type": "post", "stops": stops, "audience": audience, "schedule": sched}
        self.outbox.append(action)
        self.pending_posts.append((action, "repair" if why == "repair" else "bundle"))
        self.bundle_last[first.order["id"]] = last
        self.bundle_last[second.order["id"]] = last
        for x in (first, second):
            if x.first_post_at is None:
                x.first_post_at = self.now
        self.say("BUNDLE", first.order["id"] + "+" + second.order["id"] + f" {why} last={last} fee0={sched[0]['feeCents']}")

    def chain_drive(self, rec: GigRec) -> int:
        """Road minutes along a gig's stops."""
        total, prev = 0, None
        for st in rec.stops:
            here = self.stop_place(st)
            if here is None:
                continue
            if prev is not None:
                total += self.geo.drive(prev, here)
            prev = here
        return total

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
        if self.cfg.stop_windows and len(o["legs"]) == 1 and not self.is_late(ob, [leg]):
            to = min(to, self.last_pickup(ob, [leg]))  # a pickup after this cannot be on time: let no driver plan it
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
        if self.cfg.stop_windows and not self.is_late(ob, [leg]) and dto - self.cfg.stop_margin > max(self.now, dw["from"]) + 60:
            dto -= self.cfg.stop_margin  # drivers plan to arrive inside the window: keep an hour in hand
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
        if cfg.fee1:
            try:
                q = ob.order["legs"][legs[-1]]["delivery"]["placeId"]
                pick = self.fee1.choose(ob, legs, last, base, bool(cfg.desert_n and self.desert(q)))
            except Exception as exc:  # the model must never stop a post: fall back to the ladder
                self.say("ERR", f"fee1 {type(exc).__name__}: {exc}")
                pick = None
            if pick:
                m, why = pick
                oid = ob.order["id"]
                self.say("FEE1", f"{oid} {why}")
                return [{"at": now, "feeCents": max(1, int(round(base * m)))}]
        if cfg.fee_mode == "relative":
            # Steps anchored to lastPickupAt: hold the opening fee while there is time, raise as the pickup nears.
            # The opening fee always shows for at least fee_hold minutes: most views come in the first minutes.
            opening = cfg.fee_open_hot if ob.p_exp >= cfg.hot_p else cfg.fee_open
            if cfg.fee_open_dense and self.ontime.supply(ob.order["legs"][legs[0]]["pickup"]["placeId"], 30.0) >= cfg.dense_n:
                opening = cfg.fee_open_dense  # many drivers live near the pickup: it books in minutes at less
            if (cfg.fee_open_rule or cfg.fee_open_day) and not ob.p_exp >= cfg.hot_p:
                opening = self.open_rule(ob, legs, last, opening)
            if (cfg.v5_short_open and cfg.fee1 and not getattr(self, "scarce", False) and last - now < V5_SHORT_H * HOUR
                    and not ob.p_exp >= cfg.hot_p and not (cfg.desert_n and self.desert(ob.order["legs"][legs[-1]]["delivery"]["placeId"]))):
                opening = min(opening, cfg.v5_short_open)  # short lead, fee1 could not choose: open lower (never above a cheaper rule), the fee_rel raises stay
                self.say("V5_SHORT", f"{ob.order['id']} left={last - now} open={opening:.2f}")
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

    def home_near_delivery(self, place: str, minutes: int = 30) -> int:
        """Drivers whose trip home from this delivery takes at most `minutes` of road (fixed per world: cached)."""
        key = (place, minutes)
        if key not in self._near_q:
            self._near_q[key] = sum(c for h, c in sorted(self.home_count.items()) if self.geo.drive(place, h) <= minutes)
        return self._near_q[key]

    def desert(self, place: str) -> bool:
        """A delivery town the shortage emptied: fewer than desert_n drivers live within 60 road minutes (dev-46: 21% of won cars,
        twice as late in every policy; research/re/drivers/DEV46.md)."""
        return bool(place) and self.home_near_delivery(place, 60) < self.cfg.desert_n

    def open_rule(self, ob: OrderBook, legs: list[int], last: int, default: float) -> float:
        """Opening fee by time to the last pickup and drivers living near the delivery (cheap to move: they need no trip home)."""
        left = (last - self.now) / HOUR
        q = ob.order["legs"][legs[-1]]["delivery"]["placeId"]
        if self.cfg.desert_n and self.desert(q):
            return default  # no cut where nobody lives near the delivery
        if self.cfg.fee_cut_guard and not self.cut_ok(ob):
            return default
        nd = self.home_near_delivery(q)
        day_mult = self.day_open(left, nd)
        if day_mult:
            return day_mult
        for hours, n, mult in self.cfg.fee_open_rule:
            if left >= hours and nd >= n:
                return mult
        return default

    def cut_ok(self, ob: OrderBook) -> bool:
        """fee_cut_guard (p_ok_min, proj_min, bo_max): cut an opening only for a safe car in a week that is going well. Every deep
        cut failed H1 on one scarce week (k-safe-f2: dev-65 0.896); board W3 15:00 had booked/opening 1.27 vs 1.05-1.07."""
        p_ok_min, proj_min, bo_max = self.cfg.fee_cut_guard
        if ob.p_ok < p_ok_min:
            return False
        if self.won_count >= 30 and self.gov.projection() < proj_min:
            return False
        xs = self.bo_ratios[-60:]
        return not (len(xs) >= 30 and sum(xs) / len(xs) > bo_max)

    def day_open(self, left: float, nd: int) -> float:
        """fee_open_day: the opening for today's posting day, drivers near the delivery and hours to the last pickup; 0 = none."""
        day = self.now // DAY
        for d0, d1, n, hours, mult in self.cfg.fee_open_day:
            if d0 <= day <= d1 and nd >= n and left >= hours:
                return mult
        return 0.0

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

    def strict(self) -> bool:
        """A hard week: many of our cars needed a deadline warning. The governor then takes y4's strict settings."""
        c = self.cfg
        if self._strict_cfg is None and not (c.strict_warn and self.won_count >= c.strict_after and len(self.warned) >= c.strict_warn * self.won_count):
            return False
        return True  # once strict, strict for the rest of the week

    def gov_cfg(self) -> Config:
        """The config the governor uses now: the normal one, or the strict one in a hard week."""
        if not self.strict():
            return self.cfg
        if self._strict_cfg is None:
            c, (t, r, rel, th) = self.cfg, self.cfg.strict_gov
            self._strict_cfg = c.with_(gov_tight=max(c.gov_tight, t), gov_rescue=max(c.gov_rescue, r), gov_relaxed=max(c.gov_relaxed, rel),
                                       theta=max(c.theta, th), steep_relaxed=(1.4, 1.6, 1.8))
            self.say("STRICT", f"warned {len(self.warned)} of {self.won_count} orders: strict governor from now on")
        return self._strict_cfg

    def steep_plan_now(self, ob: Optional[OrderBook] = None) -> tuple:
        """How much to pay to save a car: little while the on-time budget is comfortable, a lot near the gate,
        and more for a dealer whose trust a late car would halve."""
        cfg = self.gov_cfg()
        if not cfg.gov_steep:
            return cfg.steep_plan
        proj = self.gov.projection(stuck=cfg.gov_stuck_steep)
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
            last = min(self.bundle_last.get(o, 0) for o, _ in rec.legs)
            if self.cfg.bundle_keep_drop and why == "dropped" and last - self.now >= self.cfg.unbundle_minutes:
                return
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
        if self.fee1_gig(rec):
            self.fee1.close(rec, False, self.now)
        plan = self.steep_plan_now(ob)
        if self.cfg.rescue_cap and len({o for o, _ in legs}) == 1:
            # Governor-capped rescue (Franco's idea B): with the week comfortably on time, a car whose margin would be small at
            # rescue fees gets a capped plan, not the steep climb (rescued singles paid 1.39x and were still 55% late, ~19/wk).
            proj_min, margin_max, cap_plan = self.cfg.rescue_cap[:3]
            ref = self.cfg.rescue_cap[3] if len(self.cfg.rescue_cap) > 3 else plan[-1]  # the fee the margin is judged at
            price = ob.order.get("priceCents") or 0
            if self.gov.projection() >= proj_min and price - ref * base < margin_max:
                plan = tuple(max(m, cur / max(1.0, base)) for m in cap_plan)
                self.say("RESCUE_CAP", f"{rec.id} {oid} {why} price={price} base={int(base)} plan={plan}")
        sched = steep(self.now, base, self.cfg, floor=cur, plan=plan)
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

    # ------------------------------------------------------------------ backhaul offers
    def stop_place(self, s: dict) -> Optional[str]:
        ob = self.orders.get(s["orderId"])
        if not ob:
            return None
        return ob.order["legs"][s["leg"]]["pickup" if s["kind"] == "pickup" else "delivery"]["placeId"]

    def gig_end(self, rec: GigRec, oid: str, leg: int, place: str, at: int) -> Optional[tuple[str, int]]:
        """Where and about when the driver finishes this gig, seen from the pickup that just happened."""
        idx = next((i for i, s in enumerate(rec.stops) if s["orderId"] == oid and s["leg"] == leg and s["kind"] == "pickup"), None)
        if idx is None:
            return None
        t, here = at, place
        for s in rec.stops[idx + 1:]:
            p = self.stop_place(s)
            if p is None:
                return None
            t += 0 if p == here else self.geo.drive(here, p)
            here = p
        return here, t

    def backhaul(self, driver: str, rec: GigRec, place: str, at: int) -> None:
        """One of our drivers will be free at `place` near minute `at`. A second car near there costs them only the
        extra time and tickets, and the app does not notify them where our gigs took them: offer the nearest open car."""
        cfg = self.cfg
        hour = (self.now % DAY) // 60
        if hour >= 22 or hour < 7 or at % DAY > cfg.backhaul_free_by or at // DAY != self.now // DAY:
            return
        if self.offers_today[(driver, self.now // DAY)] >= 3:
            return
        d = self.roster.get(driver)
        if not d:
            return
        best = None
        for g in sorted(self.gigs.values(), key=lambda g: g.id):
            if g.status != "open" or g.id == rec.id or len(g.stops) != 2 or (g.id, driver) in self.offered:
                continue
            if self.open_offers[g.id] >= 3:
                continue
            if g.audience.get("manualLicence") and d["licence"] != "manual":
                continue
            if g.audience.get("experienced") and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                continue
            oid, l0 = g.legs[0]
            ob = self.orders.get(oid)
            if not ob or ob.order["status"] == "cancelled":
                continue
            leg = ob.order["legs"][l0]
            if leg["pickup"]["privateAddress"]:
                continue
            p2 = leg["pickup"]["placeId"]
            tr = 0 if p2 == place else self.geo.drive(place, p2)
            if tr > cfg.backhaul_road:
                continue
            ready = at + tr
            ivs = open_intervals(leg["pickup"].get("hours"), max(ready, leg["pickup"]["window"]["from"]), ready + cfg.backhaul_wait)
            ivs = [(a, b) for a, b in ivs if b - a >= 15]
            if not ivs:
                continue
            arrive = ivs[0][0]
            if arrive > leg["pickup"]["window"]["to"] or arrive > self.last_pickup(ob, [l0]) - 30:
                continue
            dB = self.geo.drive(p2, leg["delivery"]["placeId"])
            if arrive // DAY != at // DAY or arrive % DAY + dB > cfg.backhaul_home_by:
                continue
            if best is None or tr < best[0]:
                best = (tr, g, ob, l0)
        if not best:
            return
        tr, g, ob, l0 = best
        base = self.base_fee(ob, [l0])
        fee = int(round(base * cfg.backhaul_mult))
        if not cfg.backhaul_below:
            fee = max(fee, current_fee(g.schedule, self.now))
        self.outbox.append({"type": "offer", "gigId": g.id, "driverId": driver, "feeCents": fee})
        self.offers_today[(driver, self.now // DAY)] += 1
        self.open_offers[g.id] += 1
        self.offered.add((g.id, driver))
        self.say("BOFFER", f"{g.id} {driver} {fee} x{fee / max(1.0, base):.2f} tr={tr} from={rec.id}")

    def repost_past_last(self) -> None:
        """An open gig whose order's last pickup has passed keeps the order's windows it was posted with, so no driver can
        book it until it expires (RULES: a driver must reach every stop inside its window; w-c3g: 13.9 gig_expired/week).
        Posted again now, its stops run to the end of the world: a driver books it at once and the car is less late
        (refund 10% within 2 h vs 25% after; research/re/external/RIVAL_FEES.md #5)."""
        for gid in sorted(self.gigs):
            rec = self.gigs[gid]
            if rec.status != "open":
                continue
            oids = sorted({o for o, _ in rec.legs})
            if len(oids) != 1 or oids[0] not in self.orders:
                continue
            ob = self.orders[oids[0]]
            legs = sorted(l for _, l in rec.legs)
            last = self.last_pickup(ob, legs)
            if rec.posted_at < last <= self.now - self.cfg.repost_past_last:
                self.say("REPOST_PASTLAST", f"{gid} {oids[0]} last pickup {last}, now {self.now}")
                self.withdraw(gid)
                self.post(ob, legs, "past-last")

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
                    self.gig_open.setdefault(rec.id, a["schedule"][0]["feeCents"])
                    rec.repair = why == "repair"
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
                    if self.cfg.fee1 and self._fee1 is not None and rec.status == "withdrawn":
                        self._fee1.booked_after_all(rec.id)  # a re-pick's withdraw lost to a booking: the week's offset counts it booked
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
                self.gig_open.setdefault(rec.id, g["schedule"][0]["feeCents"])
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
        if self.cfg.repost_past_last:
            self.repost_past_last()
        if self.held:
            self.release_held()  # before the loop below, which would post released cars one by one
        for oid in list(self.orders):
            ob = self.orders[oid]
            if ob.order["status"] == "cancelled":
                continue
            self.dispatch_order(oid, "tick")
        if self.cfg.bundle:
            for rec in list(self.gigs.values()):
                if rec.status == "open" and len({o for o, _ in rec.legs}) > 1:
                    last = min(self.bundle_last.get(o, 0) for o, _ in rec.legs)
                    soon = all(o in self.bundle_soon for o, _ in rec.legs)
                    if last - self.now < (self.cfg.bundle_soon_slack if soon else self.cfg.unbundle_minutes):
                        self.unbundle(rec, "timeout")
                    elif self.cfg.repair_split and rec.repair and self.now - rec.posted_at >= self.cfg.repair_split:
                        self.unbundle(rec, "repair-split")  # the pair did not catch a driver fast: the cars go back alone
                    elif self.cfg.long_split and self.now - rec.posted_at >= self.cfg.long_split[1] and                             self.chain_drive(rec) >= self.cfg.long_split[0]:
                        # A long pair unbooked this long rarely books (32%): withdraw it; the next tick posts the cars alone
                        # (posting in the same flush as the withdraw would race a restart's rejoin).
                        self.say("UNBUNDLE", f"{rec.id} long-split")
                        self.withdraw(rec.id)
        if self.cfg.relook_minutes:
            self.relook()
        if self.cfg.fee1 and self.cfg.fee1_repick:
            try:
                self.fee1_repick()
            except Exception as exc:  # never skip the alarm escalation below
                self.say("ERR", f"fee1_repick {type(exc).__name__}: {exc}")
        if self.cfg.offer_home_n:
            self.offer_home()
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
                if len({o for o, _ in rec.legs}) > 1 and all(o in self.bundle_soon for o, _ in rec.legs):
                    continue  # a short-notice chain splits by its own clock (tick above)
                alarm = self.cfg.alarm_minutes
                if self.cfg.desert_n and ob and len({o for o, _ in rec.legs}) == 1 and self.desert(self.stop_place(rec.stops[-1]) or ""):
                    alarm = max(alarm, self.cfg.desert_alarm)  # few drivers live near this delivery: escalate while there is time
                if ob and self.last_pickup(ob, [l for _, l in rec.legs]) - self.now < alarm:
                    ob.urgent = True
                    self.escalate_gig(rec, "alarm")
        if self.cfg.viewer_offers:
            self.offer_viewers()
        if self.now // (2 * HOUR) != self.gov_logged:
            # Every 2 world hours: the governor's view, to check its projection against the end of the week.
            self.gov_logged = self.now // (2 * HOUR)
            self.say("GOV", f"proj={self.gov.projection():.3f} cal={self.gov.calibration():.3f} won={self.won_count} "
                            f"ontime={len(self.ontime_orders)} late={len(self.late_orders)} bar={self.gov.bar():.2f}")
            if self.cfg.backlog_brake:
                x = self.brake_excess()
                self.say("BRAKE", f"U={self._brake_u} soft={max(self.cfg.backlog_brake[1], self.cfg.backlog_brake[0] * len(self.roster)):.0f} "
                                  f"excess={x:.2f} cap={self.capacity_factor():.3f}")

    def relook(self) -> None:
        """Second look: a single gig nobody booked for relook_minutes is short of its clearing fee. Raise it once, now,
        while drivers still plan that day, instead of waiting for the fee_rel steps hours later (Halal: one re-pick after 6 h)."""
        cfg = self.cfg
        for gid in sorted(self.gigs):
            rec = self.gigs[gid]
            if rec.status != "open" or rec.escalated or rec.relooked or len({o for o, _ in rec.legs}) != 1:
                continue
            if self.fee1_gig(rec):
                continue  # one fee: a re-pick is a new post (fee1_repick), not a raise nobody is notified of
            if self.now - rec.posted_at < cfg.relook_minutes:
                continue
            ob = self.orders.get(rec.legs[0][0])
            legs = [l for _, l in rec.legs]
            rec.relooked = True
            if not ob or self.last_pickup(ob, legs) - self.now <= cfg.relook_min_left:
                continue
            base = self.base_fee(ob, legs)
            fee = int(round(base * cfg.relook_mult))
            cur = current_fee(rec.schedule, self.now)
            if fee <= cur:
                continue
            later = [x for x in rec.schedule if x["at"] > self.now and x["feeCents"] > fee]
            rec.schedule = dedupe([{"at": self.now, "feeCents": fee}] + later)
            self.outbox.append({"type": "reprice", "gigId": rec.id, "schedule": rec.schedule})
            self.say("RELOOK", f"{rec.id} {ob.order['id']} sat {self.now - rec.posted_at} min {cur}->{fee}")

    def fee1_repick(self) -> None:
        """A fee1 gig unbooked for fee1_repick minutes: withdraw it; the next tick posts the car again at a new choice. A new post
        notifies drivers again (~10 views in 30 min); a raise reaches ~1 (research/mechanics/MECHANICS.md). Posting in the next tick,
        not in this flush, keeps a withdraw that loses to a booking from posting the car twice."""
        from .fee1 import repick_at
        cfg = self.cfg
        for gid in sorted(self.gigs):
            rec = self.gigs[gid]
            if rec.status != "open" or not self.fee1_gig(rec):
                continue
            oid = rec.legs[0][0]
            ob = self.orders.get(oid)
            if not ob or ob.urgent:
                continue
            legs = [l for _, l in rec.legs]
            q = ob.order["legs"][legs[-1]]["delivery"]["placeId"]
            alarm = max(cfg.alarm_minutes, cfg.desert_alarm) if (cfg.desert_n and self.desert(q)) else cfg.alarm_minutes
            left = self.last_pickup(ob, legs) - alarm - self.now  # minutes to our alarm
            posts = self.fee1.posts(oid, legs)
            # Last call: a car still unbooked fee1_last_call min before the alarm gets one more new post at a safe fee (the ladder's
            # raise 8 h before the last pickup, as a post that notifies drivers): without it a miss rode to the alarm (f1v4: cars booked
            # on their only post were late 1.4% vs 0.6%).
            last_call = (cfg.fee1_last_call and cfg.fee1_min_minutes <= left <= cfg.fee1_last_call
                         and self.now - rec.posted_at >= 60 and posts <= cfg.fee1_max_posts)
            if not last_call:
                # v5_repost: one re-pick at a flat fee, then the car keeps it to the last call (no second model re-pick)
                max_posts = min(cfg.fee1_max_posts, 2) if cfg.v5_repost and not getattr(self, "scarce", False) else cfg.fee1_max_posts
                if self.now < repick_at(rec.posted_at, cfg.fee1_repick) or (posts >= max_posts and not cfg.fee1_after_ladder):
                    continue  # (a re-pick that would fall at night waits for the morning: nobody plans a trip then)
                if left < cfg.fee1_min_minutes + (cfg.fee1_last_call or 0) and not cfg.fee1_after_ladder:
                    continue  # too close to the alarm for another choice: the last call (or the alarm) takes it
            if not last_call and cfg.v5_pair2 and not getattr(self, "scarce", False) and self.v5_pair2(rec):
                continue  # paired with another sitting single of ours: one driver, two cars, at the pair's fee
            self.fee1.close(rec, False, self.now)
            if cfg.fee1_after_ladder and not last_call:
                # The miss rejoins the old ladder in place (fee_open now, then the fee_rel steps): ARCHIVE's split of k-f1h5f, a re-posted
                # car cost EUR 3.6-6.0 more than under the ladder (-103..-220/wk) while fee1's first picks gained +540/wk every week.
                cur = current_fee(rec.schedule, self.now)
                rec.schedule = self.ladder_from_now(ob, legs, cur)
                self.outbox.append({"type": "reprice", "gigId": gid, "schedule": rec.schedule})
                self.say("FEE1_LADDER", f"{gid} {oid} sat {self.now - rec.posted_at} min at {cur} -> {rec.schedule[0]['feeCents']}..{rec.schedule[-1]['feeCents']}")
                continue
            self.say("FEE1_REPICK", f"{gid} {oid} sat {self.now - rec.posted_at} min at {rec.schedule[0]['feeCents']}{' last-call' if last_call else ''}")
            self.withdraw(gid)

    def v5_pair2(self, rec: GigRec) -> bool:
        """v5_pair2: at its re-pick, pair a sitting single with another open unbooked single of ours that one driver can take
        before or after it (chain()'s fit checks); withdraw both and post the pair at bundle_mult (pairs pay 0.84x vs 1.03x for
        a re-post alone). Stateless: the pair is a two-order gig, rebuilt after a restart like any other (run.settle)."""
        ob = self.orders.get(rec.legs[0][0])
        if not ob or len(rec.legs) != 1 or not self.simple(ob):
            return False
        if self.cfg.v5_pair2_hub and self.last_pickup(ob, [l for _, l in rec.legs]) - self.now < 6 * HOUR:
            return False  # Franco's second attempt: only a miss with >= 6 h left (time for the fresh post's view burst)
        best = None
        self.pair_blocks.clear()
        for gid in sorted(self.gigs):
            r2 = self.gigs[gid]
            if gid == rec.id or r2.status != "open" or r2.escalated or len(r2.legs) != 1:
                continue
            other = self.orders.get(r2.legs[0][0])
            if not other or other is ob or not self.simple(other):
                continue
            if other.urgent or self.last_pickup(other, [l for _, l in r2.legs]) - self.now < V5_PAIR2_SLACK:
                continue  # MARKET review: a partner near its last pickup would restart its booking clock in a new post
            for first, second in ((ob, other), (other, ob)):
                last = self.chain(first, second)
                if last is not None and self.cfg.v5_pair2_hub and                         self.home_near_delivery(second.order["legs"][0]["delivery"]["placeId"], PAIR_END_RADIUS) < self.cfg.v5_pair2_hub:
                    continue  # the chain must end at a driver-dense hub: drivers living there take it home (pairs book by their end)
                if last is not None and (best is None or self.chain_key(last, first, second) > self.chain_key(best[0], best[1], best[2])):
                    best = (last, first, second, r2)
        if self.cfg.v5_pair2_held:
            # Also a held car (won, waiting for its release, unposted) as the partner: a far larger pool than the few sitting singles
            # (v5La-P2 with sitting partners only: 1.6 pairs/wk of ~70 re-picks).
            for oid2 in sorted(self.held):
                other = self.orders.get(oid2)
                if not other or other is ob or not self.simple(other) or other.order["status"] == "cancelled":
                    continue
                if any((oid2, l) in self.leg_gig or self._pending(oid2, l) for l in range(len(other.order["legs"]))):
                    continue
                if self.last_pickup(other, [0]) - self.now < V5_PAIR2_SLACK:
                    continue
                for first, second in ((ob, other), (other, ob)):
                    last = self.chain(first, second)
                    if last is not None and self.cfg.v5_pair2_hub and                             self.home_near_delivery(second.order["legs"][0]["delivery"]["placeId"], PAIR_END_RADIUS) < self.cfg.v5_pair2_hub:
                        continue
                    if last is not None and (best is None or self.chain_key(last, first, second) > self.chain_key(best[0], best[1], best[2])):
                        best = (last, first, second, None)
        if best is None:
            self.pair_block_note([ob])
            return False
        self.pair_blocks.clear()
        last, first, second, r2 = best
        if r2 is None:  # the partner is a held car: take it out of the hold, nothing to withdraw
            for x in (first, second):
                self.held.pop(x.order["id"], None)
            self.say("V5_PAIR2", f"{rec.id}+held {first.order['id']}+{second.order['id']} last={last} sat {self.now - rec.posted_at} min")
            if self.fee1_gig(rec):
                self.fee1.close(rec, False, self.now)
            self.withdraw(rec.id)
            self.post_bundle(first, second, last, why="pair2")
            return True
        self.say("V5_PAIR2", f"{rec.id}+{r2.id} {first.order['id']}+{second.order['id']} last={last} sat {self.now - rec.posted_at}"
                             f"+{self.now - r2.posted_at} min")
        for r in (rec, r2):
            if self.fee1_gig(r):
                self.fee1.close(r, False, self.now)  # both sat unbooked until now: the week's offset keeps the evidence
            self.withdraw(r.id)
        self.post_bundle(first, second, last, why="pair2")
        return True
    def ladder_from_now(self, ob: OrderBook, legs: list[int], cur: int) -> list[dict]:
        """The relative ladder from now for a sitting gig: fee_open (never under its current fee), then the fee_rel steps before the
        last pickup. Two or more steps, so the gig is no longer a fee1 gig."""
        cfg, now = self.cfg, self.now
        base = self.base_fee(ob, legs)
        last = self.last_pickup(ob, legs)
        prev = max(cur, int(round(base * cfg.fee_open)))
        out = [{"at": now, "feeCents": prev}]
        for hours_before, mult in cfg.fee_rel:
            fee = max(prev, int(round(base * mult)))
            out.append({"at": max(now + cfg.fee_hold, last - int(hours_before * HOUR)), "feeCents": fee})
            prev = fee
        out = dedupe(sorted(out, key=lambda x: (x["at"], x["feeCents"])))
        if len(out) < 2:  # keep it out of fee1's hands: one more step at the steep plan's first rung before the alarm
            out.append({"at": max(now + cfg.fee_hold, last - cfg.alarm_minutes), "feeCents": max(prev + 1, int(round(base * cfg.steep_plan[0])))})
        return dedupe(out)

    def offer_home(self) -> None:
        """Direct offers to drivers who live near a gig's delivery but too far from its pickup to be notified: the trip home
        is the dear part of a driver's cost, so they book 26% of the gigs they see, yet see 1% (20 c3g weeks, reach.py)."""
        cfg = self.cfg
        hour = (self.now % DAY) // 60
        if hour >= 22 or hour < 7:
            return
        for rec in list(self.gigs.values()):
            if rec.status != "open" or rec.escalated or len(rec.legs) != 1 or rec.id in self.home_offered:
                continue
            if self.now - rec.posted_at < cfg.offer_home_after:
                continue
            ob = self.orders.get(rec.legs[0][0])
            if not ob:
                continue
            legs = [l for _, l in rec.legs]
            if (cfg.late_plan and self.is_late(ob, legs)) or self.last_pickup(ob, legs) - self.now < cfg.offer_home_slack:
                continue
            self.home_offered.add(rec.id)
            L = ob.order["legs"][legs[0]]
            p, q = L["pickup"]["placeId"], L["delivery"]["placeId"]
            day = self.now // DAY
            cands = []
            for did in sorted(self.roster):
                d = self.roster[did]
                if (rec.id, did) in self.offered or self.offers_today[(did, day)] >= 3:
                    continue
                if rec.audience.get("manualLicence") and d["licence"] != "manual":
                    continue
                if rec.audience.get("experienced") and not (d["rating"] >= 4.8 and d["completedGigs"] >= 50):
                    continue
                h = d["homePlaceId"]
                if self.geo.drive(q, h) > cfg.offer_home_min or self.geo.air(h, p) <= 30:
                    continue
                cands.append((self.offers_today[(did, day)], -d["completedGigs"], did))
            cands.sort()
            fee = current_fee(rec.schedule, self.now)
            for _, _, did in cands[: max(0, cfg.offer_home_n - self.open_offers[rec.id])]:
                self.outbox.append({"type": "offer", "gigId": rec.id, "driverId": did, "feeCents": int(fee)})
                self.offers_today[(did, day)] += 1
                self.open_offers[rec.id] += 1
                self.offered.add((rec.id, did))
                self.say("HOMEOFFER", f"{rec.id} {did} {fee}")

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
