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
