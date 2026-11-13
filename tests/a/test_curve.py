import math
import random
import unittest

from spreadbot.core.curve import Curve, pav

GRID = [1.0 + 0.05 * k for k in range(15)]  # 1.0 .. 1.7


def truth(ratio: float, middle: float = 1.35) -> float:
    return 1 / (1 + math.exp((ratio - middle) * 20))


class CurveTest(unittest.TestCase):
    def test_prior_without_data(self):
        c = Curve(GRID, prior=lambda r: 0.5)
        self.assertAlmostEqual(c.p(1.2), 0.5)

    def test_monotone_and_recovers_truth(self):
        c, r = Curve(GRID, prior=lambda r: 0.5), random.Random(1)
        for t in range(3000):
            x = r.uniform(1.0, 1.7)
            c.observe(x, r.random() < truth(x), t)
        values = [c.p(x) for x in GRID]
        self.assertEqual(values, sorted(values, reverse=True))
        for x in (1.1, 1.35, 1.6):
            self.assertAlmostEqual(c.p(x), truth(x), delta=0.08)

    def test_increasing(self):
        c, r = Curve(GRID, prior=lambda r: 0.5, decreasing=False), random.Random(2)
        for t in range(2000):
            x = r.uniform(1.0, 1.7)
            c.observe(x, r.random() < 1 - truth(x), t)
        values = [c.p(x) for x in GRID]
        self.assertEqual(values, sorted(values))

    def test_fading_follows_a_shift(self):
        c, r = Curve(GRID, prior=lambda r: 0.5, half_life=120), random.Random(3)
        for t in range(2000):  # old regime: middle at 1.5
            x = r.uniform(1.0, 1.7)
            c.observe(x, r.random() < truth(x, 1.5), t)
        for t in range(2000, 2600):  # price war: middle drops to 1.15
            x = r.uniform(1.0, 1.7)
            c.observe(x, r.random() < truth(x, 1.15), t)
        self.assertLess(c.p(1.35, now=2600), 0.25)

    def test_out_of_order_observation_is_faded(self):
        c = Curve(GRID, prior=lambda r: 0.5, half_life=60)
        c.observe(1.2, True, 600)
        c.observe(1.2, True, 0)  # ten half-lives old
        self.assertAlmostEqual(c.samples(), 1.0, delta=0.01)

    def test_pav(self):
        self.assertEqual(pav([1, 3, 2, 4], [1, 1, 1, 1]), [1, 2.5, 2.5, 4])


if __name__ == "__main__":
    unittest.main()
