"""bundle_climb: off by default; presets parse; the pair schedule opens low and climbs back to the usual opening."""
import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")]

from spreadbot.config import Config  # noqa: E402
from spreadbot.presets import PRESETS  # noqa: E402


class TestClimb(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(Config().bundle_climb, ())

    def test_presets_parse(self):
        c = Config.parse(PRESETS["v5La-pc1"])
        self.assertEqual(c.bundle_climb, ((0, 0.68), (25, 0.74), (50, 0.80)))
        self.assertEqual(c.late_barrier, (0.955, 300, 4, 20))
        self.assertEqual(len(Config.parse(PRESETS["v5La-pc2"]).bundle_climb), 4)


if __name__ == "__main__":
    unittest.main()


class TestClimbLive(unittest.TestCase):
    def test_release_pair_opens_low_and_climbs(self):
        import io
        import test_live as tl  # the fake world and its fixture week
        cfg = Config.parse(PRESETS["v5La-pc1"])
        if not cfg.hold:
            self.skipTest("no evening release in this config")
        clock, old_time = tl.FakeClock(), tl.run.time
        tl.run.time = clock
        try:
            world = tl.FakeWorld(tl.WEEK, tl.TUE_1610 - 15)
            snap, hist = world.snapshot(), world.events()
            desk = tl.Desk(tl.GEO, cfg, 8, snap["now"], world.roster())
            tl.run.rejoin(desk, snap, hist)
            log = io.StringIO()
            tl.run.flush(world, desk, log)
            world.now = desk.now = tl.TUE_1610
            desk.tick()
            tl.run.flush(world, desk, log)
        finally:
            tl.run.time = old_time
        pairs = [g for g in world.own.values() if len({s["orderId"] for s in g["stops"]}) > 1]
        self.assertTrue(pairs, "the release posted no pair on this fixture")
        climbed = [g for g in pairs if len(g["schedule"]) > 1 and g["schedule"][1]["at"] - g["schedule"][0]["at"] == 25]
        self.assertTrue(climbed, "no pair got the climbing schedule")
        for g in climbed:
            fees = [s["feeCents"] for s in g["schedule"]]
            self.assertEqual(fees, sorted(fees))  # only ever climbs
            self.assertLess(fees[0], fees[3])  # opens under the usual opening, reached at +75 min


class TestClimbAdapt(unittest.TestCase):
    def _desk(self, cfg):
        from spreadbot.desk import Desk
        d = Desk.__new__(Desk)  # only the climb_adapt books: no geo or roster needed
        d.cfg, d.now, d.log = cfg, 0, []
        d.ca_pairs, d.ca_booked, d.ca_dropped, d.ca_skip = {}, {}, set(), False
        return d

    def test_off_by_default_and_preset(self):
        self.assertEqual(Config().climb_adapt, ())
        self.assertEqual(Config.parse(PRESETS["v6pa"]).climb_adapt, (10, 0.5, 0.22, 0.67))

    def test_slow_rung0_triggers_sticky(self):
        d = self._desk(Config.parse(PRESETS["v6pa"]))
        for i in range(9):  # pairs posted at 0; none book on rung 0, some on rung 1
            d.ca_pairs[f"g{i}"] = 0
        d.now = 60
        for i in range(4):
            d.ca_booked[f"g{i}"] = 30
        d.ca_check()
        self.assertFalse(d.ca_skip)  # 9 < 10 pairs: still learning
        d.ca_pairs["g9"] = 0
        d.ca_check()
        self.assertTrue(d.ca_skip)  # h0 = 0 < 0.5 x h1
        self.assertIn("CLIMB_ADAPT", d.log[-1])
        d.ca_booked.clear()
        d.ca_check()
        self.assertTrue(d.ca_skip)  # sticky
