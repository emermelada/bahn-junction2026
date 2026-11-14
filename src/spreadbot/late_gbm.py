"""P(late) for a car we might win, from 804k won orders of our played weeks (research/mechanics/export_gbm.py).

Held-out-seed AUC 0.897 against 0.737 for policy.OnTime's logistic. The trees are plain JSON; scoring is standard library.
Features are the ones research/mechanics/late_data.py took at the win, rebuilt from what the desk knows at quote time.
"""
from __future__ import annotations

import json
import math
import os
from typing import TYPE_CHECKING

from .geo import DAY

if TYPE_CHECKING:
    from .desk import Desk

_MODEL: dict = {}


def model() -> dict:
    if not _MODEL:
        with open(os.path.join(os.path.dirname(__file__), "late_gbm.json"), encoding="utf-8") as f:
            _MODEL.update(json.load(f))
    return _MODEL


def score(x: list[float]) -> float:
    m = model()
    z = m["base"]
    for node in m["trees"]:
        while len(node) > 1:
            f, thr, miss_left, left, right = node
            v = x[f]
            node = (left if miss_left else right) if v != v else (left if v <= thr else right)
        z += node[0]
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


class LateModel:
    """Supply counts by road minutes are fixed per world (the roster), so they are computed once per place."""

    def __init__(self, desk: "Desk"):
        self.desk = desk
        self._sup: dict[tuple[str, int, bool], int] = {}

    def supply(self, place: str, minutes: int, back: bool = False) -> int:
        """Drivers whose home is within `minutes` of the place (home -> place; back: place -> home)."""
        key = (place, minutes, back)
        if key not in self._sup:
            g = self.desk.geo
            homes = [d["homePlaceId"] for d in self.desk.roster.values()]
            self._sup[key] = sum(1 for h in homes if (g.drive(place, h) if back else g.drive(h, place)) <= minutes)
        return self._sup[key]

    def features(self, r: dict, opt: dict) -> dict[str, float]:
        d, g = self.desk, self.desk.geo
        t = r["respondBy"]
        legs = r["legs"]
        L0 = legs[0]
        p, q = L0["pickup"]["placeId"], L0["delivery"]["placeId"]
        drive = sum(g.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in legs)
        n = d.leg_note(r["id"], 0)
        pw = L0["pickup"]["window"]
        ready = max(pw["from"], n.ready_at or 0)
        deadline = opt["deadline"] if not n.deadline else min(opt["deadline"], n.deadline)
        end = L0["delivery"]["window"]["to"] if L0["delivery"]["privateAddress"] else deadline
        lastp = min(end, deadline) - drive
        dday = deadline // DAY
        roster = max(1, len(d.roster))
        near_open = 0
        for ob in d.orders.values():
            o = ob.order
            if o.get("lastPickupAt", 0) > d.now and not any(o["deliveredAt"]):
                if g.drive(o["legs"][0]["pickup"]["placeId"], p) <= 60:
                    near_open += 1
        car = L0["car"]
        return {
            "drive": drive, "legs": len(legs), "slack": (deadline - max(t, ready) - drive) / 60, "lead_h": (lastp - t) / 60,
            "win_day": t // DAY, "win_hour": (t % DAY) / 60, "due_day": dday, "overnight": float(dday > t // DAY),
            "ready_delay_h": max(0.0, (ready - max(t, pw["from"])) / 60), "pick_private": float(L0["pickup"]["privateAddress"]),
            "deliv_private": float(L0["delivery"]["privateAddress"]), "pick_win_h": (pw["to"] - pw["from"]) / 60,
            "premium": float(any(L["car"]["premium"] for L in legs)), "electric": float(car["electric"]),
            "charge": car.get("chargePercent") or 100, "note": float(r.get("note") is not None), "note_deadline": float(bool(n.deadline)),
            "plates": float(n.plates), "manual": float(n.manual), "pick_hours": float(bool(L0["pickup"]["hours"])),
            "deliv_sat": float(bool((L0["delivery"]["hours"] or {}).get("saturday"))),
            "sup_p30": self.supply(p, 30), "sup_p60": self.supply(p, 60), "sup_p120": self.supply(p, 120),
            "sup_d30": self.supply(q, 30), "sup_d60": self.supply(q, 60), "sup_d120": self.supply(q, 120),
            "back_d30": self.supply(q, 30, True), "back_d60": self.supply(q, 60, True), "roster": roster,
            "typ_over_list": r["referenceFeeCents"] / max(1, opt["listPriceCents"]), "typ": r["referenceFeeCents"] / 100,
            "due_load": d.due_count.get(dday, 0) / roster, "near_open": near_open, "won_so_far": d.won_count,
            "batch": float(r.get("batchId") is not None), "opt_same": float(opt["kind"] == "same_day"), "opt_next": float(opt["kind"] == "next_day"),
        }

    def p_late(self, r: dict, opt: dict) -> float:
        f = self.features(r, opt)
        return score([float(f[k]) for k in model()["features"]])
