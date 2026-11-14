"""This week's competitor price level, learned from our own wins and losses (HANDBOOK: the world's price
level runs from 26% to 54% above list at level 8; a system that measures the market in the first hours and
adapts keeps its margin).

One number: the offset d in P(win) = sigmoid(A0 + d - SLOPE x ratio), fitted on this week's quotes with old
quotes fading and a pull towards d = 0 while data is thin. d / SLOPE is how much higher a ratio wins as often
as it would in an average week, so the quote moves by that much: up in a dear week, down in a cheap one."""
from __future__ import annotations

import math

from spread.types import DeskEvent

from spreadbot.core.state import State

SLOPE = 8.0  # the price ladder: win 85% at 1.1x list, 10% at 1.6x, inside one week
A0 = SLOPE * 1.42  # over 443 level 8 weeks, half our quotes win at 1.42x list (lab/a/lane_table.py)
PULL = 40.0  # quotes needed before the week's own data outweighs the average week
HALF_LIFE = 720  # world minutes; the price war lasts one day, so a day-old quote counts half


def book(state: State) -> dict:
    return state.ext.setdefault("dealer", {}).setdefault("week", {"quoted": {}, "seen": [], "at": None, "d": 0.0})


def record(state: State, request_id: str, ratio: float) -> None:
    book(state)["quoted"][request_id] = ratio


def observe(event: DeskEvent, state: State) -> None:
    if event["kind"] not in ("order_won", "order_lost"):
        return
    b = book(state)
    rid = event["order"]["id"] if event["kind"] == "order_won" else event["requestId"]
    ratio = b["quoted"].pop(rid, None)
    if ratio is not None:
        b["seen"].append((event["at"], ratio, event["kind"] == "order_won"))
        b["at"] = None  # refit on the next quote


def shift(state: State) -> float:
    """How much the ratio should move this week, in ratio units. Refitted at most once per world minute."""
    b = book(state)
    if b["at"] == state.now:
        return b["d"] / SLOPE
    d = b["d"]
    for _ in range(6):  # Newton steps on d, with the pull as a Gaussian prior (4 = 1 / max p(1-p))
        g, h = -d * 4 / PULL, 4 / PULL
        for at, r, y in b["seen"]:
            w = 0.5 ** ((state.now - at) / HALF_LIFE)
            p = 1 / (1 + math.exp(-(A0 + d - SLOPE * r)))
            g += w * (y - p)
            h += w * p * (1 - p)
        d += g / h
    b["at"], b["d"] = state.now, d
    return d / SLOPE
