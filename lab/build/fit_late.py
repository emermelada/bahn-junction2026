"""Does our own unbooked backlog near the pickup (and edge-day deadlines) predict a late car beyond the quote-time P(on time)?

usage: python lab/build/fit_late.py RUN_DIR ...   (each with log.txt + reveal.json.gz; map from data/map.json)
Per won order: logit of the quoted P(on time) for the option won, our posted-but-unbooked orders within 30 km of the
pickup at the win minute, the same over all places, deadline on Friday / last Monday, drive minutes. Label: late.
Fits logistic models on half the runs, scores AUC on the other half (split by run, so no week leaks).
"""
import collections
import gzip
import json
import math
import re
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

DAY = 1440
M = json.load(open("data/map.json"))
P = {p["id"]: p for p in M["places"]}
DRIVE = {(r["from"], r["to"]): r["minutes"] for r in M["roads"]}


def air(a, b):
    p, q = P[a], P[b]
    la1, lo1, la2, lo2 = map(math.radians, (p["lat"], p["lon"], q["lat"], q["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


NEAR = {a: {b for b in P if air(a, b) <= 30} for a in P}


def rows(run):
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    pq = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "QUOTE":
            rid = rest.split()[0]
            pq[rid] = {m.group(1): float(m.group(2)) for m in re.finditer(r"(\w+):r=[\d.]+,p=([\d.]+)", rest)}
    truth = {o["orderId"]: o for o in d["reveal"]["orders"]}
    gig_orders = {g["id"]: {s["orderId"] for s in g["stops"]} for g in d["gigs"]}
    posted = collections.defaultdict(lambda: 10 ** 9)
    for g in d["gigs"]:
        for o in gig_orders[g["id"]]:
            posted[o] = min(posted[o], g["postedAt"])
    booked = collections.defaultdict(lambda: 10 ** 9)
    won, cancelled = {}, set()
    for e in d["events"]:
        if e["kind"] == "gig_booked":
            for o in gig_orders.get(e["gigId"], ()):
                booked[o] = min(booked[o], e["at"])
        elif e["kind"] == "order_won":
            won[e["order"]["id"]] = (e["at"], e["order"])
        elif e["kind"] == "order_cancelled":
            cancelled.add(e["orderId"])
    pick = {oid: o["legs"][0]["pickup"]["placeId"] for oid, (at, o) in won.items()}
    out = []
    for oid, (at, o) in won.items():
        if oid in cancelled or oid not in truth or o["option"] not in pq.get(oid, {}):
            continue
        t = truth[oid]
        dead = lambda l: min(o["deadline"], l["noteDeadline"]) if l["noteDeadline"] else o["deadline"]
        late = not all(l["deliveredAt"] is not None and l["deliveredAt"] <= dead(l) for l in t["legs"])
        p = min(0.995, max(0.005, pq[oid][o["option"]]))
        here = NEAR[pick[oid]]
        bl30 = sum(1 for o2 in won if o2 != oid and posted[o2] <= at < booked[o2] and pick[o2] in here)
        blall = sum(1 for o2 in won if o2 != oid and posted[o2] <= at < booked[o2])
        dd = o["deadline"] // DAY
        drive = sum(DRIVE.get((L["pickup"]["placeId"], L["delivery"]["placeId"]), 600) for L in o["legs"])
        out.append((math.log(p / (1 - p)), math.log1p(bl30), math.log1p(blall), float(dd in (4, 7)),
                    float(dd in (4, 7)) * drive / 60, drive / 60, int(late)))
    return out


runs = sys.argv[1:]
data = {r: rows(r) for r in runs}
A = [x for i, r in enumerate(runs) if i % 2 == 0 for x in data[r]]
B = [x for i, r in enumerate(runs) if i % 2 == 1 for x in data[r]]
A, B = np.array(A), np.array(B)
print(f"orders: fit {len(A)} ({A[:, -1].mean():.3f} late), test {len(B)} ({B[:, -1].mean():.3f} late)")
names = ["logit_p", "log1p_bl30", "log1p_blall", "edge", "edge_x_drive_h", "drive_h"]
for cols in ([0], [0, 1], [0, 2], [0, 3, 4], [0, 1, 3, 4], [0, 1, 2, 3, 4, 5]):
    m = LogisticRegression(C=10.0, max_iter=2000).fit(A[:, cols], A[:, -1])
    auc = roc_auc_score(B[:, -1], m.predict_proba(B[:, cols])[:, 1])
    print(f"{'+'.join(names[c] for c in cols):45s} test AUC {auc:.3f}  coef " + " ".join(f"{names[c]}={w:+.3f}" for c, w in zip(cols, m.coef_[0])) + f" b={m.intercept_[0]:+.3f}")
# raw table: late share by backlog bucket
for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 10), (10, 99)):
    sel = [x for x in np.vstack([A, B]) if lo <= math.expm1(x[1]) < hi]
    if sel:
        s = np.array(sel)
        print(f"bl30 in [{lo},{hi}): n={len(s):5d} late={s[:, -1].mean():.3f} mean quoted P(late)={np.mean(1 - 1 / (1 + np.exp(-s[:, 0]))):.3f}")
for e in (0, 1):
    s = np.array([x for x in np.vstack([A, B]) if x[3] == e])
    for lo, hi in ((0, 2), (2, 4), (4, 12)):
        ss = s[(s[:, 5] >= lo) & (s[:, 5] < hi)]
        if len(ss):
            print(f"edge={e} drive {lo}-{hi} h: n={len(ss):5d} late={ss[:, -1].mean():.3f} quoted P(late)={np.mean(1 - 1 / (1 + np.exp(-ss[:, 0]))):.3f}")
