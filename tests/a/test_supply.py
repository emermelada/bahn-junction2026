"""Supply (V2 capacity): every place has a region, hours are >= 0 and deterministic, a replay gives the same numbers,
and the flu / snow / weekend parts act as documented. Run: PYTHONPATH=src python -m pytest tests/a/test_supply.py"""
import json
import os

from spreadbot import supply as S
from spreadbot.config import Config
from spreadbot.geo import DAY, Geo

MAP = os.path.join(os.path.dirname(__file__), "..", "..", "data", "map.json")


class Rec:
    def __init__(self, gid, oid, posted, fee):
        self.id, self.stops, self.posted_at, self.schedule = gid, [{"orderId": oid, "leg": 0, "kind": "pickup"}], posted, [{"at": posted, "feeCents": fee}]


class FakeDesk:
    def __init__(self):
        self.geo = Geo(json.load(open(MAP, encoding="utf-8"))) if os.path.exists(MAP) else None
        self.roster = {f"d{i}": {"id": f"d{i}", "homePlaceId": p} for i, p in enumerate(["vantaa"] * 40 + ["oulu"] * 6 + ["pori"])}
        self.requests = {"R1": {"legs": [{"pickup": {"placeId": "oulu"}}]}, "R2": {"legs": [{"pickup": {"placeId": "helsinki"}}]}, "R3": {"legs": [{"pickup": {"placeId": "tampere"}}]}}
        self.gigs = {"g1": Rec("g1", "R1", 600, 5000), "g2": Rec("g2", "R2", 600, 5000), "g3": Rec("g3", "R3", 600, 5000)}
        self.orders, self.now, self.cfg = {}, 0, Config()


EVENTS = [
    {"kind": "forecast", "at": 0, "from": 1 * DAY, "to": 2 * DAY, "placeIds": ["oulu"]},
    {"kind": "gig_booked", "at": 900, "gigId": "g1", "driverId": "d40", "feeCents": 5000},  # slow: 300 min
    {"kind": "gig_booked", "at": 620, "gigId": "g2", "driverId": "d0", "feeCents": 5000},   # fast
    {"kind": "gig_viewed", "at": 610, "gigId": "g2", "driverId": "d1"},
] + [{"kind": "gig_dropped", "at": 2 * DAY + 6 * 60 + i, "gigId": "g3", "driverId": "d0"} for i in range(S.FLU_DROPS)]


def build():
    s = S.Supply(FakeDesk())
    for e in EVENTS:
        s.on_event(e)
    return s


def test_every_place_has_a_region():
    if not os.path.exists(MAP):
        return
    s = S.Supply(FakeDesk())
    assert all(s.region(p) in s.regions() for p in s.desk.geo.ids)
    assert set(S.REGION) == set(s.desk.geo.ids)


def test_hours_nonnegative_and_deterministic():
    a, b = build(), build()
    for rg in a.regions():
        for d in range(9):
            assert a.hours(rg, d) >= 0
            assert a.hours(rg, d) == b.hours(rg, d)  # same events, same numbers (a replay after a restart)


def test_weekend_flu_snow():
    s = build()
    assert s.hours("cap", 6) == 0.0                           # Sunday: every site closed
    assert 0 < s.hours("cap", 5) < s.hours("cap", 1)          # Saturday: short site hours
    assert s.hours("cap", 7) == s.hours("cap", 1)             # Mon2 is a full working day
    assert abs(s.hours("cap", 2) / s.hours("cap", 3) - S.FLU_CUT) < 1e-9  # the flu day
    assert abs(s.hours("oulu", 1) / s.hours("oulu", 3) - S.SNOW) < 1e-9   # snow in Oulu on Tuesday


def test_learned_moves_hours_within_bounds():
    s = build()
    assert s.learned("oulu") < s.learned("cap") <= S.LEARN_MAX  # Oulu's gig sat, the capital's went at once
    assert s.learned("tre") < s.learned("cap")                  # Tampere's bookings were dropped
    assert s.learned("oulu") >= S.LEARN_MIN


def test_roster_scales_base():
    s = S.Supply(FakeDesk())
    d2 = FakeDesk(); d2.roster = {f"d{i}": {"id": f"d{i}", "homePlaceId": "vantaa"} for i in range(400)}
    assert S.Supply(d2).base["cap"] > s.base["cap"]
