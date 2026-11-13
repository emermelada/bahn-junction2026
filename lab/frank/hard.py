"""Which won orders end late? Features known at quote time -> on-time label. Logistic fit for insight.

usage: python lab/frank/hard.py data/runs/exp1/*-L8
"""
import collections
import gzip
import json
import math
import re
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "src")
from spreadbot.geo import Geo  # noqa: E402

geo = Geo(json.load(open("data/map.json")))
X, Y, META = [], [], []
NAMES = ["fee_ratio", "log_drive", "log_sup_p30", "log_sup_d30", "log_sup_p80", "same_day", "slack_h", "late_hour", "private", "premium", "tradein", "ready_later", "note", "friday"]
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev, rev = d["events"], d["reveal"]
    homes = collections.Counter(x["homePlaceId"] for x in d["roster"])
    sup = lambda p, r: sum(c for h, c in homes.items() if geo.air(h, p) <= r)
    reqs = {r["request"]["id"]: r["request"] for r in rev["requests"]}
    truth = {o["orderId"]: o["legs"] for o in rev["orders"]}
    won = {e["order"]["id"]: e["order"] for e in ev if e["kind"] == "order_won"}
    cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    first = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        oid = rest.split()[0]
        if code == "POST" and " won " in rest and oid not in first:
            m = re.search(r"legs=\[([\d, ]+)\].*fee0=(\d+)", rest)
            q = reqs[oid]
            first[oid] = int(m.group(2)) / (q["referenceFeeCents"] * len(m.group(1).split(",")) / len(q["legs"]))
    for oid, o in won.items():
        if oid in cancelled or oid not in truth or oid not in first:
            continue
        q = reqs[oid]
        L0 = q["legs"][0]
        p, dl = L0["pickup"]["placeId"], L0["delivery"]["placeId"]
        drive = sum(geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in q["legs"])
        ready = L0["pickup"]["window"]["from"]
        slack = (o["deadline"] - max(q["respondBy"], ready) - drive) / 60
        tl = truth[oid]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        ontime = all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl)
        x = [first[oid], math.log(drive + 10), math.log1p(sup(p, 30)), math.log1p(sup(dl, 30)), math.log1p(sup(p, 80)), o["option"] == "same_day", min(slack, 48),
             (q["respondBy"] % 1440) / 60 > 15, L0["pickup"]["privateAddress"] or L0["delivery"]["privateAddress"], any(L["car"]["premium"] for L in q["legs"]),
             len(q["legs"]) == 2, ready > q["respondBy"] + 120, q["note"] is not None, q["respondBy"] // 1440 == 4]
        X.append([float(v) for v in x])
        Y.append(ontime)
        META.append((run[-12:], oid, o["option"], round(slack, 1), drive, sup(p, 30), sup(dl, 30), ontime))
X, Y = np.array(X), np.array(Y)
print("n", len(Y), "on-time", Y.mean().round(3))
mu, sd = X.mean(0), X.std(0) + 1e-9
clf = LogisticRegression(C=1.0, max_iter=2000).fit((X - mu) / sd, Y)
for n, c in sorted(zip(NAMES, clf.coef_[0]), key=lambda t: -abs(t[1])):
    print(f"  {n:12s} {c:+.2f}")
p = clf.predict_proba((X - mu) / sd)[:, 1]
for th in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9):
    keep = p >= th
    print(f"  keep p>={th}: {keep.mean():.2f} of orders, on-time among kept {Y[keep].mean():.3f}")
# simple univariate tables
def tab(name, idx, edges):
    out = []
    for lo, hi in zip(edges, edges[1:]):
        m = (X[:, idx] >= lo) & (X[:, idx] < hi)
        if m.sum():
            out.append(f"[{lo},{hi}):{Y[m].mean():.2f}({m.sum()})")
    print(name, " ".join(out))
tab("slack_h", NAMES.index("slack_h"), [-99, 0, 1, 2, 3, 4, 6, 8, 12, 24, 99])
tab("log_drive", NAMES.index("log_drive"), [0, 4, 4.5, 5, 5.5, 6, 6.5, 9])
tab("log_sup_p30", NAMES.index("log_sup_p30"), [0, 0.5, 1.5, 2.5, 3.5, 4.5, 9])
tab("log_sup_d30", NAMES.index("log_sup_d30"), [0, 0.5, 1.5, 2.5, 3.5, 4.5, 9])
tab("fee_ratio", 0, [0, 1.0, 1.2, 1.4, 1.6, 2.0, 9])
json.dump({"X": X.tolist(), "Y": Y.tolist(), "names": NAMES, "meta": META}, open("data/hard_rows.json", "w"))
