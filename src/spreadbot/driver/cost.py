"""Cost oracle, v0 stub: every option costs the typical fee, is on time and serviceable. B1 replaces it."""
from __future__ import annotations

from spread.types import DeliveryOption, PriceRequest

from spreadbot.core.interfaces import CostEstimate
from spreadbot.core.state import State


def estimate_cost(request: PriceRequest, option: DeliveryOption, state: State) -> CostEstimate:
    return CostEstimate(fee_cents=request["referenceFeeCents"], p_on_time=1.0, serviceable=True)
