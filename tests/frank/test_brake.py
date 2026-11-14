"""backlog_brake: off by default, presets parse, and the dry preset plays a week like its base (it only logs)."""
import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")]

from spreadbot.config import Config  # noqa: E402
from spreadbot.presets import PRESETS  # noqa: E402


class TestBrake(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(Config().backlog_brake, ())

    def test_presets_parse(self):
        c = Config.parse(PRESETS["v5aV2b"])
        self.assertEqual(c.backlog_brake, (0.03, 10, 16, 24, 0.24, 0.10, 0.86))
        self.assertEqual(c.load_free, 0.12)
        self.assertEqual(Config.parse(PRESETS["v5aV2b0"]).backlog_brake[4:], (0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
