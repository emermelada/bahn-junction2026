"""Quote policy, baseline: every serviceable option at one ratio above list; decline the rest. A2 replaces the
fixed ratio with the acceptance curve."""
from __future__ import annotations

from spread.types import PriceRequest

from spreadbot.core.rng import rng
from spreadbot.core.state import State
from spreadbot.dealer.flags import FLAGS
from spreadbot.dealer.trust import trust_factor
from spreadbot.driver.cost import estimate_cost

DECLINE_RATIO = 5  # RULES: a quote far above list loses and costs nothing; 5x list is far above the 26-54% range


def quote(request: PriceRequest, state: State) -> dict[str, int]:
    if FLAGS["ladder"]:
        r = rng(state.world_id, request["id"])
        option = r.choice(request["options"])
        return {option["kind"]: round(option["listPriceCents"] * (1 + r.random() * FLAGS["ladder"]))}
    prices = {}
    trust = trust_factor(state, request["dealerId"]) if FLAGS["trust"] else 1.0
    for o in request["options"]:
        cost = estimate_cost(request, o, state)
        price = round(o["listPriceCents"] * trust * (FLAGS["quote_ratio"] + FLAGS["same_day_extra"] * (o["kind"] == "same_day")))
        floor = FLAGS["min_margin_cents"]
        if cost.serviceable and (floor is None or price - cost.fee_cents >= floor):
            prices[o["kind"]] = price
    return prices or decline(request)


def decline(request: PriceRequest) -> dict[str, int]:
    """The safe answer: a price no dealer takes. Never leave a request unanswered."""
    first = request["options"][0]
    return {first["kind"]: first["listPriceCents"] * DECLINE_RATIO}
