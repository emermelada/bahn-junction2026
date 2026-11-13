"""Rescue offers: after an order's deadline warning, send its open gig straight to drivers who can still
take it in time: those who viewed it (they use the app today), then those living within 30 km of the
pickup. An offer reaches a driver whom a raise in the app does not notify.

RULES limits: at most 3 offers per driver per day, at most 3 open offers per gig, an offer stays open
10 minutes, and no driver reads one from 23:00 to 07:00."""
from __future__ import annotations

from spread.types import Action, DeskEvent, Order

from spreadbot.core.state import State
from spreadbot.driver.cost import drivers_near_ids
from spreadbot.driver.flags import FLAGS

DAY = 24 * 60
PER_DRIVER_DAY, PER_GIG, OPEN_MINUTES = 3, 3, 10  # RULES
QUIET = (23 * 60, 7 * 60)  # RULES: no driver reads an offer from 23:00 to 07:00


def book(state: State) -> dict:
    return state.ext.setdefault("driver", {}).setdefault("offers", {"viewers": {}, "open": {}, "sent": {}, "tried": set()})


def observe(event: DeskEvent, state: State) -> None:
    b = book(state)
    if event["kind"] == "gig_viewed":
        viewers = b["viewers"].setdefault(event["gigId"], [])
        if event["driverId"] not in viewers:
            viewers.append(event["driverId"])
    elif event["kind"] == "offer_answered":
        b["open"][event["gigId"]] = max(0, b["open"].get(event["gigId"], 0) - 1)


def rescue_offers(state: State, order: Order, gig_id: str, cars: int, now: int) -> list[Action]:
    if not FLAGS["offer_fee"] or not (QUIET[1] <= now % DAY < QUIET[0]):
        return []
    b = book(state)
    room = PER_GIG - b["open"].get(gig_id, 0)
    if room <= 0:
        return []
    request = state.requests[order["id"]]
    fee = round(request["referenceFeeCents"] * cars / len(order["legs"]) * FLAGS["offer_fee"])
    pickup = order["legs"][0]["pickup"]["placeId"]
    audience = state.gigs[gig_id]["audience"]
    licence = {d["id"]: d for d in state.ext.get("roster", [])}
    candidates = b["viewers"].get(gig_id, []) + drivers_near_ids(state, pickup)
    actions: list[Action] = []
    for driver in dict.fromkeys(candidates):
        if len(actions) == room:
            break
        profile = licence.get(driver)
        if profile is None or (driver, gig_id) in b["tried"]:
            continue
        if audience.get("manualLicence") and profile["licence"] != "manual":
            continue
        if audience.get("experienced") and (profile["rating"] < 4.8 or profile["completedGigs"] < 50):  # RULES
            continue
        day_key = (driver, now // DAY)
        if b["sent"].get(day_key, 0) >= PER_DRIVER_DAY:
            continue
        b["sent"][day_key] = b["sent"].get(day_key, 0) + 1
        b["tried"].add((driver, gig_id))
        b["open"][gig_id] = b["open"].get(gig_id, 0) + 1
        actions.append({"type": "offer", "gigId": gig_id, "driverId": driver, "feeCents": fee})
    return actions
