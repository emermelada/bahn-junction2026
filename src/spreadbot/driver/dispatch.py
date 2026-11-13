"""Dispatch, v0 stub: the kit starter's behaviour, written as a reconciler over State.

Each call compares what should be on the road with what is, and returns the actions that close the gap:
every undelivered leg of a live order sits on a live gig; a gig of an order whose plan changed is posted
again; once the deadline warning comes, the order's open gigs go at steep fees. Because it reads only
State, the same code serves a normal step and a restart."""
from __future__ import annotations

from typing import Optional

from spread.types import Action, FeeStep, Order, StopRef

from spreadbot.core.rng import rng
from spreadbot.core.state import State, legs_of
from spreadbot.driver.flags import FLAGS
from spreadbot.notes.reader import needs_manual, needs_plates, window_from_note

HOUR, DAY = 60, 24 * 60
MID_SLACK = 8 * HOUR  # fee ladder: with 8-24 h to the last pickup, gigs near the typical fee still booked in time
SPLIT_MINUTES = 12 * HOUR  # RULES: a gig with more than one car may plan at most 12 hours of driving
BUNDLE_BUFFER = 60  # minutes of spare time a chain keeps before each car's deadline, for real driving times
REFUSED_BACKOFF = 30  # minutes before we try a refused post again; refusals name a window, so the next try usually differs


def dispatch(state: State, now: int) -> list[Action]:
    actions: list[Action] = []
    waiting: list[Order] = []  # new single cars held back a while to find a partner for a two-car chain
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
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now, base=gig_base(state, gig))})
                state.log(now, "reprice_urgent", gid, order=oid)
            elif FLAGS["raise_lead"] and oid not in state.urgent and now >= (due := order["lastPickupAt"] - FLAGS["raise_lead"]) \
                    and gig["scheduledAt"] < due:
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now, raised=True, base=gig_base(state, gig))})
                state.log(now, "reprice_early", gid, order=oid)
        need = [leg for leg in state.undelivered(order) if (oid, leg) not in state.gig_of or leg in freed]
        need = [leg for leg in need if not _backing_off(state, (oid, leg), now)]
        if not need:
            continue
        if FLAGS["bundle"] and pairable(state, order, need, now):
            waiting.append(order)
            continue
        groups = [need] if len(need) == 1 or drive_minutes(state, order, need) <= SPLIT_MINUTES else [[leg] for leg in need]
        for legs in groups:
            actions.append(post(state, order, legs, now))
            state.log(now, "post", oid, legs=legs, retry=any((oid, leg) in state.failures for leg in legs))
    return actions + bundles(state, waiting, now)


def post(state: State, order: Order, legs: list[int], now: int) -> Action:
    oid = order["id"]
    reasons = [r for leg in legs for r in state.failures.get((oid, leg), [])]
    note = state.requests[oid]["note"] if FLAGS["read_notes"] else None
    audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]),
                "manualLicence": "licence" in reasons or needs_manual(note)}
    stops: list[StopRef] = []
    for leg in legs:
        car, pickup, delivery = order["legs"][leg]["car"], order["legs"][leg]["pickup"], order["legs"][leg]["delivery"]
        first: StopRef = {"orderId": oid, "leg": leg, "kind": "pickup", "withPlates": "no_plates" in reasons or needs_plates(note),
                          "withCharging": bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30)}
        second: StopRef = {"orderId": oid, "leg": leg, "kind": "delivery"}
        noted = window_from_note(note, pickup["window"], "pickup")
        if noted != pickup["window"]:
            first["window"] = noted
        base = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], order["deadline"])}
        noted = window_from_note(note, base, "delivery")
        if noted != base:
            second["window"] = noted
        last = state.failures.get((oid, leg), [None])[-1]
        if last in ("not_ready", "closed"):
            start = max(retry_from(state, order, leg, now), first.get("window", pickup["window"])["from"])
            first["window"] = {"from": start, "to": max(pickup["window"]["to"], start)}
        stops += [first, second]
    expired = any((oid, leg) in state.expired for leg in legs)
    stops = without_windows(stops, float("inf") if expired else now)
    return {"type": "post", "stops": stops, "audience": audience, "schedule": fees(state, order, len(legs), now)}


