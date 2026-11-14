"""Where the money went: ledger split, price/list of won orders, fee over typical fee, late share by option, booked fee over
opening fee, escalations. usage: python -I v2_diag.py <run dir> [...]"""
import collections
import gzip
import json
import os
import re
import sys


def run(d):
    r = json.load(gzip.open(os.path.join(d, "reveal.json.gz")))
    reqs = {X["request"]["id"]: X for X in r["reveal"]["requests"]}
    led = collections.Counter()
    late = set()
    for e in r["events"]:
        if e["kind"] == "ledger":
            L = e["line"]
            led[L["kind"]] += L["cents"]
            if L["kind"] in ("late_refund", "undelivered_penalty") and L.get("orderId"):
                late.add(L["orderId"])
    won = [e["order"] for e in r["events"] if e["kind"] == "order_won"]
    by_opt = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
    for o in won:
        X = reqs.get(o["id"])
        if not X:
            continue
        lst = next(op["listPriceCents"] for op in X["request"]["options"] if op["kind"] == o["option"])
        b = by_opt[o["option"]]
        b[0] += 1
        b[1] += o["id"] in late
        b[2] += o["priceCents"] / lst
        b[3] += o["priceCents"] / X["request"]["referenceFeeCents"]
    fee0, booked, esc = {}, [], 0
    rx = re.compile(r"fee0=(\d+)")
    for line in open(os.path.join(d, "log.txt"), encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t", 2)
        if len(p) != 3:
            continue
        if p[1] == "GIG":
            m = rx.search(p[2])
            if m:
                fee0[p[2].split()[0]] = int(m.group(1))
        elif p[1] == "BOOKED":
            g, _, fee = p[2].split()[:3]
            if g in fee0:
                booked.append(int(fee) / fee0[g])
        elif p[1] == "ESCALATE":
            esc += 1
    ref_won = sum(reqs[o["id"]]["request"]["referenceFeeCents"] for o in won if o["id"] in reqs)
    print(f"{d}: orders {len(won)} late {len(late)} ({len(late)/max(1,len(won)):.3f})")
    print("  ledger EUR: " + ", ".join(f"{k} {v/100:.0f}" for k, v in sorted(led.items())))
    print(f"  driver fees / typical fees of won orders: {-led['driver_fee']/max(1,ref_won):.2f}; revenue/typical {led['revenue']/max(1,ref_won):.2f}")
    for k, b in sorted(by_opt.items()):
        print(f"  {k:14s} n {b[0]:4d} late {b[1]/b[0]:.3f} price/list {b[2]/b[0]:.3f} price/typical {b[3]/b[0]:.2f}")
    if booked:
        booked.sort()
        print(f"  booked fee / opening fee: n {len(booked)} median {booked[len(booked)//2]:.2f} p90 {booked[int(len(booked)*0.9)]:.2f} share at opening {sum(b <= 1.001 for b in booked)/len(booked):.2f}; escalations {esc}")


for d in sys.argv[1:]:
    run(d)
