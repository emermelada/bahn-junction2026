import unittest

from spreadbot.core.state import State, replay
from spreadbot.driver.dispatch import dispatch

MAP = {"places": [{"id": "a", "name": "A", "lat": 0, "lon": 0}, {"id": "b", "name": "B", "lat": 0, "lon": 1}],
       "roads": [{"from": x, "to": y, "km": 10 if x == y else 100, "minutes": 15 if x == y else 90} for x in "ab" for y in "ab"]}
WINDOW = {"from": 600, "to": 1200}
LEG = {"car": {"premium": False, "electric": False, "chargePercent": None},
       "pickup": {"placeId": "a", "privateAddress": False, "window": WINDOW, "hours": None},
       "delivery": {"placeId": "b", "privateAddress": False, "window": WINDOW, "hours": None}}
REQUEST = {"id": "R1", "dealerId": "d1", "batchId": None, "arrivedAt": 540, "respondBy": 555, "legs": [LEG],
           "options": [{"kind": "same_day", "deadline": 1200, "listPriceCents": 20000}], "referenceFeeCents": 9000, "note": None}
ORDER = {"id": "R1", "dealerId": "d1", "option": "same_day", "priceCents": 20000, "deadline": 1200, "legs": [LEG],
         "status": "waiting", "deliveredAt": [None], "lastPickupAt": 1000}


def week() -> list[dict]:
    """A tiny log: a request, a win, our post, a booking, a drop, a deadline warning, a delivery, money."""
    post = {"type": "post", "stops": [{"orderId": "R1", "leg": 0, "kind": "pickup"}, {"orderId": "R1", "leg": 0, "kind": "delivery"}],
            "audience": {"experienced": False, "manualLicence": False}, "schedule": [{"at": 555, "feeCents": 9000}]}
    return [
        {"t": "now", "now": 540}, {"t": "ev", "e": {"seq": 0, "at": 540, "kind": "price_request", "request": REQUEST}},
        {"t": "now", "now": 555}, {"t": "ev", "e": {"seq": 1, "at": 555, "kind": "order_won", "order": ORDER}},
        {"t": "res", "a": post, "r": {"ok": True, "id": "g1"}},
        {"t": "now", "now": 600}, {"t": "ev", "e": {"seq": 2, "at": 560, "kind": "gig_booked", "gigId": "g1", "driverId": "d9", "feeCents": 9000}},
        {"t": "ev", "e": {"seq": 3, "at": 590, "kind": "gig_dropped", "gigId": "g1", "driverId": "d9"}},
        {"t": "ev", "e": {"seq": 4, "at": 700, "kind": "deadline_close", "orderId": "R1", "lastPickupAt": 880}},
    ]


class StateTest(unittest.TestCase):
    def fresh(self) -> State:
        return replay(week(), State("w", 8, 0, 9000, MAP))

    def test_fold(self):
        s = self.fresh()
        self.assertEqual(s.gigs["g1"]["status"], "open")
        self.assertEqual(s.gig_of[("R1", 0)], "g1")
        self.assertEqual(s.orders["R1"]["lastPickupAt"], 880)
        self.assertIn("R1", s.urgent)

    def test_repeat_events_are_dropped(self):
        s = self.fresh()
        self.assertFalse(s.apply({"seq": 2, "at": 560, "kind": "gig_booked", "gigId": "g1", "driverId": "d9", "feeCents": 9000}))
        self.assertEqual(s.gigs["g1"]["status"], "open")

    def test_replay_gives_same_digest(self):
        self.assertEqual(self.fresh().summary()["digest"], self.fresh().summary()["digest"])

    def test_dispatch_reprices_urgent_open_gig(self):
        s = self.fresh()
        s.now = 710
        actions = dispatch(s, 710)
        self.assertEqual([a["type"] for a in actions], ["reprice"])
        self.assertEqual(actions[0]["schedule"][0]["feeCents"], 13500)  # 1.5 x typical fee

    def test_dispatch_posts_after_failed_visit_with_plates(self):
        s = self.fresh()
        s.apply({"seq": 5, "at": 720, "kind": "visit_failed", "gigId": "g1", "orderId": "R1", "leg": 0, "reason": "no_plates"})
        actions = dispatch(s, 720)
        self.assertEqual(actions[0]["type"], "post")
        self.assertTrue(actions[0]["stops"][0]["withPlates"])

    def test_delivery_finishes_order(self):
        s = self.fresh()
        s.apply({"seq": 5, "at": 900, "kind": "delivered", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "b"})
        s.apply({"seq": 6, "at": 900, "kind": "ledger", "line": {"at": 900, "kind": "revenue", "cents": 20000, "orderId": "R1",
                                                               "gigId": None, "detail": ""}})
        self.assertEqual(s.gigs["g1"]["status"], "done")
        self.assertEqual(list(s.active_orders()), [])
        self.assertEqual(s.margin_cents, 20000)
        self.assertEqual(dispatch(s, 900), [])


if __name__ == "__main__":
    unittest.main()
