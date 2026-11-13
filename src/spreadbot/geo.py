"""The map: places, road minutes and km, straight-line km. Loaded once from the API (free) or a cache."""
from __future__ import annotations

import json
import math
import os
from typing import Any

HOUR = 60
DAY = 24 * HOUR


class Geo:
    def __init__(self, world_map: dict[str, Any]):
        self.places = {p["id"]: p for p in world_map["places"]}
        self.ids = sorted(self.places)
        self.minutes: dict[tuple[str, str], int] = {}
        self.road_km: dict[tuple[str, str], float] = {}
        for r in world_map["roads"]:
            self.minutes[(r["from"], r["to"])] = r["minutes"]
            self.road_km[(r["from"], r["to"])] = r["km"]
        self._air: dict[tuple[str, str], float] = {}
        for a in self.ids:
            for b in self.ids:
                self._air[(a, b)] = _haversine(self.places[a], self.places[b])

    def air(self, a: str, b: str) -> float:
        return self._air.get((a, b), 999.0)

    def drive(self, a: str, b: str) -> int:
        return self.minutes.get((a, b), 600)

    def km(self, a: str, b: str) -> float:
        return self.road_km.get((a, b), 600.0)

    def near(self, a: str, radius_km: float) -> list[str]:
        return [b for b in self.ids if self.air(a, b) <= radius_km]


def _haversine(p: dict, q: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (p["lat"], p["lon"], q["lat"], q["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def load_geo(client: Any, cache: str = "data/map.json") -> Geo:
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return Geo(json.load(f))
    world_map = client.map()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(world_map, f)
    return Geo(world_map)


def day_of(t: int) -> int:
    return t // DAY


def minute_of_day(t: int) -> int:
    return t % DAY


def is_open(hours: dict | None, t: int) -> bool:
    """Whether a site with these (stated) hours is open at world minute t. None = private address: always."""
    if hours is None:
        return True
    d, m = (t // DAY) % 7, t % DAY
    if d in hours["weekdays"]:
        return hours["opens"] <= m < hours["closes"]
    if d == 5 and hours.get("saturday"):
        s = hours["saturday"]
        return s["opens"] <= m < s["closes"]
    return False


def open_intervals(hours: dict | None, start: int, end: int) -> list[tuple[int, int]]:
    """Open intervals of a site between start and end (world minutes)."""
    if end <= start:
        return []
    if hours is None:
        return [(start, end)]
    out = []
    for d in range(start // DAY, end // DAY + 1):
        wd = d % 7
        if wd in hours["weekdays"]:
            o, c = hours["opens"], hours["closes"]
        elif wd == 5 and hours.get("saturday"):
            o, c = hours["saturday"]["opens"], hours["saturday"]["closes"]
        else:
            continue
        a, b = max(start, d * DAY + o), min(end, d * DAY + c)
        if a < b:
            out.append((a, b))
    return out
