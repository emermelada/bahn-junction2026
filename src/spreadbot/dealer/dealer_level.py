"""Per-dealer price level, relative to this week's average (HANDBOOK: dealers differ in how much price matters to
them; the competitor raises its prices for a dealer whose requests we mostly lose). A dealer that accepts our
quotes more often than the average dealer this week gets a higher ratio, one that rarely does gets a lower one.

Measured against this week's own average win rate, not a historical one, so it moves prices around our level
instead of moving the level itself (week_level.py moved the level and lost on fresh seeds)."""
from __future__ import annotations

import math

from spread.types import DeskEvent

from spreadbot.core.state import State

SLOPE = 8.0  # the price ladder: win 85% at 1.1x list, 10% at 1.6x, inside one week
PULL = 30.0  # quotes a dealer needs before its own rate outweighs the week's average
HALF_LIFE = 1440  # world minutes; the competitor re-prices each dealer every morning


def book(state: State) -> dict:
    return state.ext.setdefault("dealer", {}).setdefault("dealers", {"quoted": {}, "seen": []})


def record(state: State, request_id: str, dealer_id: str) -> None:
    book(state)["quoted"][request_id] = dealer_id


def observe(event: DeskEvent, state: State) -> None:
    if event["kind"] not in ("order_won", "order_lost"):
        return
    b = book(state)
    rid = event["order"]["id"] if event["kind"] == "order_won" else event["requestId"]
    dealer = b["quoted"].pop(rid, None)
    if dealer is not None:
        b["seen"].append((event["at"], dealer, event["kind"] == "order_won"))


def shift(state: State, dealer_id: str) -> float:
    """Ratio shift for this dealer: (logit of its shrunk win rate - logit of the week's) / SLOPE."""
    wins = n = dw = dn = 0.0
    for at, dealer, won in book(state)["seen"]:
        w = 0.5 ** ((state.now - at) / HALF_LIFE)
        wins, n = wins + w * won, n + w
        if dealer == dealer_id:
            dw, dn = dw + w * won, dn + w
    if n < PULL:
        return 0.0
    p_all = min(0.95, max(0.05, wins / n))
    p_dealer = min(0.95, max(0.05, (dw + PULL * p_all) / (dn + PULL)))
    return (math.log(p_dealer / (1 - p_dealer)) - math.log(p_all / (1 - p_all))) / SLOPE
