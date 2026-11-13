"""Refit the on-time model on weeks played by the current policy (features exactly as the bot computes them).

usage: python lab/frank/refit_ontime.py data/runs/v1c/*-L8 data/runs/v1h-bundle/*-L8 ...
"""
import gzip
import json
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, "src")
from spreadbot.config import Config  # noqa: E402
from spreadbot.desk import Desk  # noqa: E402
from spreadbot.geo import Geo  # noqa: E402
from spreadbot.policy import ONTIME_COEF  # noqa: E402

geo = Geo(json.load(open("data/map.json")))
NAMES = [k for k in ONTIME_COEF if k not in ("intercept", "fee")]
X, Y, G = [], [], []
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    desk = Desk(geo, Config(), 8, 0, d["roster"])
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    desk.requests.update(reqs)
    truth = {o["orderId"]: o["legs"] for o in d["reveal"]["orders"]}
    canc = {e["orderId"] for e in d["events"] if e["kind"] == "order_cancelled"}
    for e in d["events"]:
        if e["kind"] != "order_won" or e["order"]["id"] in canc or e["order"]["id"] not in truth:
            continue
        o = e["order"]
        q = reqs[o["id"]]
        opt = next(x for x in q["options"] if x["kind"] == o["option"])
        f = desk.ontime.features(q, opt["deadline"], o["option"])
        tl = truth[o["id"]]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        X.append([f[n] for n in NAMES])
        Y.append(all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl))
        G.append(run.split("/")[-1])
X, Y, G = np.array(X), np.array(Y), np.array(G)
print("orders", len(Y), "on-time", Y.mean().round(3))
seeds = sorted(set(G))
aucs, cal = [], []
for s in seeds:
    te = G == s
    m = LogisticRegression(C=0.3, max_iter=5000).fit(X[~te], Y[~te])
    p = m.predict_proba(X[te])[:, 1]
    aucs.append(roc_auc_score(Y[te], p))
    cal += list(zip(p, Y[te]))
print("held-out-seed AUC", np.round(aucs, 3), "mean", round(float(np.mean(aucs)), 3))
cal = np.array(cal)
for lo, hi in [(0, 0.85), (0.85, 0.9), (0.9, 0.93), (0.93, 0.96), (0.96, 1.01)]:
    k = (cal[:, 0] >= lo) & (cal[:, 0] < hi)
    if k.sum():
        print(f"  pred [{lo},{hi}) n={k.sum()} mean pred {cal[k,0].mean():.3f} actual {cal[k,1].mean():.3f}")
m = LogisticRegression(C=0.3, max_iter=5000).fit(X, Y)
coef = {"intercept": round(float(m.intercept_[0]), 3), **{n: round(float(c), 3) for n, c in zip(NAMES, m.coef_[0])}, "fee": 0.0}
print("ONTIME_COEF =", coef)
