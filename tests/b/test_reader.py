import unittest

from spreadbot.notes.reader import needs_manual, needs_plates, window_from_note


def note(text):
    return {"text": text, "language": "fi"}


class ReaderTest(unittest.TestCase):
    def test_plates(self):
        self.assertTrue(needs_plates(note("Kilvet puuttuu, tuo siirtokilvet")))
        self.assertTrue(needs_plates(note("Unregistered, needs trade plates")))
        self.assertFalse(needs_plates(note("Huoltokirja ja rekisteriote autossa.")))

    def test_manual(self):
        self.assertTrue(needs_manual(note("Manuaali, ei automaatti.")))
        self.assertTrue(needs_manual(note("Käsivaihteinen.")))
        self.assertFalse(needs_manual(note("Hi. Automatic, not a manual.")))
        self.assertFalse(needs_manual(None))

    def test_delivery_closing_time(self):
        w = window_from_note(note("Vastaanotto klo 16 asti, toimitus ennen klo 16"), {"from": 1980, "to": 2400}, "delivery")
        self.assertEqual(w["to"], 1440 + 16 * 60)


if __name__ == "__main__":
    unittest.main()


class BundleTest(unittest.TestCase):
    def test_return_leg_pairs_into_one_gig(self):
        from spreadbot.core.state import State
        from spreadbot.driver import dispatch as d
        from tests.a.test_state import LEG, MAP, ORDER, REQUEST
        s = State("w", 8, 600, 9000, MAP)
        back = {**LEG, "pickup": {**LEG["delivery"]}, "delivery": {**LEG["pickup"]}}
        for oid, leg in (("R1", LEG), ("R2", back)):
            s.requests[oid] = {**REQUEST, "id": oid, "legs": [leg], "respondBy": 590}
            s.orders[oid] = {**ORDER, "id": oid, "legs": [leg], "deadline": 2400, "lastPickupAt": 2000, "deliveredAt": [None]}
        old = dict(d.FLAGS)
        try:
            d.FLAGS.update(bundle=True, read_notes=False)
            actions = d.dispatch(s, 600)
        finally:
            d.FLAGS.clear()
            d.FLAGS.update(old)
        self.assertEqual(len(actions), 1)
        self.assertEqual([st["orderId"] for st in actions[0]["stops"]], ["R1", "R1", "R2", "R2"])
