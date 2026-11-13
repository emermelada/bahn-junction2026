"""Quote policy: every serviceable option at one ratio of list (times the dealer's trust); decline the rest.
The ratio is fixed (quote_ratio) or, with learn_price, the one that maximises win chance x margin on the
live win model, with a small seeded jitter so the curve keeps learning around its optimum."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from spread.types import PriceRequest

from spreadbot.core.rng import rng
from spreadbot.core.state import State
from spreadbot.dealer.flags import FLAGS
from spreadbot.dealer.trust import trust_factor
from spreadbot.dealer.win_model import curve, record_quote
from spreadbot.driver.cost import estimate_cost

DECLINE_RATIO = 5  # RULES: a quote far above list loses and costs nothing; 5x list is far above the 26-54% range
CANDIDATES = [1.10 + 0.02 * k for k in range(31)]  # 1.10 .. 1.70
JITTER = 0.04
LANE_CAP = 0.35  # no lane moves the ratio more than this: the table's p10-p90 is -0.30 to +0.25  # exploration around the chosen ratio, so the curve sees both sides of it


def quote(request: PriceRequest, state: State) -> dict[str, int]:
    if FLAGS["ladder"]:
        r = rng(state.world_id, request["id"])
        option = r.choice(request["options"])
        return {option["kind"]: round(option["listPriceCents"] * (1 + r.random() * FLAGS["ladder"]))}
    prices = {}
    trust = trust_factor(state, request["dealerId"]) if FLAGS["trust"] else 1.0
    costs = {o["kind"]: estimate_cost(request, o, state) for o in request["options"]}
    ratio = FLAGS["quote_ratio"] + FLAGS["lane_weight"] * lane_shift(request)
    if FLAGS["learn_price"]:
        ratio = best_ratio(request, state, trust, costs)
        ratio += (rng(state.world_id, request["id"], "jitter").random() * 2 - 1) * JITTER
        record_quote(state, request["id"], ratio)
    for o in request["options"]:
        cost = costs[o["kind"]]
        price = round(o["listPriceCents"] * trust * (ratio + FLAGS["same_day_extra"] * (o["kind"] == "same_day")))
        floor = FLAGS["min_margin_cents"]
        if cost.serviceable and floor is not None and price - cost.fee_cents < floor and FLAGS["max_ratio"]:
            price = max(price, cost.fee_cents + floor)  # price to cost: let the dealer decide instead of declining
            if price > o["listPriceCents"] * FLAGS["max_ratio"]:
                price = 0
        if cost.serviceable and price and (floor is None or price - cost.fee_cents >= floor):
            prices[o["kind"]] = price
        elif cost.serviceable:
            state.log(state.now, "below_floor", request["id"], option=o["kind"], margin=price - cost.fee_cents)
    return prices or decline(request)


def best_ratio(request: PriceRequest, state: State, trust: float, costs: dict) -> float:
    """The ratio that maximises P(win) x (price - fee - floor) on the request's slowest serviceable option.
    Drivers, not requests, are scarce: the margin floor stands in for the price of using one up."""
    options = [o for o in request["options"] if costs[o["kind"]].serviceable] or request["options"]
    o = options[-1]
    c = curve(state)
    cost = costs[o["kind"]].fee_cents + (FLAGS["min_margin_cents"] or 0)
    return max(CANDIDATES, key=lambda r: c.p(r, state.now) * (r * trust * o["listPriceCents"] - cost))


@lru_cache(maxsize=1)
def lanes() -> dict[str, float]:
    """Per lane, how much higher a ratio wins as often (lab/a/lane_table.py, fitted on all our level 8 weeks)."""
    with open(os.path.join(os.path.dirname(__file__), "lanes.json"), encoding="utf-8") as f:
        return json.load(f)["shift"]


def lane_shift(request: PriceRequest) -> float:
    """The competitor's lane factor that holds in every world (RULES), as a ratio shift; 0 for unseen lanes."""
    lane = request["legs"][0]["pickup"]["placeId"] + ">" + request["legs"][-1]["delivery"]["placeId"]
    return max(-LANE_CAP, min(LANE_CAP, lanes().get(lane, 0.0)))


def decline(request: PriceRequest) -> dict[str, int]:
    """The safe answer: a price no dealer takes. Never leave a request unanswered."""
    first = request["options"][0]
    return {first["kind"]: first["listPriceCents"] * DECLINE_RATIO}
