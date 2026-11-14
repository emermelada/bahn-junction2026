"""A3 offline validation of supply.py on held-out weeks (seed number % 4 == 3; prior refit on the other seeds).
Replays each week's events into Supply; at 16:00 the day before (the evening release, when the planner commits a day)
reads hours(region, day) and compares with the planner-hours our cars really used that day.
usage: PYTHONPATH=src python -I lab/a/supply_check.py  (needs research/sessionA/scripts/a3_supply_rows.json)"""
import collections, gzip, json, os, statistics, sys
sys.path.insert(0, "src")
from spreadbot import supply as S
from spreadbot.config import Config
from spreadbot.geo import DAY

TRAIN = {  # a3_supply_prior.py on seeds % 4 != 3 (227 weeks)
    "cap": (419, 0.70, 204.3), "east": (40, 0.13, 29.6), "jkl": (44, 0.16, 15.9), "lahti": (37, 0.10, 24.9),
    "north": (6, 0.05, 13.3), "oulu": (56, 0.17, 34.9), "sw": (9, 0.05, 11.6), "tku": (50, 0.21, 29.7),
    "tre": (80, 0.26, 32.9), "west": (36, 0.10, 32.1)}
S.PRIOR = TRAIN


class Rec:
    def __init__(self, g):
        self.stops, self.posted_at, self.schedule = g["stops"], g["postedAt"], g["schedule"]


class FakeDesk:
    def __init__(self, d):
        self.roster = {r["id"]: r for r in d["roster"]}
        self.gigs = {g["id"]: Rec(g) for g in d["gigs"]}
        self.requests = {X["request"]["id"]: X["request"] for X in d["reveal"]["requests"]}
        self.orders, self.now, self.cfg = {}, 0, Config()


rows = json.load(open(os.path.join("..", "research", "sessionA", "scripts", "a3_supply_rows.json")))
actual = {(r["f"], r["rg"], r["day"]): r["phours"] for r in rows}
held = sorted({r["f"] for r in rows if int(r["seed"].split("-")[1]) % 4 == 3})
U = collections.defaultdict(list); P = []; L = []
for f in held:
    d = json.load(gzip.open(os.path.join("..", f)))
    sup = S.Supply(FakeDesk(d))
    evs = sorted(d["events"], key=lambda e: (e["at"], e.get("seq", 0)))
    i = 0
    for day in (1, 2, 3, 4, 5, 7):
        t = (day - 1) * DAY + 16 * 60 if day != 7 else 4 * DAY + 16 * 60  # Mon2 cars are committed by Friday evening
        while i < len(evs) and evs[i]["at"] < t:
            sup.on_event(evs[i]); i += 1
        sup.desk.now = t
        for rg in sup.regions():
            h = sup.hours(rg, day); a = actual.get((f, rg, day), 0.0)
            U[(rg, day)].append(a / max(1e-9, h) if h > 0 else (0.0 if a == 0 else 9.9))
            P.append((h, a)); L.append(sup.learned(rg))
print(f"held-out weeks {len(held)}; u = used / Supply.hours, read at 16:00 the day before")
print("region  | u p50  p90  p95  max | share of days over 1.0")
for rg in sorted({k[0] for k in U}):
    v = sorted(x for (r, d), xs in U.items() if r == rg and d in (1, 2, 3, 4) for x in xs)
    print(f"  {rg:5s} | {v[len(v)//2]:.2f} {v[int(.9*len(v))]:.2f} {v[int(.95*len(v))]:.2f} {v[-1]:.2f} | {sum(x > 1 for x in v)/len(v):.3f}")
for day in (5, 7):
    v = sorted(x for (r, d), xs in U.items() if d == day for x in xs)
    print(f"  day {day} | {v[len(v)//2]:.2f} {v[int(.9*len(v))]:.2f} {v[int(.95*len(v))]:.2f} {v[-1]:.2f} | {sum(x > 1 for x in v)/len(v):.3f}")
hs = [h for h, a in P if h > 0]; as_ = [a for h, a in P if h > 0]
mh, ma = statistics.mean(hs), statistics.mean(as_)
cov = sum((h - mh) * (a - ma) for h, a in zip(hs, as_)) / len(hs)
print(f"corr(hours, used) over region-days {cov / (statistics.pstdev(hs) * statistics.pstdev(as_)):.2f}; learned factor p5/p50/p95 "
      f"{sorted(L)[len(L)//20]:.2f}/{sorted(L)[len(L)//2]:.2f}/{sorted(L)[19*len(L)//20]:.2f}")
