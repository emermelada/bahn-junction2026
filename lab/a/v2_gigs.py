"""Per-gig split of a run: chain/single x post reason x escalated: gigs, cars, fee over typical, late share; and late cars by
won day and option. usage: python -I v2_gigs.py <run dir>"""
import collections
import gzip
import json
import re
import sys

d = sys.argv[1]
r = json.load(gzip.open(d + "/reveal.json.gz"))
reqs = {X["request"]["id"]: X["request"] for X in r["reveal"]["requests"]}
late = set()
fee = collections.defaultdict(int)
for e in r["events"]:
    if e["kind"] == "ledger":
        L = e["line"]
        if L["kind"] in ("late_refund", "undelivered_penalty"):
            late.add(L["orderId"])
        if L["kind"] == "driver_fee" and L.get("gigId"):
            fee[L["gigId"]] += -L["cents"]
gigs = {g["id"]: g for g in r["gigs"]}
gigwhy, esc, posted, booked = {}, set(), {}, {}
for line in open(d + "/log.txt", encoding="utf-8", errors="replace"):
    p = line.rstrip("\n").split("\t", 2)
    if len(p) != 3:
        continue
    if p[1] == "GIG":
        w = p[2].split()
        gigwhy[w[0]] = w[2]
        posted[w[0]] = int(p[0])
    elif p[1] == "ESCALATE":
        esc.add(p[2].split()[0])
    elif p[1] == "BOOKED":
        booked[p[2].split()[0]] = int(p[0])
C = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0.0])
for gid, g in gigs.items():
    if gid not in fee:
        continue
    oids = sorted({s["orderId"] for s in g["stops"]})
    n = len(oids)
    ref = sum(reqs[o]["referenceFeeCents"] for o in oids if o in reqs)
    key = ("chain" if n > 1 else "single", gigwhy.get(gid, "?"), "esc" if gid in esc else "flat")
    c = C[key]
    c[0] += 1
    c[1] += n
    c[2] += fee[gid]
    c[3] += ref
    c[4] += sum(o in late for o in oids)
    c[5] += (booked[gid] - posted[gid]) / 60 if gid in booked and gid in posted else 0
print(f"{'kind':8s}{'why':14s}{'esc':5s} gigs cars fee/ref late  h-to-book")
for k, c in sorted(C.items()):
    print(f"{k[0]:8s}{k[1]:14s}{k[2]:5s} {c[0]:4d} {c[1]:4d} {c[2]/max(1,c[3]):.2f} {c[4]/max(1,c[1]):.2f}  {c[5]/max(1,c[0]):.1f}")
late_by, n_by = collections.Counter(), collections.Counter()
for e in r["events"]:
    if e["kind"] == "order_won":
        o = e["order"]
        k = (e["at"] // 1440, o["option"])
        n_by[k] += 1
        late_by[k] += o["id"] in late
print("won day, option: n late")
for k in sorted(n_by):
    print(f"  {k} {n_by[k]:3d} {late_by[k]/n_by[k]:.2f}")
