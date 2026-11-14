"""Risk (V2): P(late) in (0, 1), deterministic, and moves the way the fit says (trade-in, Friday load, a planned pickup on
the deadline day, chains). Run: PYTHONPATH=src python -m pytest tests/a/test_risk.py (or call the test_ functions)."""
import json
import os

from spreadbot.config import Config
from spreadbot.desk import Desk
from spreadbot.geo import DAY, Geo
from spreadbot.risk import Risk

MAP = os.path.join(os.path.dirname(__file__), "..", "..", "data", "map.json")


def leg(p, d, premium=False):
    return {"car": {"premium": premium, "electric": False, "chargePercent": None},
            "pickup": {"placeId": p, "privateAddress": False, "window": {"from": 600, "to": 2000}},
            "delivery": {"placeId": d, "privateAddress": False, "window": {"from": 600, "to": 2000}}}


def request(rid, legs, deadline):
    return {"id": rid, "dealerId": "D01", "respondBy": 615, "legs": legs, "note": None,
            "options": [{"kind": "same_day", "deadline": deadline, "listPriceCents": 10000}]}


def desk():
    roster = [{"id": f"d{i}", "homePlaceId": "vantaa" if i % 2 else "tampere"} for i in range(400)]
    d = Desk(Geo(json.load(open(MAP, encoding="utf-8"))), Config(), 8, 600, roster)
    return d


def test_range_and_determinism():
    d = desk(); r = request("R1", [leg("vantaa", "espoo")], 1080)
    d.requests["R1"] = r
    a, b = Risk(d).p_late(r, "same_day", 0), Risk(d).p_late(r, "same_day", 0)
    assert 0.0 < a < 1.0 and a == b


def test_directions():
    d = desk(); rk = Risk(d)
    short = request("R1", [leg("vantaa", "espoo")], 1080)
    trade = request("R2", [leg("vantaa", "tampere"), leg("tampere", "vantaa")], 2 * DAY + 1080)
    far = request("R3", [leg("vantaa", "oulu")], 2 * DAY + 1080)
    for r in (short, trade, far):
        d.requests[r["id"]] = r
    assert rk.p_late(trade, "same_day", 1) > rk.p_late(far, "same_day", 1)    # a trade-in is the riskiest car (46% late)
    assert rk.p_late(far, "same_day", 2) > rk.p_late(far, "same_day", 1)      # pickup on the deadline day, shorter lead
    assert rk.p_late(far, "same_day", 1, 2) > rk.p_late(far, "same_day", 1)   # in a chain
    assert rk.p_late(far, "same_day", 1) > rk.p_late(short, "same_day", 0)


def test_load_raises_risk():
    d = desk(); r = request("R1", [leg("vantaa", "espoo")], 4 * DAY + 1080)
    d.requests["R1"] = r
    before = Risk(d).p_late(r, "same_day", 3)
    from spreadbot.desk import OrderBook
    for i in range(60):  # 60 cars already due Friday: load 0.15 of 400 drivers
        o = {"id": f"W{i}", "dealerId": "D01", "option": "same_day", "deadline": 4 * DAY + 1080, "legs": [leg("vantaa", "espoo")],
             "deliveredAt": [None], "status": "won", "lastPickupAt": 4 * DAY + 1000}
        d.orders[o["id"]] = OrderBook(o, 600)
    d.now += 1  # new minute: the cache refreshes
    assert Risk(d).p_late(r, "same_day", 3) > before
