"""Dealer and driver curves from research runs (random quote ratio, flat random fee ratio).

usage: python lab/frank/curves.py data/runs/exp1/*/reveal.json.gz
"""
import collections
import gzip
import json
import math
import sys

sys.path.insert(0, "src")
from spreadbot.geo import Geo  # noqa: E402

geo = Geo(json.load(open("data/map.json")))
dealer_rows, driver_rows = [], []
for path in sys.argv[1:]:
    d = json.load(gzip.open(path, "rt"))
    ev, rev, gigs = d["events"], d["reveal"], d["gigs"]
    reqs = {r["request"]["id"]: r for r in rev["requests"]}
    homes = collections.Counter(x["homePlaceId"] for x in d["roster"])
    # trust at each minute from ledger
    trust = collections.defaultdict(int)
    trust_at = []  # (at, dealer, count) snapshots
    refunds = set(e["line"]["orderId"] for e in ev if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty"))
    outcome_at = {}
    for e in ev:
        if e["kind"] in ("order_won", "order_lost"):
            rid = e["order"]["id"] if e["kind"] == "order_won" else e["requestId"]
            outcome_at[rid] = (e["at"], trust[reqs[rid]["request"]["dealerId"]] if rid in reqs else 0)
        if e["kind"] == "ledger" and e["line"]["kind"] == "revenue":
            oid = e["line"]["orderId"]
            if oid in reqs and oid not in refunds:
                dl = reqs[oid]["request"]["dealerId"]
                trust[dl] = min(25, trust[dl] + 1)
            elif oid in reqs:
                dl = reqs[oid]["request"]["dealerId"]
                trust[dl] //= 2
    for rid, r in reqs.items():
        if not r["quote"]:
            continue
        q = r["request"]
        opt = q["options"][0]
        p = r["quote"].get(opt["kind"])
        if p is None:
            continue
        at, tr = outcome_at.get(rid, (q["respondBy"], 0))
        dealer_rows.append((p / opt["listPriceCents"], tr, r["outcome"] == "won", at // 1440, q["dealerId"], opt["kind"], len(q["options"])))
    # driver side: each order's FIRST gig
    first_gig = {}
    for g in sorted(gigs, key=lambda g: g["postedAt"]):
        oid = g["stops"][0]["orderId"]
        first_gig.setdefault(oid, g)
    booked_at = {}
    for e in ev:
        if e["kind"] == "gig_booked":
            booked_at.setdefault(e["gigId"], (e["at"], e["feeCents"]))
    warn = {}
    for e in ev:
        if e["kind"] == "deadline_close":
            warn.setdefault(e["orderId"], e["at"])
    won = {e["order"]["id"]: e for e in ev if e["kind"] == "order_won"}
    for oid, g in first_gig.items():
        if oid not in reqs or oid not in won:
            continue
        q = reqs[oid]["request"]
        o = won[oid]["order"]
        nlegs = sum(1 for s in g["stops"] if s["kind"] == "pickup")
        base = q["referenceFeeCents"] * nlegs / len(q["legs"])
        f0 = g["schedule"][0]["feeCents"] / base
        b = booked_at.get(g["id"])
        p0 = q["legs"][0]["pickup"]["placeId"]
        d0 = q["legs"][0]["delivery"]["placeId"]
        sup_p = sum(c for h, c in homes.items() if geo.air(h, p0) <= 30)
        sup_d = sum(c for h, c in homes.items() if geo.air(h, d0) <= 30)
        horizon = o["lastPickupAt"] - g["postedAt"]
        driver_rows.append(dict(f0=round(f0, 2), booked=b is not None and (oid not in warn or b[0] <= warn[oid]), wait=(b[0] - g["postedAt"]) if b else None,
                                sup_p=sup_p, sup_d=sup_d, horizon=horizon, option=o["option"], hour=(g["postedAt"] % 1440) // 60,
                                drive=geo.drive(p0, d0), private=q["legs"][0]["pickup"]["privateAddress"] or q["legs"][0]["delivery"]["privateAddress"]))

print("== DEALER: win rate by quote/list (trust-adjusted), n =", len(dealer_rows))
bins = collections.defaultdict(lambda: [0, 0])
for r, tr, w, day, *_ in dealer_rows:
    x = r / (1 + tr / 100)
    k = round(math.floor(x * 20) / 20, 2)
    bins[k][0] += w
    bins[k][1] += 1
for k in sorted(bins):
    print(f"  r={k:.2f}  n={bins[k][1]:4d}  win={bins[k][0]/bins[k][1]:.2f}")
print("  by day (r in 1.2-1.5):", {day: round(sum(w for r, tr, w, dd, *_ in dealer_rows if dd == day and 1.2 <= r / (1 + tr / 100) < 1.5) / max(1, sum(1 for r, tr, w, dd, *_ in dealer_rows if dd == day and 1.2 <= r / (1 + tr / 100) < 1.5)), 2) for day in range(5)})

print("== DRIVER: first gig flat fee ratio -> booked before warning, n =", len(driver_rows))
by = collections.defaultdict(list)
for x in driver_rows:
    by[x["f0"]].append(x)
for k in sorted(by):
    xs = by[k]
    waits = sorted(x["wait"] for x in xs if x["booked"])
    print(f"  fee/ref={k:.2f} n={len(xs):3d} booked={sum(x['booked'] for x in xs)/len(xs):.2f} median wait={waits[len(waits)//2] if waits else None}")
print("== DRIVER by pickup supply (all ratios), booked share per fee bucket")
for lo, hi in [(0, 10), (10, 40), (40, 120), (120, 2000)]:
    row = []
    for k in sorted(by):
        xs = [x for x in by[k] if lo <= x["sup_p"] < hi]
        row.append(f"{k}:{sum(x['booked'] for x in xs)/len(xs):.2f}({len(xs)})" if xs else f"{k}:-")
    print(f"  sup_p {lo}-{hi}: " + "  ".join(row))
print("== DRIVER by delivery supply")
for lo, hi in [(0, 10), (10, 40), (40, 120), (120, 2000)]:
    row = []
    for k in sorted(by):
        xs = [x for x in by[k] if lo <= x["sup_d"] < hi]
        row.append(f"{k}:{sum(x['booked'] for x in xs)/len(xs):.2f}({len(xs)})" if xs else f"{k}:-")
    print(f"  sup_d {lo}-{hi}: " + "  ".join(row))
print("== DRIVER by option")
for opt in ("same_day", "next_day", "within_3_days"):
    row = []
    for k in sorted(by):
        xs = [x for x in by[k] if x["option"] == opt]
        row.append(f"{k}:{sum(x['booked'] for x in xs)/len(xs):.2f}({len(xs)})" if xs else f"{k}:-")
    print(f"  {opt}: " + "  ".join(row))
json.dump({"dealer": dealer_rows, "driver": driver_rows}, open("data/curves_rows.json", "w"))
