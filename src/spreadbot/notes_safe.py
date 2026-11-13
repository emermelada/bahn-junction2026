"""Reads a request's note through notes.read_note; any failure gives the empty reading."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from .notes import LegNote, read_note  # type: ignore
except Exception:  # the reader is optional: the bot runs without it
    @dataclass
    class LegNote:  # type: ignore[no-redef]
        ready_at: Optional[int] = None
        after_payment: bool = False
        pickup_hours: Optional[tuple] = None
        delivery_hours: Optional[tuple] = None
        deadline: Optional[int] = None
        manual: bool = False
        plates: bool = False
        summer_tyres: bool = False
        uncertain: bool = False

    def read_note(request: dict) -> list:  # type: ignore[no-redef]
        return [LegNote() for _ in request["legs"]]


def read_note_safe(request: dict) -> list:
    try:
        out = read_note(request) if request.get("note") else []
        return list(out) + [LegNote() for _ in range(len(request["legs"]) - len(out))]
    except Exception:
        return [LegNote() for _ in request["legs"]]
