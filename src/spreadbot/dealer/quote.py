"""Quote policy, v0 stub: the kit starter's quote, the list price of the first option. A2 replaces it."""
from __future__ import annotations

from spread.types import PriceRequest

from spreadbot.core.state import State

DECLINE_RATIO = 5  # RULES: a quote far above list loses and costs nothing; 5x list is far above the 26-54% range


def quote(request: PriceRequest, state: State) -> dict[str, int]:
    first = request["options"][0]
    return {first["kind"]: first["listPriceCents"]}


def decline(request: PriceRequest) -> dict[str, int]:
    """The safe answer: a price no dealer takes. Never leave a request unanswered."""
    first = request["options"][0]
    return {first["kind"]: first["listPriceCents"] * DECLINE_RATIO}
