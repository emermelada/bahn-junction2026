"""The two unannounced competitor events of level 8, read from our own wins and losses (RULES, HANDBOOK):

- Outage: on one working day, 08:00-18:00, the competitor is down in one region (a town and the places within
  80 km). Dealers there turn to a backup about 30% dearer. Sign: today we win nearly every quote picked up near
  one town. Answer: price higher there for the rest of the day.
- Price war: on one working day without an outage, 08:00-18:00, the competitor quotes 20% under its usual
  prices everywhere. Sign: today's win rate falls far under the week's so far. Answer: price lower for the
  rest of the day; the margin floor still declines what would not pay."""
from __future__ import annotations

import math

from spread.types import DeskEvent, PriceRequest

from spreadbot.core.state import State

DAY = 24 * 60
REGION_KM = 80  # RULES: the outage region is a town and the places within 80 km of it, in a straight line
OUTAGE_MIN, OUTAGE_RATE = 4, 0.85  # quotes near one town today, and the win rate that says its competitor is down
WAR_MIN, WAR_DROP = 20, 0.4  # quotes today, and today's win rate under this share of the week's says price war


def book(state: State) -> dict:
    return state.ext.setdefault("dealer", {}).setdefault("events", {"quoted": {}, "seen": []})


def record(state: State, request: PriceRequest) -> None:
    book(state)["quoted"][request["id"]] = request["legs"][0]["pickup"]["placeId"]


def observe(event: DeskEvent, state: State) -> None:
    if event["kind"] not in ("order_won", "order_lost"):
        return
    b = book(state)
    rid = event["order"]["id"] if event["kind"] == "order_won" else event["requestId"]
    town = b["quoted"].pop(rid, None)
    if town is not None:
        b["seen"].append((event["at"], town, event["kind"] == "order_won"))


def shift(state: State, request: PriceRequest, outage_up: float, war_down: float) -> float:
    """The ratio change for this request: +outage_up inside a region in outage, -war_down on a price-war day."""
    today = state.now // DAY
    seen = book(state)["seen"]
    past = [won for at, _, won in seen if at // DAY < today]
    now_ = [(town, won) for at, town, won in seen if at // DAY == today]
    if outage_up:
        here = state.places[request["legs"][0]["pickup"]["placeId"]]
        near = [won for town, won in now_ if km(here, state.places[town]) <= REGION_KM]
        if len(near) >= OUTAGE_MIN and sum(near) / len(near) >= OUTAGE_RATE:
            state.log(state.now, "outage_seen", request["id"], quotes=len(near))
            return outage_up
    if war_down and len(now_) >= WAR_MIN and len(past) >= WAR_MIN:
        if sum(w for _, w in now_) / len(now_) < WAR_DROP * sum(past) / len(past):
            state.log(state.now, "price_war_seen", request["id"], quotes=len(now_))
            return -war_down
    return 0.0


def km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
