"""Cost oracle, v1: serviceability from where drivers live and how many cars we already won there.
The fee is still the typical fee and p_on_time is still 1; B1 learns both."""
from __future__ import annotations

import math

from spread.types import DeliveryOption, PriceRequest

from spreadbot.core.interfaces import CostEstimate
from spreadbot.core.state import State
from spreadbot.driver.flags import FLAGS
from spreadbot.governor import risk_mode

DAY = 24 * 60
EASY_DRIVERS = 30  # in rescue mode, only pickups with this many drivers living within 30 km count as easy
NOTIFY_KM = 30  # RULES: the app notifies drivers whose home is within 30 km of the first pickup, in a straight line


def estimate_cost(request: PriceRequest, option: DeliveryOption, state: State) -> CostEstimate:
    serviceable = True
    for leg in request["legs"]:
        town, day = leg["pickup"]["placeId"], leg["pickup"]["window"]["from"] // DAY
        near = drivers_near(state, town)
        if near < FLAGS["min_drivers_near"]:
            serviceable = False
        cap = FLAGS["cars_per_driver_day"]
        if cap and won_cars(state, town, day) + 1 > cap * near:
            serviceable = False
    if FLAGS["min_slack"] and slack(request, option, state) < FLAGS["min_slack"]:
        serviceable = False
    mode = risk_mode(state, state.now)
    cap = FLAGS["max_backlog"] // 2 if mode == "tight" else FLAGS["max_backlog"]
    if cap and backlog(state) >= cap:
        serviceable = False
    if mode != "normal" and option["kind"] == "same_day":
        serviceable = False
    if mode == "rescue" and min(drivers_near(state, leg["pickup"]["placeId"]) for leg in request["legs"]) < EASY_DRIVERS:
        serviceable = False
    fee = round(request["referenceFeeCents"] * FLAGS["fee_open"])  # what dispatch will open the gig at
    return CostEstimate(fee_cents=fee, p_on_time=1.0, serviceable=serviceable)


def slack(request: PriceRequest, option: DeliveryOption, state: State) -> int:
    """Minutes from the moment we would win the order to its latest pickup by road time. A gig posted
    with under 3 hours of this left almost never found a driver in time (dev-02, 1 of 36)."""
    legs = request["legs"]
    drive = sum(state.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
    drive += sum(40 for leg in legs if leg["car"]["electric"] and (leg["car"]["chargePercent"] or 100) < 30)
    if len(legs) == 2:
        drive += state.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])
    deadline = option["deadline"]
    delivery = legs[-1]["delivery"]
    if delivery["privateAddress"]:
        deadline = min(deadline, delivery["window"]["to"] + 30)  # RULES: a private delivery is due 30 min after its hour
    return deadline - drive - request["respondBy"]


def backlog(state: State) -> int:
    """Won orders due for pickup within a day with a car that no driver holds yet. Cached per minute.
    Later orders are left out: drivers book a later day only once they know they work it."""
    cache = state.ext.setdefault("driver", {})
    if cache.get("backlog_at") != state.now:
        n = 0
        for o in state.active_orders():
            if o["lastPickupAt"] > state.now + DAY:
                continue
            for leg in state.undelivered(o):
                gid = state.gig_of.get((o["id"], leg))
                if gid is None or state.gigs[gid]["status"] == "open":
                    n += 1
                    break
        cache["backlog_at"], cache["backlog"] = state.now, n
    return cache["backlog"]


def drivers_near(state: State, town: str) -> int:
    """Drivers living within 30 km of a town, from the driver list. Cached per world."""
    cache = state.ext.setdefault("driver", {}).setdefault("near", {})
    if town not in cache:
        homes: dict[str, int] = {}
        for d in state.ext.get("roster", []):
            homes[d["homePlaceId"]] = homes.get(d["homePlaceId"], 0) + 1
        here = state.places[town]
        cache[town] = sum(n for h, n in homes.items() if km(here, state.places[h]) <= NOTIFY_KM)
    return cache[town]


def won_cars(state: State, town: str, day: int) -> int:
    """Cars of live won orders that are collected in this town on this day."""
    return sum(1 for o in state.orders.values() if o["status"] != "cancelled"
               for leg in o["legs"] if leg["pickup"]["placeId"] == town and leg["pickup"]["window"]["from"] // DAY == day)


def km(a: dict, b: dict) -> float:
    """Great-circle km between two places."""
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