def fees(state: State, order: Order, cars: int, now: int, raised: bool = False, base: Optional[float] = None) -> list[FeeStep]:
    fee = base if base is not None else state.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
    if FLAGS["fee_ladder"]:
        ratio = 0.8 + rng(state.world_id, order["id"], cars).random() * FLAGS["fee_ladder"]
        return [{"at": now, "feeCents": max(1, int(fee * ratio + 0.5))}]
    lo, hi = FLAGS["fee_open"], FLAGS["fee_top"]
    left = order["lastPickupAt"] - now
    weekend = order["lastPickupAt"] // DAY >= 5
    if FLAGS["fee_open_long"] and left >= DAY and (FLAGS["long_fee_over_weekend"] or not weekend):  # time to wait for cheaper drivers
        lo, hi = FLAGS["fee_open_long"], FLAGS["fee_open_long"]
    elif FLAGS["fee_open_weekend"] and weekend:
        lo, hi = FLAGS["fee_open_weekend"], FLAGS["fee_open_weekend"]
    elif FLAGS["fee_open_mid"] and left >= MID_SLACK:
        lo, hi = FLAGS["fee_open_mid"], FLAGS["fee_open_mid"]
    if order["id"] in state.urgent:  # the top fee or 1.5 times at once, then a quarter more every half hour
        steps = [(k * 30, max(1.5, hi) + k / 4) for k in range(5)]
    elif raised:  # one early raise for a gig still open close to its last pickup, before the deadline warning
        steps = [(0, FLAGS["fee_raise"])]
    elif hi <= lo:  # one flat fee: drivers who see no raises have nothing to wait for
        steps = [(0, lo)]
    else:  # from the opening fee up to the top, in five hourly steps (the starter: 1.0 to 1.5)
        steps = [(k * HOUR, lo + (hi - lo) * k / 5) for k in range(6)]
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


def gig_base(state: State, gig) -> float:
    """The typical fee of all the cars on a gig, which may come from two orders."""
    return sum(state.requests[st["orderId"]]["referenceFeeCents"] / len(state.orders[st["orderId"]]["legs"])
               for st in gig["stops"] if st["kind"] == "pickup")


# --- two-car chains ----------------------------------------------------------------------------------------------
# A driver who delivers car A where car B waits saves a trip home and a trip out (HANDBOOK: a gig that ends near
# the next pickup is cheap). We hold a new single car for a while, pair it with another whose pickup lies near
# its delivery, and post both as one gig at a discount on the two fees.

def pairable(state: State, order: Order, need: list[int], now: int) -> bool:
    """A new single car, with time to spare, still inside its holding time."""
    oid = order["id"]
    return (len(order["legs"]) == 1 and need == [0] and oid not in state.urgent and (oid, 0) not in state.failures
            and (oid, 0) not in state.expired and order["lastPickupAt"] - now >= FLAGS["bundle_slack"]
            and now - state.requests[oid]["respondBy"] < FLAGS["bundle_hold"])


def chain_ok(state: State, a: Order, b: Order, now: int) -> bool:
    """One driver can take car A, then car B, on time and within the 12-hour driving limit."""
    la, lb = a["legs"][0], b["legs"][0]
    pa, da, pb, db = la["pickup"]["placeId"], la["delivery"]["placeId"], lb["pickup"]["placeId"], lb["delivery"]["placeId"]
    gap = state.minutes(da, pb)
    if gap > FLAGS["bundle_gap"] or state.minutes(pa, da) + gap + state.minutes(pb, db) > SPLIT_MINUTES:
        return False
    at_da = max(now, la["pickup"]["window"]["from"]) + state.minutes(pa, da)
    at_pb = max(at_da + gap, lb["pickup"]["window"]["from"])
    return (at_da <= a["deadline"] - BUNDLE_BUFFER and at_pb <= lb["pickup"]["window"]["to"]
            and at_pb + state.minutes(pb, db) <= b["deadline"] - BUNDLE_BUFFER)


def bundles(state: State, waiting: list[Order], now: int) -> list[Action]:
    """Pairs held cars greedily, in the order won. Unpaired cars wait until their holding time is over."""
    actions: list[Action] = []
    used: set[str] = set()
    for a in waiting:
        if a["id"] in used:
            continue
        for b in waiting:
            if b["id"] in used or b is a or not chain_ok(state, a, b, now):
                continue
            pa, pb = post(state, a, [0], now), post(state, b, [0], now)
            fee = round((pa["schedule"][0]["feeCents"] + pb["schedule"][0]["feeCents"]) * FLAGS["bundle_factor"])
            audience = {k: pa["audience"][k] or pb["audience"][k] for k in pa["audience"]}
            actions.append({"type": "post", "stops": pa["stops"] + pb["stops"], "audience": audience,
                            "schedule": [{"at": now, "feeCents": fee}]})
            used.update((a["id"], b["id"]))
            state.log(now, "post_bundle", a["id"], with_order=b["id"], fee=fee)
            break
    return actions


def _backing_off(state: State, leg: tuple[str, int], now: int) -> bool:
    refused: Optional[tuple[int, str]] = state.refused.get(leg)
    return refused is not None and now - refused[0] < REFUSED_BACKOFF


def _cars(gig) -> int:
    return sum(1 for s in gig["stops"] if s["kind"] == "pickup")
