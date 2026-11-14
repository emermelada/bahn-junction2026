"""Replay played weeks through Demand (src/spreadbot/demand.py) and score its forecast of the cars we still win.
At 08:00, 12:00 and 16:00 of Mon-Fri: predicted future won cars per (region, deadline day) from requests not yet arrived,
against the cars the run did win from them; also requests still to arrive per (region, arrival day). Compared with the
planner's old _future() rule (21 requests/h x region share x this week's win share, half on the arrival day, half next).
The tables are fitted on these same request streams (57 weeks): this is a check of the module's code and of the win part
on other policies; the leave-one-seed-out numbers are in research/sessionA/scripts/a5_demand_check.py / a5_wins_check.py.
usage: PYTHONPATH=src python -I lab/a/demand_check.py <sweep dir> [...]   (dirs of <seed>-L8/reveal.json.gz)"""
import collections
import glob
import gzip
import json
import os
import statistics as st
import sys

from spreadbot import demand as D

DAY = 1440
CHECK = (8 * 60, 12 * 60, 16 * 60)


class FakeDesk:
    supply = None


def main() -> None:
    regs = sorted(set(D.REGION.values()))
    err = collections.defaultdict(list)
    tot = []
    for sweep in sys.argv[1:]:
        for p in sorted(glob.glob(os.path.join(sweep, "*-L8", "reveal.json.gz"))):
            d = json.load(gzip.open(p))
            ev = sorted((e for e in d["events"] if e["kind"] in ("price_request", "order_won", "order_lost")), key=lambda e: e["seq"])
            reqs = {x["request"]["id"]: x for x in d["reveal"]["requests"]}
            for d0 in range(5):
                for m in CHECK:
                    now = d0 * DAY + m
                    dm = D.Demand(FakeDesk())
                    for e in ev:
                        if e["at"] >= now:
                            break
                        dm.on_event(e)
                    actual, areq = collections.Counter(), collections.Counter()
                    for x in reqs.values():
                        r = x["request"]
                        if r["arrivedAt"] < now:
                            continue
                        g = D.REGION[r["legs"][0]["pickup"]["placeId"]]
                        areq[(g, r["arrivedAt"] // DAY)] += 1
                        if x["outcome"] == "won" and x.get("option"):
                            dl = {o["kind"]: o["deadline"] // DAY for o in r["options"]}
                            actual[(g, dl[x["option"]])] += len(r["legs"])
                    pred, preq = collections.Counter(), collections.Counter()
                    for g in regs:
                        for day in range(d0, 5):
                            preq[(g, day)] += dm.requests_left(g, day, now)
                            for e in dm.expected(g, day, now):
                                pred[(g, e.deadline_day)] += e.n_cars
                    # the planner's old rule
                    past = [x for x in reqs.values() if x["request"]["respondBy"] < now]
                    win = (sum(x["outcome"] == "won" for x in past) + 0.45 * 20) / (len(past) + 20)
                    share = {g: sum(v for pl, v in D.PLACE_SHARE.items() if D.REGION[pl] == g) for g in regs}
                    old = collections.Counter()
                    for g in regs:
                        for day in range(d0, 5):
                            hl = max(0.0, 18 - max(8.0, m / 60)) if day == d0 else 10.0
                            n = 21.0 * hl * share[g] * win
                            old[(g, day)] += 0.5 * n
                            old[(g, day + 1)] += 0.5 * n
                    tot.append(sum(actual.values()))
                    for name, pr in (("demand", pred), ("old", old)):
                        keys = set(pr) | set(actual)
                        err[name + " cells"].append(sum(abs(pr[k] - actual[k]) for k in keys))
                        err[name + " total"].append(abs(sum(pr.values()) - sum(actual.values())))
                    keys = set(preq) | set(areq)
                    err["requests cells"].append(sum(abs(preq[k] - areq[k]) for k in keys))
    print(f"checkpoints {len(tot)}; mean future won cars {st.mean(tot):.0f}")
    for k, v in err.items():
        print(f"  {k:16s} mean abs error {st.mean(v):7.1f}")


if __name__ == "__main__":
    main()
