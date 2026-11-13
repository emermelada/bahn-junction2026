"""Diagnose a run: money split, price and fee ratios, on-time calibration by p_ok, late causes, per day.

usage: python lab/frank/diag.py data/runs/<tag>/<seed>-L8 [...]
"""
import collections
import gzip
import json
import re
import statistics as st
import sys

for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev, rev, gigs = d["events"], d["reveal"], d["gigs"]
    reqs = {r["request"]["id"]: r for r in rev["requests"]}
    truth = {o["orderId"]: o["legs"] for o in rev["orders"]}
    won = {e["order"]["id"]: e["order"] for e in ev if e["kind"] == "order_won"}
    cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    money = collections.Counter()
    for e in ev:
        if e["kind"] == "ledger":
            money[e["line"]["kind"]] += e["line"]["cents"] / 100
    print(f"=== {run}  total {sum(money.values()):.0f}  " + "  ".join(f"{k}={v:.0f}" for k, v in money.most_common()))
    pok = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "QUOTE":
            rid = rest.split()[0]
            pok[rid] = {m.group(1): float(m.group(2)) for m in re.finditer(r"(\w+):r=[\d.]+,p=([\d.]+)", rest)}
    out = collections.Counter(r["outcome"] for r in reqs.values())
    declined = sum(1 for r in reqs.values() if r["quote"] and min(r["quote"].values()) > 3 * r["request"]["options"][0]["listPriceCents"])
    print(f"requests {len(reqs)} outcomes {dict(out)} declined {declined}")
    rows = []
    for oid, o in won.items():
        if oid in cancelled or oid not in truth:
            continue
        q = reqs[oid]["request"]
        tl = truth[oid]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        ontime = all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl)
        lp = next(x["listPriceCents"] for x in q["options"] if x["kind"] == o["option"])
        rows.append(dict(oid=oid, ontime=ontime, ratio=o["priceCents"] / lp, p=pok.get(oid, {}).get(o["option"], None), opt=o["option"], day=o["deadline"] // 1440,
                         won_day=q["respondBy"] // 1440, price=o["priceCents"] / 100, ref=q["referenceFeeCents"] / 100))
    print(f"orders {len(rows)} on-time {sum(r['ontime'] for r in rows)/len(rows):.3f} mean price/list {st.mean(r['ratio'] for r in rows):.3f} "
          f"options {collections.Counter(r['opt'] for r in rows)}")
    for lo, hi in [(0, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.01)]:
        xs = [r for r in rows if r["p"] is not None and lo <= r["p"] < hi]
        if xs:
            print(f"  p_ok [{lo},{hi}) n={len(xs)} on-time {sum(r['ontime'] for r in xs)/len(xs):.2f}")
    for day in range(5):
        xs = [r for r in rows if r["won_day"] == day]
        if xs:
            print(f"  won day {day}: n={len(xs)} on-time {sum(r['ontime'] for r in xs)/len(xs):.2f} price/list {st.mean(r['ratio'] for r in xs):.2f}")
    # fees per booked gig over typical fee
    book = {e["gigId"]: e["feeCents"] for e in ev if e["kind"] == "gig_booked"}
    done = {e["gigId"] for e in ev if e["kind"] == "gig_started"}
    gr = []
    for g in gigs:
        if g["id"] in done and g["status"] in ("done", "working"):
            oid = g["stops"][0]["orderId"]
            q = reqs[oid]["request"]
            nl = sum(1 for s in g["stops"] if s["kind"] == "pickup")
            gr.append(g["feeCents"] / (q["referenceFeeCents"] * nl / len(q["legs"])))
    if gr:
        print(f"  started gigs {len(gr)} fee/typical quartiles {[round(x, 2) for x in st.quantiles(gr, n=4)]} mean {st.mean(gr):.2f}")
    kinds = collections.Counter(e["kind"] for e in ev if e["kind"] not in ("gig_viewed", "ledger"))
    print("  events", dict(kinds))
