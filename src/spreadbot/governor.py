"""On-time governor, v0 stub: always normal. B4 replaces it."""
from __future__ import annotations

from spreadbot.core.state import State


def risk_mode(state: State, now: int) -> str:
    return "normal"
