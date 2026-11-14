"""Driver fee paid per gig vs the typical fee of its cars, singles vs bundles.

usage: python lab/frank/gigcost.py data/runs/<tag>/*-L8
"""
import collections, gzip, json, sys, statistics

tot = collections.Counter()
rat = collections.defaultdict(list)
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    ref = {}
    for e in d["events"]:
        if e["kind"] == "order_won":
            ref[e["order"]["id"]] = reqs[e["order"]["id"]]["referenceFeeCents"] / max(1, len(e["order"]["legs"]))
    fee = collections.Counter()
    for e in d["events"]:
        if e["kind"] == "ledger" and e["line"]["kind"] == "driver_fee" and e["line"].get("gigId"):
            fee[e["line"]["gigId"]] -= e["line"]["cents"]
    for g in d["gigs"]:
        if not fee[g["id"]]:
            continue
        cars = [s["orderId"] for s in g["stops"] if s["kind"] == "pickup"]
        r = sum(ref.get(o, 0) for o in cars)
        if not r:
            continue
        kind = "single" if len(cars) == 1 else ("tradein" if len(set(cars)) == 1 else f"bundle{len(cars)}")
        tot[kind + "_fee"] += fee[g["id"]]; tot[kind + "_ref"] += r; tot[kind + "_n"] += 1
        rat[kind].append(fee[g["id"]] / r)
nw = len(sys.argv[1:])
for k in sorted(rat):
    print(f"{k:10s} gigs/week {tot[k+'_n']/nw:6.1f}  fee/ref total {tot[k+'_fee']/tot[k+'_ref']:.3f}  median {statistics.median(rat[k]):.3f}  fees/week {tot[k+'_fee']/nw/100:8.0f}  ref/week {tot[k+'_ref']/nw/100:8.0f}")
print(d["gigs"][0].keys())
