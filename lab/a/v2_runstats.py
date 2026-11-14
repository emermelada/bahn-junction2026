"""Per-run V2 diagnostics from log.txt + summary.json: score, quotes/declines, posts by kind, bookings within an hour of a
post, expiries, escalations, chains, lam at the last PLAN line of each day. usage: python -I v2_runstats.py <run dir> [...]"""
import collections
import json
import os
import re
import sys


def run(d):
    s = json.load(open(os.path.join(d, "summary.json")))["score"]
    c = collections.Counter()
    posts = {}
    plan_by_day = {}
    for line in open(os.path.join(d, "log.txt"), encoding="utf-8", errors="replace"):
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) != 3:
            continue
        t, tag, rest = int(parts[0]) if parts[0].isdigit() else -1, parts[1], parts[2]
        c[tag] += 1
        if tag == "QUOTE" and " DECLINE " in " " + rest + " ":
            c["DECLINE"] += 1
        elif tag == "V2POST":
            c["V2CHAIN"] += "+" in rest
        elif tag == "GIG":
            posts[rest.split()[0]] = t
        elif tag == "BOOKED":
            gid = rest.split()[0]
            if gid in posts:
                c["BOOK<1h"] += t - posts[gid] <= 60
        elif tag == "PLAN":
            plan_by_day[t // 1440] = rest[:160]
    print(f"{os.path.basename(d):12s} margin {s['marginCents']/100:8.0f} orders {s['wonOrders']:4d} on-time {s['onTimeShare']:.3f} | quotes {c['QUOTE']} declined {c['DECLINE']} "
          f"| V2POST {c['V2POST']} chains {c['V2CHAIN']} POST {c['POST']} BOOKED {c['BOOKED']} <1h {c['BOOK<1h']} REOPEN {c['REOPEN']} ESCALATE {c['ESCALATE']} ERR {c['ERR']}")
    for day in sorted(plan_by_day):
        print(f"   day {day}: {plan_by_day[day]}")


for d in sys.argv[1:]:
    if os.path.exists(os.path.join(d, "summary.json")):
        run(d)
    else:
        for x in sorted(os.listdir(d)):
            if x.endswith("-L8") and os.path.exists(os.path.join(d, x, "summary.json")):
                run(os.path.join(d, x))
