"""Builds tests/frank/fixtures/week-dev31.json.gz from a recorded practice week (rc3-check, dev-31, level 8,
on-time 0.955): events up to Wednesday 12:00, the gigs posted by then (with their end-of-week stops and
schedules) and the roster. Run once; the tests read only the fixture.

  python tests/frank/make_fixture.py ../v1-evening/data/runs/rc3-check/dev-31-L8/reveal.json.gz
"""
from __future__ import annotations

import gzip
import json
import os
import sys

CUT = 2 * 1440 + 12 * 60  # Wednesday 12:00


def main(path: str) -> None:
    d = json.load(gzip.open(path, "rt", encoding="utf-8"))
    events = [e for e in d["events"] if e["at"] <= CUT]
    # The desk stores the event's order dict and fills deliveredAt in place, so a saved week carries the
    # end state inside its order_won events. Put back what each event said when it came.
    delivered: dict[tuple[str, int], int] = {}
    for e in events:
        if e["kind"] in ("order_won", "order_changed"):
            o = e["order"]
            o["deliveredAt"] = [delivered.get((o["id"], i)) for i in range(len(o["legs"]))]
            o["status"] = "waiting" if e["kind"] == "order_won" else o["status"]
        elif e["kind"] == "delivered":
            delivered[(e["orderId"], e["leg"])] = e["at"]
    gigs = [g for g in d["gigs"] if g["postedAt"] <= CUT]
    out = os.path.join(os.path.dirname(__file__), "fixtures", "week-dev31.json.gz")
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump({"source": "rc3-check dev-31 L8", "cut": CUT, "events": events, "gigs": gigs, "roster": d["roster"]}, f)
    print(out, len(events), "events", len(gigs), "gigs")


if __name__ == "__main__":
    main(sys.argv[1])
