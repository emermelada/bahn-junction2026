"""Dispatch, v0 stub: the kit starter's behaviour, written as a reconciler over State.

Each call compares what should be on the road with what is, and returns the actions that close the gap:
every undelivered leg of a live order sits on a live gig; a gig of an order whose plan changed is posted
again; once the deadline warning comes, the order's open gigs go at steep fees. Because it reads only
State, the same code serves a normal step and a restart."""
from __future__ import annotations

from typing import Optional

from spread.types import Action, FeeStep, Order, StopRef

from spreadbot.core.state import State, legs_of

HOUR = 60
SPLIT_MINUTES = 12 * HOUR  # RULES: a gig with more than one car may plan at most 12 hours of driving
REFUSED_BACKOFF = 30  # minutes before we try a refused post again; refusals name a window, so the next try usually differs


def dispatch(state: State, now: int) -> list[Action]:
    actions: list[Action] = []
    for order in state.active_orders():
        oid = order["id"]
        gig_ids = list(dict.fromkeys(state.gig_of[(oid, leg)] for leg in state.undelivered(order) if (oid, leg) in state.gig_of))
        freed: set[int] = set()
        for gid in gig_ids:
            gig = state.gigs[gid]
            if gig["status"] != "open":
                continue
            if oid in state.changed and gig["postedAt"] < state.changed[oid]:
                actions.append({"type": "withdraw", "gigId": gid})
                freed.update(leg for o, leg in legs_of(gig) if o == oid)
                state.log(now, "withdraw_changed", gid, order=oid)
            elif oid in state.urgent and gig["scheduledAt"] < state.urgent[oid]:
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now)})
                state.log(now, "reprice_urgent", gid, order=oid)
        need = [leg for leg in state.undelivered(order) if (oid, leg) not in state.gig_of or leg in freed]
        need = [leg for leg in need if not _backing_off(state, (oid, leg), now)]
        if not need:
            continue
        groups = [need] if len(need) == 1 or drive_minutes(state, order, need) <= SPLIT_MINUTES else [[leg] for leg in need]
        for legs in groups:
            actions.append(post(state, order, legs, now))
            state.log(now, "post", oid, legs=legs, retry=any((oid, leg) in state.failures for leg in legs))
    return actions


def post(state: State, order: Order, legs: list[int], now: int) -> Action:
    oid = order["id"]
    reasons = [r for leg in legs for r in state.failures.get((oid, leg), [])]
    audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]), "manualLicence": "licence" in reasons}
    stops: list[StopRef] = []
    for leg in legs:
        car, pickup = order["legs"][leg]["car"], order["legs"][leg]["pickup"]
        first: StopRef = {"orderId": oid, "leg": leg, "kind": "pickup", "withPlates": "no_plates" in reasons,
                          "withCharging": bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30)}
        last = state.failures.get((oid, leg), [None])[-1]
        if last in ("not_ready", "closed"):
            start = retry_from(state, order, leg, now)
            first["window"] = {"from": start, "to": max(pickup["window"]["to"], start)}
        stops += [first, {"orderId": oid, "leg": leg, "kind": "delivery"}]
    expired = any((oid, leg) in state.expired for leg in legs)
    stops = without_windows(stops, float("inf") if expired else now)
    return {"type": "post", "stops": stops, "audience": audience, "schedule": fees(state, order, len(legs), now)}


def fees(state: State, order: Order, cars: int, now: int) -> list[FeeStep]:
    fee = state.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
    if order["id"] in state.urgent:  # 1.5 times at once, then a quarter more every half hour, up to 2.5 times
        steps = [(k * 30, 1.5 + k / 4) for k in range(5)]
    else:  # the typical fee, then 10% more every hour, up to 1.5 times
        steps = [(k * HOUR, 1 + k / 10) for k in range(6)]
    if state.level == 1:
        steps = steps[:1]
    return [{"at": now + dt, "feeCents": max(1, int(fee * f + 0.5))} for dt, f in steps]


def retry_from(state: State, order: Order, leg: int, now: int) -> int:
    """After a visit found the car not ready or the site closed: two hours on, or later when the dealer
    moved the deadline by a delay."""
    request = state.requests[order["id"]]
    promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), order["deadline"])
    return max(now + 2 * HOUR, order["legs"][leg]["pickup"]["window"]["from"] + max(0, order["deadline"] - promised))


def without_windows(stops: list[StopRef], before: float) -> list[StopRef]:
    """Drops stop windows that end before `before`, so the order's window applies, which runs to the end of
    the world once it has ended."""
    return [{k: v for k, v in s.items() if k != "window"} if "window" in s and s["window"]["to"] < before else s for s in stops]


def drive_minutes(state: State, order: Order, legs: list[int]) -> int:
    """Road minutes from the first pickup to the last delivery, legs in order."""
    places = [p for leg in legs for p in (order["legs"][leg]["pickup"]["placeId"], order["legs"][leg]["delivery"]["placeId"])]
    return sum(state.minutes(a, b) for a, b in zip(places, places[1:]))


def _backing_off(state: State, leg: tuple[str, int], now: int) -> bool:
    refused: Optional[tuple[int, str]] = state.refused.get(leg)
    return refused is not None and now - refused[0] < REFUSED_BACKOFF


def _cars(gig) -> int:
    return sum(1 for s in gig["stops"] if s["kind"] == "pickup")
