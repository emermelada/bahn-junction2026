"""Dealer trust at level 8 (RULES): each dealer counts our orders delivered to it on time, up to 25; each
raises the prices it accepts from us by 1%; a late order halves the count, rounded down. We count it from
our own account: an order's revenue line with no late refund is on time."""
from __future__ import annotations

from spreadbot.core.state import State

CAP = 25  # RULES: the count stops at 25 orders
STEP = 0.01  # RULES: each counted order raises accepted prices by 1%


def trust_count(state: State, dealer_id: str) -> int:
    """The dealer's count now, replaying its settled orders in the order we won them."""
    count = 0
    for order in state.orders.values():
        if order["dealerId"] != dealer_id:
            continue
        kinds = [k for k, _ in state.money.get(order["id"], [])]
        if "revenue" not in kinds and "undelivered_penalty" not in kinds:
            continue  # not settled yet
        if "late_refund" in kinds or "undelivered_penalty" in kinds:
            count //= 2
        else:
            count = min(CAP, count + 1)
    return count


def trust_factor(state: State, dealer_id: str) -> float:
    return 1 + STEP * trust_count(state, dealer_id) if state.level >= 8 else 1.0
