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
        self.positions: dict[str, tuple[str, int]] = {}  # driver -> (place, minute), from our gigs
        self.viewers: dict[str, int] = {}  # driver -> last minute seen in the app
        self.roster = {d["id"]: d for d in roster}
        self.home_count: dict[str, int] = defaultdict(int)
        for d in roster:
            self.home_count[d["homePlaceId"]] += 1
        self.won_count = 0
        self.late_orders: set[str] = set()
        self.ontime_orders: set[str] = set()
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
            self.market.observe(at, r["dealerId"], min(ratios) / self.trust_factor(r["dealerId"]), won)

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
            ob = self.orders.get(rec.legs[0][0])
            if ob:
                self.book_ratios.append(e["feeCents"] / max(1.0, self.base_fee(ob, [l for _, l in rec.legs])))
            self.say("BOOKED", f"{rec.id} {e['driverId']} {e['feeCents']}")

    def on_offer_answered(self, e: dict) -> None:
        self.open_offers[e["gigId"]] = max(0, self.open_offers[e["gigId"]] - 1)
        self.say("OFFER_ANS", f"{e['gigId']} {e['driverId']} {e['answer']}")

    def on_gig_dropped(self, e: dict) -> None:
        self._reopen(e["gigId"], "dropped")

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
        cost = r["referenceFeeCents"] * self.cost_mult()
        prices: dict = {}
        meta: dict = {}
        info = []
        for opt in r["options"]:
            kind = opt["kind"]
            if kind not in cfg.quote_options:
                continue
            p_ok, slack = self.ontime.p_ok(r, opt["deadline"], kind)
            if p_ok < bar or slack < cfg.min_slack_h:
                info.append(f"{kind}:skip(p={p_ok:.2f},s={slack:.1f})")
                continue
            risk_frac = (1 - p_ok) * cfg.late_cost_frac
            ratio, ev = self.market.best_ratio(dealer, day, opt["listPriceCents"], tf, cost, risk_frac, cfg.shadow_cents)
            if ratio <= 0 or ev < cfg.min_ev_cents:
                info.append(f"{kind}:noev")
                continue
            prices[kind] = int(round(opt["listPriceCents"] * ratio * tf))
            meta[kind] = p_ok
            info.append(f"{kind}:r={ratio:.2f},p={p_ok:.2f},ev={ev/100:.0f}")
        self.quote_meta[r["id"]] = meta
        head = f"bar={bar:.2f} tf={tf:.2f} mu={self.market.mu_for(dealer, day):.3f} cost={cost/100:.0f}"
        if not prices:
            return decline_prices(r), f"DECLINE {head} {' '.join(info)}"
        return prices, f"{head} {' '.join(info)}"

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
        groups = [legs]
        if len(legs) == 2 and self.trade_minutes(ob.order) > 12 * HOUR - 10:
            groups = [[l] for l in legs]
        for g in groups:
            self.post(ob, g, why)

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
        last = ob.order["lastPickupAt"]
        if ob.urgent or last - now < 2 * HOUR:
            return steep(now, base, cfg)
        # Open low, then a few raises spread over the slack, all before the deadline warning (3 h before lastPickupAt).
        span = max(30, last - 3 * HOUR - now)
        out, prev = [], 0
        for frac, mult in cfg.fee_plan:
            fee = max(prev, int(round(base * mult)))
            out.append({"at": now + int(span * frac), "feeCents": fee})
            prev = fee
        return dedupe(out)

    def escalate_gig(self, rec: GigRec, why: str) -> None:
        if rec.status != "open":
            return
        legs = rec.legs
        oid = legs[0][0]
        ob = self.orders.get(oid)
        if not ob:
            return
        base = self.base_fee(ob, [l for _, l in legs])
        cur = current_fee(rec.schedule, self.now)
        sched = steep(self.now, base, self.cfg, floor=cur)
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
                else:
                    refused_posts.append((a, res.get("reason", "")))
            elif not res.get("ok"):
                self.say("REFUSED", f"{a['type']} {a.get('gigId', a.get('requestId', ''))} {res.get('reason', '')[:120]}")
        for a, reason in refused_posts:
            self.say("POST_REFUSED", f"{a['stops'][0]['orderId']} {reason[:160]}")
            self.repair_post(a, reason)

    def repair_post(self, a: dict, reason: str) -> None:
        """A refused post: split multi-car gigs, or drop own windows, and try again next step."""
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
        """Called once per step: posts anything missing."""
        for oid in list(self.orders):
            ob = self.orders[oid]
            if ob.order["status"] == "cancelled":
                continue
            self.dispatch_order(oid, "tick")


def steep(now: int, base: float, cfg: Config, floor: int = 0) -> list[dict]:
    out, prev = [], floor
    for i, m in enumerate(cfg.steep_plan):
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
