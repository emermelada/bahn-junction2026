"""The one State object. It holds only facts, built by folding events and the results of our own actions,
in the order they happened. A restart is a replay: the same log gives the same state.

Decisions live in dealer/ and driver/. Each side keeps its own trackers in `ext`, fed by its own
observe(event, state)."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable, Iterable, Optional

from spread.types import Action, ActionResult, DeskEvent, Gig, Order, PriceRequest, WorldMap

LIVE = ("open", "booked", "working")
Leg = tuple[str, int]  # (order id, leg index)


class State:
    def __init__(self, world_id: str, level: int, now: int, ends_at: int, world_map: WorldMap,
                 log: Optional[Callable[..., None]] = None):
        self.world_id, self.level, self.now, self.ends_at = world_id, level, now, ends_at
        self.places = {p["id"]: p for p in world_map["places"]}
        self.roads = {(r["from"], r["to"]): (r["km"], r["minutes"]) for r in world_map["roads"]}
        self.log = log or (lambda *a, **k: None)
        self.seq = -1
        self.requests: dict[str, PriceRequest] = {}
        self.orders: dict[str, Order] = {}  # won orders, cancelled included (status says so)
        self.gigs: dict[str, Gig] = {}  # our gigs; adds "scheduledAt", the minute the schedule was set
        self.gig_of: dict[Leg, str] = {}  # each leg on a live gig
        self.failures: dict[Leg, list[str]] = {}  # visit_failed reasons, oldest first
        self.expired: set[Leg] = set()  # legs whose last gig expired; cleared by the next post
        self.refused: dict[Leg, tuple[int, str]] = {}  # last refused post: minute, reason
        self.released: dict[Leg, int] = {}  # release events: the car can be collected from then
        self.picked: dict[Leg, int] = {}
        self.urgent: dict[str, int] = {}  # order id -> minute of its latest deadline_close
        self.changed: dict[str, int] = {}  # order id -> minute of its latest order_changed
        self.late: dict[str, int] = {}  # gig id -> pickupAt from driver_late
        self.forecasts: list[DeskEvent] = []
        self.margin_cents = 0
        self.money: dict[str, list[tuple[str, int]]] = {}  # order id -> ledger lines (kind, cents)
        self.ext: dict[str, Any] = {}

    # --- the map ---------------------------------------------------------------------------------------
    def minutes(self, a: str, b: str) -> int:
        return self.roads[(a, b)][1]

    def km(self, a: str, b: str) -> float:
        return self.roads[(a, b)][0]

    # --- folding ---------------------------------------------------------------------------------------
    def apply(self, e: DeskEvent) -> bool:
        """Folds one event. False for a repeat (a server restart can send events again)."""
        if e["seq"] <= self.seq:
            return False
        self.seq = e["seq"]
        kind = e["kind"]
        if kind == "price_request":
            self.requests[e["request"]["id"]] = e["request"]
        elif kind == "order_won":
            self.orders[e["order"]["id"]] = copy.deepcopy(e["order"])
        elif kind == "order_changed":
            self.orders[e["order"]["id"]] = copy.deepcopy(e["order"])
            self.changed[e["order"]["id"]] = e["at"]
        elif kind == "order_cancelled":
            if e["orderId"] in self.orders:
                self.orders[e["orderId"]]["status"] = "cancelled"
            for g in e["gigs"]:
                gig = self.gigs.get(g["gigId"])
                if gig is None:
                    continue
                if g["outcome"] in ("withdrawn", "released"):
                    self._end_gig(gig, "withdrawn")
                else:  # shortened or continues: the other cars stay on it
                    self._drop_stops(gig, lambda s: s["orderId"] == e["orderId"])
        elif kind == "release":
            self.released[(e["orderId"], e["leg"])] = e["at"]
        elif kind == "gig_booked":
            self._set(e["gigId"], status="booked", driverId=e["driverId"], feeCents=e["feeCents"])
        elif kind in ("gig_dropped", "no_show"):
            self._set(e["gigId"], status="open", driverId=None)
            self.late.pop(e["gigId"], None)
        elif kind == "gig_started":
            self._set(e["gigId"], status="working")
        elif kind == "driver_late":
            self.late[e["gigId"]] = e["pickupAt"]
        elif kind == "gig_expired":
            gig = self.gigs.get(e["gigId"])
            if gig is not None:
                self.expired.update(legs_of(gig))
                self._end_gig(gig, "withdrawn")
        elif kind == "picked_up":
            self.picked[(e["orderId"], e["leg"])] = e["at"]
        elif kind == "visit_failed":
            leg = (e["orderId"], e["leg"])
            self.failures.setdefault(leg, []).append(e["reason"])
            gig = self.gigs.get(e["gigId"])
            if gig is not None:
                self._drop_stops(gig, lambda s: (s["orderId"], s["leg"]) == leg)
        elif kind == "delivered":
            order = self.orders.get(e["orderId"])
            if order is not None:
                order["deliveredAt"][e["leg"]] = e["at"]
                if all(at is not None for at in order["deliveredAt"]):
                    order["status"] = "delivered"
            self.gig_of.pop((e["orderId"], e["leg"]), None)
            gig = self.gigs.get(e["gigId"])
            if gig is not None and not any(leg in self.gig_of for leg in legs_of(gig)):
                gig["status"] = "done"
        elif kind == "deadline_close":
            self.urgent[e["orderId"]] = e["at"]
            if e["orderId"] in self.orders:
                self.orders[e["orderId"]]["lastPickupAt"] = e["lastPickupAt"]
        elif kind == "forecast":
            self.forecasts.append(e)
        elif kind == "ledger":
            line = e["line"]
            self.margin_cents += line["cents"]
            if line["orderId"]:
                self.money.setdefault(line["orderId"], []).append((line["kind"], line["cents"]))
        return True

    def applied(self, action: Action, result: ActionResult) -> None:
        """Folds the result of one of our actions, applied at self.now."""
        if not result["ok"]:
            if action["type"] == "post":
                for s in action["stops"]:
                    self.refused[(s["orderId"], s["leg"])] = (self.now, result["reason"])
            return
        if action["type"] == "post":
            gig = {"id": result["id"], "stops": action["stops"], "audience": action["audience"],
                   "schedule": action["schedule"], "status": "open", "postedAt": self.now, "feeCents": 0,
                   "driverId": None, "scheduledAt": self.now}
            self.gigs[result["id"]] = gig
            for leg in legs_of(gig):
                self.gig_of[leg] = result["id"]
                self.expired.discard(leg)
                self.refused.pop(leg, None)
        elif action["type"] == "reprice":
            self._set(action["gigId"], schedule=action["schedule"], scheduledAt=self.now)
        elif action["type"] in ("withdraw", "release"):
            gig = self.gigs.get(action["gigId"])
            if gig is not None:
                self._end_gig(gig, "withdrawn")

    # --- views -----------------------------------------------------------------------------------------
    def active_orders(self) -> Iterable[Order]:
        """Won orders that are not cancelled and still have a car to deliver, in the order won."""
        return (o for o in self.orders.values() if o["status"] != "cancelled" and None in o["deliveredAt"])

    def undelivered(self, order: Order) -> list[int]:
        return [i for i, at in enumerate(order["deliveredAt"]) if at is None]

    def summary(self) -> dict[str, Any]:
        """A digest of the facts, to check that a replay rebuilds the same state."""
        facts = [self.seq, self.margin_cents, self.orders, self.gigs, sorted(self.gig_of.items()), sorted(self.failures.items()),
                 sorted(self.expired), sorted(self.urgent.items()), sorted(self.changed.items())]
        digest = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]
        statuses: dict[str, int] = {}
        for g in self.gigs.values():
            statuses[g["status"]] = statuses.get(g["status"], 0) + 1
        return {"seq": self.seq, "now": self.now, "marginCents": self.margin_cents, "requests": len(self.requests),
                "orders": len(self.orders), "gigs": statuses, "digest": digest}

    # --- helpers ---------------------------------------------------------------------------------------
    def _set(self, gig_id: str, **fields: Any) -> None:
        if gig_id in self.gigs:
            self.gigs[gig_id].update(fields)

    def _end_gig(self, gig: Gig, status: str) -> None:
        gig["status"] = status
        for leg in legs_of(gig):
            if self.gig_of.get(leg) == gig["id"]:
                del self.gig_of[leg]

    def _drop_stops(self, gig: Gig, drop: Callable[[Any], bool]) -> None:
        for s in gig["stops"]:
            if drop(s) and self.gig_of.get((s["orderId"], s["leg"])) == gig["id"]:
                del self.gig_of[(s["orderId"], s["leg"])]
        gig["stops"] = [s for s in gig["stops"] if not drop(s)]
        if not gig["stops"]:
            gig["status"] = "done"


def legs_of(gig: Gig) -> list[Leg]:
    return list(dict.fromkeys((s["orderId"], s["leg"]) for s in gig["stops"]))


def replay(lines: Iterable[dict], state: State) -> State:
    """Rebuilds a state from a run log: {"t":"now"}, {"t":"res"} and {"t":"ev"} lines, in order."""
    for line in lines:
        if line["t"] == "now":
            state.now = line["now"]
        elif line["t"] == "res":
            state.applied(line["a"], line["r"])
        elif line["t"] == "ev":
            state.apply(line["e"])
    return state
