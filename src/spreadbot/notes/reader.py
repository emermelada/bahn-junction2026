"""Notes reader v1: rules only, no network. Reads a dealer note in Finnish, Swedish or English into what
dispatch needs: narrower pickup and delivery windows, transfer plates, a manual licence.

Windows: the kit starter's keyword reader (spread/starter.py, window_from_note), kept as is: clock times
near "before/after/by" words and opening-hour ranges. Plates and manual gearbox: keyword lists written from
data/notes_corpus.jsonl. When unsure, the cautious reading: asking for plates or a manual licence costs a
little audience or 30 minutes; missing them costs a failed visit (at least €25) and a late car."""
from __future__ import annotations

import re
from typing import Optional

from spread.types import Note, TimeWindow

HOUR, DAY = 60, 24 * 60

PLATES = re.compile(r"plates|kilv|kilpi|rekkari|rekister(?!iote)|skylt|unregistered|avregistrer", re.IGNORECASE)
MANUAL = re.compile(r"manua|maanua|manuell|stick shift|käsivaih|manuell växel", re.IGNORECASE)
NOT_MANUAL = re.compile(r"(\bei|\bnot( a)?|\binte|\bno)\s+manu", re.IGNORECASE)


def needs_plates(note: Optional[Note]) -> bool:
    return bool(note and PLATES.search(note["text"]))


def needs_manual(note: Optional[Note]) -> bool:
    """A manual gearbox: "Manuaali, ei automaatti" is manual, "Automatic, not a manual" is not."""
    return bool(note and MANUAL.search(note["text"]) and not NOT_MANUAL.search(note["text"]))


# --- windows: the kit starter's reader -----------------------------------------------------------------------
AFTER = re.compile(r"jälkeen|alkaen|aikaisintaan|\bafter\b|\bfrom\b|earliest|not before|ei ennen|valmis|\bready\b|efter|tidigast|inte före|klar", re.ASCII)
BEFORE = re.compile(r"ennen|mennessä|viim|\bbefore\b|\bby\b|latest|före|senast", re.ASCII)
DELIVERY = re.compile(r"toimit|perillä|perille|vastaanot|kohde|deliver|arrive|destination|receiv|leverera|leverans|framme|mottag", re.ASCII)
CLOCK = re.compile(r"(?:klo|kl\.?)\s*(\d{1,2})(?:[.:](\d{2}))?|\b(\d{1,2})[.:](\d{2})\b", re.ASCII)
RANGE = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?\b", re.ASCII)


def window_from_note(note: Optional[Note], window: TimeWindow, stop: str) -> TimeWindow:
    """Narrows a stop's window by clock times in the note, found by keywords. The time is on the window's own day."""
    if not note:
        return window
    text = note["text"].lower()
    if bool(DELIVERY.search(text)) != (stop == "delivery"):
        return window

    def minutes(hour: int, minute: int) -> Optional[int]:
        return None if hour > 24 or minute > 59 else hour * HOUR + minute

    start, end = window["from"], window["to"]
    for match in RANGE.finditer(text):  # opening hours hold every day
        opens, closes = minutes(int(match[1]), int(match[2] or 0)), minutes(int(match[3]), int(match[4] or 0))
        if opens is None or closes is None or opens >= closes:
            continue
        start = max(start, start // DAY * DAY + opens)
        end = min(end, end // DAY * DAY + closes)
    text = RANGE.sub(" ", text)
    for match in CLOCK.finditer(text):
        m = minutes(int(match[1] or match[3]), int(match[2] or match[4] or 0))
        if m is None:
            continue
        time = window["from"] // DAY * DAY + m
        around = text[max(0, match.start() - 16): match.end() + 16]
        if AFTER.search(around):
            start = max(start, time)
        elif BEFORE.search(around):
            end = min(end, time)
    return {"from": start, "to": end} if start <= end else window
