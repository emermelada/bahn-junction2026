"""Crash test without a world: feed one played week's events (reveal.json.gz) into a fresh Desk with the given flags.
The world never answers our actions, so no gig is ever booked; this checks the handlers, pricing and the planner for
exceptions (ERR lines) and prints what they decided. usage: python -I v2_replay.py <run dir> [k=v ...]"""
import collections
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from spreadbot.config import Config  # noqa: E402
from spreadbot.desk import Desk  # noqa: E402
from spreadbot.geo import Geo  # noqa: E402
from spreadbot.presets import PRESETS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    run = sys.argv[1]
    sets = PRESETS["c3"] + sys.argv[2:]
    cfg = Config.parse(sets)
    geo = Geo(json.load(open(os.path.join(HERE, "..", "..", "data", "map.json"), encoding="utf-8")))
    d = json.load(gzip.open(os.path.join(run, "reveal.json.gz")))
    desk = Desk(geo, cfg, 8, 0, d["roster"])
    events = sorted(d["events"], key=lambda e: (e["at"], e["seq"]))
    last_tick = 0
    for e in events:
        if e["at"] - last_tick >= 15:
            desk.now = e["at"]
            desk.tick()
            last_tick = e["at"]
        desk.now = e["at"]
        desk.handle(e)
    desk.tick()
    codes = collections.Counter(l.split("\t")[1] for l in desk.log if "\t" in l)
    print(f"events {len(events)} log lines {len(desk.log)}: {dict(codes)}")
    for l in desk.log:
        if "\tERR\t" in l:
            print(l)
    n = 0
    for l in desk.log:
        if "\tPLAN\t" in l or "\tV2POST\t" in l:
            n += 1
            if n <= 12 or n % 40 == 0:
                print(l[:220])
    q = [l for l in desk.log if "\tQUOTE\t" in l]
    dec = sum(" DECLINE " in l for l in q)
    print(f"quotes {len(q)} declined {dec}")
    for l in q[:3] + q[len(q) // 2: len(q) // 2 + 3]:
        print(l[:220])


if __name__ == "__main__":
    main()
