"""On-time governor: the 90% delivery minimum is a cliff, so it gets its own guard.

It projects the week's late share: orders already late, plus orders that can no longer be on time (no
driver and past lastPickupAt), plus half of those with a deadline warning and still no driver, over all
won orders. The mode then tells the quote side how much risk it may still take on."""
from __future__ import annotations

from spreadbot.core.state import State
from spreadbot.driver.flags import FLAGS

# Plan: treat lateness as a budget, plan for 5%, never spend 10%. Thresholds on the projected late share:
TIGHT = 0.05  # above this, win only cars that are easy to move
RESCUE = 0.08  # above this, win almost nothing new until the share recovers
MIN_ORDERS = 40  # early in the week one late car is not 100% late: divide by at least this many orders


def projected_late_share(state: State, now: int) -> float:
    won = late = 0.0
    for order in state.orders.values():
        if order["status"] == "cancelled":
            continue
        won += 1
        kinds = [k for k, _ in state.money.get(order["id"], [])]
        if "late_refund" in kinds or "undelivered_penalty" in kinds:
            late += 1
            continue
        if order["status"] == "delivered":
            continue
        unheld = any(state.gig_of.get((order["id"], leg)) is None or state.gigs[state.gig_of[(order["id"], leg)]]["status"] == "open"
                     for leg in state.undelivered(order))
        if unheld and now > order["lastPickupAt"]:
            late += 1
        elif unheld and order["id"] in state.urgent:
            late += 0.5
    return late / max(won, MIN_ORDERS)


def risk_mode(state: State, now: int) -> str:
    if not FLAGS["governor"]:
        return "normal"
    cache = state.ext.setdefault("driver", {})
    if cache.get("mode_at") != now:
        share = projected_late_share(state, now)
        cache["mode_at"], cache["mode"] = now, "rescue" if share > RESCUE else "tight" if share > TIGHT else "normal"
    return cache["mode"]
