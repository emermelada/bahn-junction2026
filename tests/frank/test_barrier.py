"""late_barrier: the price of one expected late car (Halal's barrier) and its presets."""
import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")]

from spreadbot.config import Config  # noqa: E402
from spreadbot.policy import barrier_cents  # noqa: E402
from spreadbot.presets import PRESETS  # noqa: E402

B = (0.955, 300, 4, 20)


class TestBarrier(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(Config().late_barrier, ())

    def test_no_orders_no_price(self):
        self.assertEqual(barrier_cents(1.0, 0, B), 0.0)

    def test_on_target_costs_eur(self):
        # 1000 orders at exactly the target share (calm negligible): used ~ 1 -> ~EUR 300 per expected late car
        self.assertAlmostEqual(barrier_cents(0.955, 1000, B) / 100, 300 * (1000 / 1020) ** 4, places=6)

    def test_steep_and_capped(self):
        a, b, c = barrier_cents(0.97, 300, B), barrier_cents(0.94, 300, B), barrier_cents(0.80, 300, B)
        self.assertLess(a, 100 * 100)
        self.assertGreater(b, 3 * a)
        self.assertEqual(c, 300 * 100 * 2 ** 4)  # capped at 2^grip x eur

    def test_presets_parse(self):
        for name in ("k-f1h5f-cap", "k-f1h5f-lb", "k-f1h5f-lbc", "k-safe-dcl-cap", "k-safe-dcl-lb"):
            self.assertIn(name, PRESETS)
        self.assertTrue(any(s.startswith("late_barrier=") for s in PRESETS["k-f1h5f-lb"]))


if __name__ == "__main__":
    unittest.main()
