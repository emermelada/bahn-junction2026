"""Chain offers: a driver who already holds one of our gigs pays only the extra time and tickets for a second
one (HANDBOOK). When such a driver will finish near the pickup of an open gig, in time for it, offer them that
gig directly at a lower fee than the app's. RULES limits: 3 offers per driver per day, 3 open offers per gig,
10 minutes each, none read from 23:00 to 07:00."""
from __future__ import annotations

from spread.types import Action, DeskEvent

from spreadbot.core.state import State
from spreadbot.driver.flags import FLAGS

DAY = 24 * 60
PER_DRIVER_DAY, PER_GIG = 3, 3  # RULES
QUIET_FROM, QUIET_TO = 23 * 60, 7 * 60  # RULES: no driver reads an offer from 23:00 to 07:00
REACH = 45  # road minutes at most from the driver's last delivery to the offered pickup
SPARE = 60  # minutes of spare time the chain keeps before the offered car's last pickup


def book(state: State) -> dict:
    return state.ext.setdefault("driver", {}).setdefault("chains", {"open": {}, "sent": {}, "tried": set()})


def observe(event: DeskEvent, state: State) -> None:
    if event["kind"] == "offer_answered":
        b = book(state)
        b["open"][event["gigId"]] = max(0, b["open"].get(event["gigId"], 0) - 1)


def chain_offers(state: State, now: int) -> list[Action]:
    if not FLAGS["chain_offer"] or not QUIET_TO <= now % DAY < QUIET_FROM:
        return []
    b = book(state)
    finishing = []  # (driver, place, minute) for drivers on our booked or working gigs
    for gig in state.gigs.values():
        if gig["status"] not in ("booked", "working") or not gig["driverId"]:
            continue
        last = gig["stops"][-1]
        order = state.orders.get(last["orderId"])
        if order is None:
            continue
        first = gig["stops"][0]
        start = max(now, state.orders[first["orderId"]]["legs"][first["leg"]]["pickup"]["window"]["from"])
        place = order["legs"][last["leg"]]["delivery"]["placeId"]
        pickup = state.orders[first["orderId"]]["legs"][first["leg"]]["pickup"]["placeId"]
        finishing.append((gig["driverId"], place, start + state.minutes(pickup, place)))
    actions: list[Action] = []
    for gid, gig in state.gigs.items():
        if gig["status"] != "open" or len({s["orderId"] for s in gig["stops"]}) != 1 or b["open"].get(gid, 0) >= PER_GIG:
            continue
        first = gig["stops"][0]
        order = state.orders.get(first["orderId"])
        if order is None or order["id"] in state.urgent:
            continue
        leg = order["legs"][first["leg"]]
        for driver, place, done in finishing:
            if (driver, gid) in b["tried"] or b["sent"].get((driver, now // DAY), 0) >= PER_DRIVER_DAY:
                continue
            arrive = done + state.minutes(place, leg["pickup"]["placeId"])
            if state.minutes(place, leg["pickup"]["placeId"]) > REACH or arrive > order["lastPickupAt"] - SPARE:
                continue
            cars = sum(1 for s in gig["stops"] if s["kind"] == "pickup")
            fee = round(state.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"]) * FLAGS["chain_offer"])
            b["tried"].add((driver, gid))
            b["sent"][(driver, now // DAY)] = b["sent"].get((driver, now // DAY), 0) + 1
            b["open"][gid] = b["open"].get(gid, 0) + 1
            actions.append({"type": "offer", "gigId": gid, "driverId": driver, "feeCents": fee})
            state.log(now, "chain_offer", gid, driver=driver, fee=fee)
            if b["open"][gid] >= PER_GIG:
                break
    return actions
