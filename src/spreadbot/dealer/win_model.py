"""The dealer win model: the chance a dealer takes our price, as a function of price / (list x trust),
learned live from our own wins and losses with the shared acceptance curve.

The prior is the price ladder of two level 8 weeks (docs/log a-20261114-0010): about 80% wins up to 1.1x
list, 50% at 1.25x, 35-40% at 1.3-1.4x, 20% at 1.5x, 10% at 1.6x. Each week then moves it: competitor
level (26-54% above list), its day factors, the price war and the outage all show up as wins and losses."""
from __future__ import annotations

import math

from spread.types import DeskEvent

from spreadbot.core.curve import Curve
from spreadbot.core.state import State

GRID = [1.0 + 0.05 * k for k in range(15)]  # 1.0 .. 1.7, the range the ladder covered
HALF_LIFE = 240  # world minutes; the price war lasts 10 hours, so the curve must turn within a few hours
STRENGTH = 3.0  # prior weight per grid point, in observations


def prior(ratio: float) -> float:
    """A logistic close to the ladder's points: 0.79 at 1.0x, 0.47 at 1.3x, 0.31 at 1.4x, 0.17 at 1.5x, 0.09 at 1.6x."""
    return 0.85 / (1 + math.exp((ratio - 1.33) * 8))


def curve(state: State) -> Curve:
    dealer = state.ext.setdefault("dealer", {})
    if "curve" not in dealer:
        dealer["curve"] = Curve(GRID, prior, strength=STRENGTH, half_life=HALF_LIFE, decreasing=True)
        dealer["quoted"] = {}  # request id -> the ratio we quoted
    return dealer["curve"]


def record_quote(state: State, request_id: str, ratio: float) -> None:
    curve(state)
    state.ext["dealer"]["quoted"][request_id] = ratio


def observe(event: DeskEvent, state: State) -> None:
    """Feeds wins and losses of our quotes into the curve."""
    if event["kind"] not in ("order_won", "order_lost"):
        return
    request_id = event["order"]["id"] if event["kind"] == "order_won" else event["requestId"]
    ratio = state.ext.get("dealer", {}).get("quoted", {}).pop(request_id, None)
    if ratio is not None:
        curve(state).observe(ratio, event["kind"] == "order_won", event["at"])
