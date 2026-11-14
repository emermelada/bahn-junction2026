"""Late share and fee by how a car moved: single gig, bundle, after an unbundle, or held then posted alone.

usage: python lab/frank/latekind.py data/runs/<tag>/*-L8
"""
import gzip, json, sys, collections
c = collections.Counter()
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    truth = {o["orderId"]: o for o in d["reveal"]["orders"]}
    won = {e["order"]["id"]: (e["at"], e["order"]) for e in d["events"] if e["kind"] == "order_won"}
    unb, first_post = set(), {}
    g2o = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "GIG":
            gid, oid = rest.split()[:2]
            g2o[gid] = oid
            first_post.setdefault(oid, int(t))
        if code == "UNBUNDLE":
            pass
    booked = {}
    for g in d["gigs"]:
        if g.get("driverId"):
            cars = {s["orderId"] for s in g["stops"] if s["kind"] == "pickup"}
            for o in cars:
                booked.setdefault(o, []).append(len(cars))
    for oid, (at, o) in won.items():
        t = truth.get(oid)
        if not t:
            continue
        dead = lambda l: min(o["deadline"], l["noteDeadline"]) if l["noteDeadline"] else o["deadline"]
        late = not all(l["deliveredAt"] is not None and l["deliveredAt"] <= dead(l) for l in t["legs"])
        b = booked.get(oid, [])
        k = "bundle" if any(x > 1 for x in b) else ("held>2h" if first_post.get(oid, at) - at > 120 else "single")
        if len(o["legs"]) == 2:
            k = "tradein"
        c[k, "n"] += 1
        c[k, "late"] += late
n = len(sys.argv[1:])
for k in ("single", "held>2h", "bundle", "tradein"):
    print(f"{k:8s} cars/week {c[k,'n']/n:6.1f} late {c[k,'late']/max(1,c[k,'n']):.3f}")
