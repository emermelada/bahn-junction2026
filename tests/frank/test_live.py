"""Offline tests of the live path (run.py, emulate.py) on a recorded week. No network, no worlds.

  ../v1-evening/.venv/Scripts/python -m unittest discover -s tests/frank -v
  PRESET=best ../v1-evening/.venv/Scripts/python -m unittest discover -s tests/frank     (the desk with a preset)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "harness"), os.path.dirname(__file__)]

import spread  # noqa: E402

import spreadbot.run as run  # noqa: E402
from spreadbot.config import Config  # noqa: E402
from spreadbot.desk import Desk  # noqa: E402
from fakeworld import FakeClient, FakeClock, FakePractice, FakeWorld, legs_of, live_legs, load_map, load_week  # noqa: E402

WEEK = load_week()
GEO = load_map()
TUE_1610 = 1440 + 16 * 60 + 10  # ten minutes after Tuesday's evening release
if os.environ.get("PRESET"):
    from spreadbot.presets import PRESETS
    CFG = Config.parse(PRESETS[os.environ["PRESET"]])
else:
    CFG = Config()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self._time = run.time
        run.time = self.clock  # sleeps and timers in run.py use the fake clock
        self.log = io.StringIO()

    def tearDown(self) -> None:
        run.time = self._time

    def rebuild(self, world: FakeWorld, cfg: Config = CFG) -> tuple[Desk, dict]:
        snap, hist = world.snapshot(), world.events()
        desk = Desk(GEO, cfg, 8, snap["now"], world.roster())
        run.rejoin(desk, snap, hist)
        return desk, snap

    def assert_one_live_gig_per_car(self, world: FakeWorld) -> None:
        seen: dict = {}
        for g in world.snapshot()["gigs"]:
            if g["status"] in ("open", "booked", "working"):
                for s in g["stops"]:
                    if s["kind"] == "pickup":
                        key = (s["orderId"], s["leg"])
                        self.assertNotIn(key, seen, f"car {key} in two live gigs: {seen.get(key)} and {g['id']}")
                        seen[key] = g["id"]

    def quotes(self, world: FakeWorld) -> dict[str, int]:
        n: dict[str, int] = {}
        for a in world.acts:
            if a["type"] == "quote":
                n[a["requestId"]] = n.get(a["requestId"], 0) + 1
        return n


class RejoinTest(Base):
    def test_restarts_never_post_a_car_twice(self):
        for T in (2350, TUE_1610, 2490, 3300):
            with self.subTest(minute=T):
                world = FakeWorld(WEEK, T)
                desk1, snap1 = self.rebuild(world)
                live1 = live_legs(snap1)
                posted = {s["orderId"] for g in snap1["gigs"] for s in g["stops"]}
                self.assertFalse(set(desk1.held) & posted, "a held car is already in a gig")
                run.flush(world, desk1, self.log)
                posts1 = [l for a in world.acts if a["type"] == "post" for l in legs_of(a)]
                self.assertFalse(set(posts1) & set(live1), "posted a car that has a live gig")
                self.assertEqual(len(posts1), len(set(posts1)), "posted a car twice in one rebuild")
                self.assertLessEqual({r["id"] for r in snap1["openRequests"]}, set(self.quotes(world)), "an open request got no quote")
                # A second restart at the same minute (a crash right after the first rebuild).
                n = len(world.acts)
                desk2, snap2 = self.rebuild(world)
                run.flush(world, desk2, self.log)
                again = world.acts[n:]
                withdrawn = {gid for a in again if a["type"] == "withdraw" for gid in [a["gigId"]]}
                freed = {l for g in snap2["gigs"] if g["id"] in withdrawn for l in legs_of(g)}
                posts2 = {l for a in again if a["type"] == "post" for l in legs_of(a)}
                # A car may be posted again only after its live gig was withdrawn (a held car pairing with an
                # open single is the chain planner at work); a car without a gig may be posted.
                self.assertFalse(posts2 & (set(live_legs(snap2)) - freed), "the second rebuild posted a car that already had a gig")
                self.assert_one_live_gig_per_car(world)

    def test_release_pairs_keep_their_timer(self):
        if not CFG.hold:
            self.skipTest("no evening release in this config")
        world = FakeWorld(WEEK, TUE_1610 - 15)  # the first life: before the release
        desk1, _ = self.rebuild(world)
        run.flush(world, desk1, self.log)
        world.now = TUE_1610
        desk1.now = TUE_1610
        desk1.tick()  # the release
        run.flush(world, desk1, self.log)
        pairs = {gid for gid, g in world.own.items() if len({s["orderId"] for s in g["stops"]}) > 1 and g["status"] == "open"}
        self.assertTrue(pairs, "the release posted no pair on this fixture")
        n = len(world.acts)
        run.flush(world, self.rebuild(world)[0], self.log)  # restart: the pairs must stay
        split = {a["gigId"] for a in world.acts[n:] if a["type"] == "withdraw"} & pairs
        self.assertFalse(split, f"a restart split the release pairs {sorted(split)}")
        # Without the timer from settle(), tick would split every open pair at once (the old behaviour).
        old = run.chain_last
        run.chain_last = lambda desk, obs: (_ for _ in ()).throw(RuntimeError("off"))
        try:
            n = len(world.acts)
            run.flush(world, self.rebuild(world)[0], self.log)
            self.assertTrue({a["gigId"] for a in world.acts[n:] if a["type"] == "withdraw"} & pairs)
        finally:
            run.chain_last = old

    def test_replay_runs_each_event_at_its_own_minute(self):
        world = FakeWorld(WEEK, 3300)
        seen = []
        hist = world.events()
        snap = world.snapshot()
        desk = Desk(GEO, CFG, 8, snap["now"], world.roster())
        handle = desk.handle
        desk.handle = lambda e: (seen.append((desk.now, e["at"])), handle(e))
        run.rejoin(desk, snap, hist)
        replayed = seen[: len(hist)]
        self.assertTrue(all(now == at for now, at in replayed))
        self.assertEqual(desk.now, 3300)


class FlushTest(Base):
    def test_a_malformed_action_loses_only_itself(self):
        world = FakeWorld(WEEK, 2350)
        desk = Desk(GEO, CFG, 8, 2350, world.roster())
        q = [{"type": "quote", "requestId": f"Q{i}", "prices": {"same_day": 10000}} for i in range(3)]
        bad = {"type": "reprice", "gigId": "g1", "schedule": [{"at": 2350, "feeCents": 100.5}]}  # a fraction: the client refuses it
        desk.outbox = [q[0], bad, q[1], q[2]]
        run.flush(world, desk, self.log)
        self.assertEqual([a["requestId"] for a in world.acts], ["Q0", "Q1", "Q2"])
        self.assertTrue(any("DROPPED" in x for x in desk.log))
        # The server's 400 that names an action, and one that names none.
        for indexed in (True, False):
            world = FakeWorld(WEEK, 2350)
            world.reject, world.reject_indexed = (lambda a: a["type"] == "offer"), indexed
            desk.outbox = [q[0], {"type": "offer", "gigId": "g1", "driverId": "d", "feeCents": 5000}, q[1]]
            run.flush(world, desk, self.log)
            self.assertEqual([a["type"] for a in world.acts], ["quote", "quote"], f"indexed={indexed}")

    def test_more_than_fifty_actions_go_in_batches_quotes_first(self):
        world = FakeWorld(WEEK, 2350)
        desk = Desk(GEO, CFG, 8, 2350, world.roster())
        desk.outbox = [{"type": "withdraw", "gigId": f"nope{i}"} for i in range(60)] + [{"type": "quote", "requestId": "Q", "prices": {}}]
        run.flush(world, desk, self.log)
        self.assertEqual(world.calls, [50, 11])
        self.assertEqual(world.acts[0]["type"], "quote")


class LiveLoopTest(Base):
    def live(self, world: FakeWorld) -> None:
        run.supervise(world, FakeClient(world), GEO, CFG, self.log, lambda: world.now)

    def requests_between(self, a: int, b: int) -> set:
        return {e["request"]["id"] for e in WEEK["events"] if e["kind"] == "price_request" and a < e["at"] <= b}

    def test_a_quietly_dead_stream_is_noticed(self):
        world = FakeWorld(WEEK, 2350, ends=2700, clock=self.clock)
        world.dead_after = 30  # each connection dies quietly after 30 events
        self.live(world)
        self.assertGreater(world.streams, 2, "never reconnected")
        n = self.quotes(world)
        missing = self.requests_between(2350, 2700) - set(n)
        self.assertFalse(missing, f"{len(missing)} requests never quoted")
        self.assertTrue(all(v == 1 for v in n.values()), "a request was quoted twice")

    def test_repeated_events_are_dropped(self):
        world = FakeWorld(WEEK, 2350, ends=2600, clock=self.clock)
        world.dup = True
        self.live(world)
        n = self.quotes(world)
        self.assertLessEqual(self.requests_between(2350, 2600), set(n))
        self.assertTrue(all(v == 1 for v in n.values()), "a repeated event was handled twice")

    def test_breaks_everywhere_end_in_one_gig_per_car(self):
        world = FakeWorld(WEEK, 2350, ends=2800, clock=self.clock)
        U = lambda: spread.Unreachable(0, "Cannot reach https://spread.bahnexpress.com: [Errno 11001] getaddrinfo failed")  # noqa: E731
        world.fail = {"events": [U()], "snapshot": [U(), spread.SpreadError(500, "boom")], "act": [U()], "stream": [U()], "roster": [U()]}
        self.live(world)
        self.assertIn(5, self.clock.slept)
        self.assertLessEqual(self.requests_between(2350, 2800), set(self.quotes(world)))
        self.assert_one_live_gig_per_car(world)

    def test_a_bug_in_one_handler_does_not_stop_the_loop(self):
        world = FakeWorld(WEEK, 2350, ends=2600, clock=self.clock)
        orig = Desk.on_order_won
        Desk.on_order_won = lambda self, e: (_ for _ in ()).throw(KeyError("boom")) if e["order"]["id"] == "R00400" else orig(self, e)
        try:
            self.live(world)
        finally:
            Desk.on_order_won = orig
        self.assertLessEqual(self.requests_between(2350, 2600), set(self.quotes(world)))

    def test_world_already_ended(self):
        world = FakeWorld(WEEK, 3000, ends=3000, clock=self.clock)
        self.assertTrue(run.run_live(world, FakeClient(world), GEO, CFG, self.log, lambda: world.now))
        self.assertEqual(world.acts, [])


class RetryTest(Base):
    def test_patient_backs_off_and_gives_up_on_real_errors(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise spread.Unreachable(0, "getaddrinfo failed")
            return "ok"
        self.assertEqual(run.patient(flaky), "ok")
        self.assertEqual(self.clock.slept, [5.0, 10.0])
        with self.assertRaises(spread.SpreadError):
            run.patient(lambda: (_ for _ in ()).throw(spread.SpreadError(400, "bad")))
        self.assertEqual(len(self.clock.slept), 2)

    def practice(self, world: FakePractice, tmp: str) -> int:
        args = argparse.Namespace(set=None, level=8, board=False, seed="fx", tag="t", quiet=True, save_events=False, reveal=False)
        old = (spread.Client, run.load_geo, os.getcwd())
        spread.Client, run.load_geo = (lambda: FakeClient(world)), (lambda client: GEO)
        os.chdir(tmp)
        try:
            return run.practice(args)
        finally:
            spread.Client, run.load_geo = old[0], old[1]
            os.chdir(old[2])

    def test_practice_survives_a_lost_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = FakePractice(WEEK, 0, ends=2 * 1440 + 12 * 60, clock=self.clock)
            world.lose = {40}  # the 40th advance happens, but its answer is lost (DNS)
            self.assertEqual(self.practice(world, tmp), 0)
            self.assertFalse(world.deleted)
            with open(os.path.join(tmp, "data", "runs", "t", "fx-L8", "summary.json")) as f:
                s = json.load(f)
            self.assertEqual(s["rebuilds"], 1)
            self.assertIn(5.0, self.clock.slept)
            self.assert_one_live_gig_per_car(world)

    def test_practice_still_deletes_on_a_real_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = FakePractice(WEEK, 0, ends=2 * 1440, clock=self.clock)
            world.fail = {"advance": [spread.SpreadError(400, "bad body", "[0].prices")]}
            self.assertEqual(self.practice(world, tmp), 1)
            self.assertTrue(world.deleted)

    def test_emulator_ticker_survives_breaks(self):
        import emulate
        old = emulate.time
        emulate.time = self.clock
        try:
            world = FakePractice(WEEK, 1000, ends=1600, clock=self.clock)
            world.lose = {3}
            world.fail = {"advance": [spread.Unreachable(0, "getaddrinfo failed")], "snapshot": [spread.Unreachable(0, "x")]}
            t = emulate.Ticker(world, 0)
            t.run()
            self.assertIsNone(t.error)
            self.assertEqual(t.now, 1600)
        finally:
            emulate.time = old



class ScarcityTest(Base):
    def test_the_switch_flips_at_the_same_hour_after_any_restart(self):
        from spreadbot.presets import PRESETS
        cfg = Config.parse(PRESETS["v5q2V"])
        flips = set()
        for T in (2350, 3300, 4300, 6000):
            with self.subTest(minute=T):
                desk, _ = self.rebuild(FakeWorld(WEEK, T), cfg)
                if T < cfg.scarcity_from:
                    self.assertFalse(desk.scarce)
                    self.assertEqual(desk.cfg.load_free, cfg.load_free)
                    continue
                lines = [l.split("	")[2].split(":")[0] for l in desk.log if "	SCARCE	" in l]
                self.assertEqual(len(lines), 1 if desk.scarce else 0)
                flips.add((desk.scarce, tuple(lines)))
                if desk.scarce:  # the switched config is the one price() and due_load() read
                    self.assertEqual((desk.cfg.load_free, desk.cfg.load_slope, desk.cfg.load_bundle_w), (0.07, 1.0, 1.0))
                    self.assertIs(desk.market.cfg, desk.cfg)
        self.assertEqual(len(flips), 1, f"restarts disagree on the flip: {flips}")


if __name__ == "__main__":
    unittest.main()
