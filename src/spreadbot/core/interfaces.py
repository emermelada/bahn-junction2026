# src/spreadbot/core/interfaces.py   (frozen after tag v0)
"""The contract between the dealer side (A) and the driver side (B).

B implements, A calls:
    driver.cost.estimate_cost(request, option, state) -> CostEstimate
    governor.risk_mode(state, now) -> str        # "normal" | "tight" | "rescue"
    driver.dispatch.dispatch(state, now) -> list[Action]   # post, reprice, offer, withdraw, release

A implements, the runner calls:
    dealer.quote.quote(request, state) -> dict[str, int]   # option kind -> price in cents

Each side keeps its own trackers in state.ext["dealer"] / state.ext["driver"],
fed by its observe(event, state), so neither side edits core/state.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostEstimate:
    fee_cents: int  # expected total driver cost for this option
    p_on_time: float  # chance that every car arrives by its deadline
    serviceable: bool  # False means decline at any price


RISK_MODES = ("normal", "tight", "rescue")
