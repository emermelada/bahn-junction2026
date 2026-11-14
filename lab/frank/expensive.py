"""Which won cars end expensive (paid fee > 1.3x typical, or late)? Quote-time features only.

usage: python lab/frank/expensive.py data/runs/v1am-load05/*-L8 data/runs/rc2/*-L8 ...
Held out by seed. Prints AUC, calibration and the logistic coefficients to paste into the bot.
"""
import collections
import gzip
import json
import math
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, "src")
from spreadbot.config import Config  # noqa: E402
from spreadbot.desk import Desk  # noqa: E402
from spreadbot.geo import DAY, Geo  # noqa: E402

geo = Geo(json.load(open("data/map.json")))
NAMES = ["log_drive", "log_ref", "log_sup_p30", "log_sup_p80", "log_sup_d30", "slack12", "overnight", "same_day",
         "hour", "late_hour", "friday", "premium", "private", "note", "load", "tradein"]
X, Y, M, G = [], [], [], []
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev = d["events"]
    desk = Desk(geo, Config(), 8, 0, d["roster"])
    nd = len(d["roster"])
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    desk.requests.update(reqs)
    truth = {o["orderId"]: o["legs"] for o in d["reveal"]["orders"]}
    canc = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    g2o = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "GIG":
            g2o[rest.split()[0]] = rest.split()[1]
    fees = collections.Counter()
    money = collections.Counter()
    for e in ev:
        if e["kind"] == "ledger":
            line = e["line"]
            oid = line.get("orderId") or g2o.get(line.get("gigId") or "")
            if oid:
                money[oid] += line["cents"]
                if line["kind"] == "driver_fee":
                    fees[oid] -= line["cents"]
    due = collections.Counter()
    for e in ev:
        if e["kind"] != "order_won":
            continue
        o = e["order"]
        q = reqs.get(o["id"])
        if not q:
            continue
        opt = next(x for x in q["options"] if x["kind"] == o["option"])
        f = desk.ontime.features(q, opt["deadline"], o["option"])
        dday = o["deadline"] // DAY
        load = due[dday] / nd
        due[dday] += 1
        if o["id"] in canc or o["id"] not in truth:
            continue
        L0 = q["legs"][0]
        p, dl = L0["pickup"]["placeId"], L0["delivery"]["placeId"]
        drive = sum(geo.drive(L["pickup"]["placeId"], L["delivery"]["placeId"]) for L in q["legs"])
        hour = (q["respondBy"] % DAY) / 60
        x = [math.log(drive + 10), math.log(q["referenceFeeCents"]), math.log1p(desk.supply_near(p, 30)), f["log_sup_p80"], f["log_sup_d30"],
             f["slack12"], f["overnight"], f["same_day"], hour, float(hour >= 15), f["friday"], f["premium"], f["private"], f["note"], load,
             float(len(q["legs"]) == 2)]
        tl = truth[o["id"]]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        late = not all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl)
        X.append(x)
        Y.append(late or fees[o["id"]] > 1.3 * q["referenceFeeCents"])
        M.append(money[o["id"]] / 100)
        G.append(run.split("/")[-1])
X, Y, M, G = np.array(X), np.array(Y), np.array(M), np.array(G)
mu, sd = X.mean(0), X.std(0) + 1e-9
Z = (X - mu) / sd
print("orders", len(Y), "expensive share", Y.mean().round(3), "mean margin", M.mean().round(1))
aucs, preds = [], np.zeros(len(Y))
for s in sorted(set(G)):
    te = G == s
    m = LogisticRegression(C=0.3, max_iter=5000).fit(Z[~te], Y[~te])
    preds[te] = m.predict_proba(Z[te])[:, 1]
    if len(set(Y[te])) > 1:
        aucs.append(roc_auc_score(Y[te], preds[te]))
print("held-out-seed AUC mean", round(float(np.mean(aucs)), 3), "min", round(float(np.min(aucs)), 3))
for q in (0.5, 0.7, 0.8, 0.9, 0.95):
    th = np.quantile(preds, q)
    hi = preds >= th
    print(f"  top {1-q:.0%} by risk: expensive {Y[hi].mean():.2f} margin/order {M[hi].mean():6.1f} | rest {Y[~hi].mean():.2f} {M[~hi].mean():6.1f}")
m = LogisticRegression(C=0.3, max_iter=5000).fit(Z, Y)
coef = {n: round(float(c / s), 4) for n, c, s in zip(NAMES, m.coef_[0], sd)}
coef["intercept"] = round(float(m.intercept_[0] - sum(c * mm / s for c, mm, s in zip(m.coef_[0], mu, sd))), 4)
print("EXPENSIVE_COEF =", coef)
for n, c in sorted(zip(NAMES, m.coef_[0]), key=lambda t: -abs(t[1]))[:8]:
    print(f"  {n:12s} {c:+.2f} (per sd)")

# Margin directly: does any quote-time signal find the cars that lose money?
from sklearn.ensemble import GradientBoostingRegressor
pm = np.zeros(len(M))
for s in sorted(set(G)):
    te = G == s
    r = GradientBoostingRegressor(max_depth=3, n_estimators=200, learning_rate=0.05, subsample=0.8).fit(X[~te], np.clip(M[~te], -150, 150))
    pm[te] = r.predict(X[te])
print("margin model, held-out seeds: corr", round(float(np.corrcoef(pm, M)[0, 1]), 3))
for q in (0.05, 0.1, 0.2, 0.3):
    th = np.quantile(pm, q)
    lo = pm <= th
    print(f"  bottom {q:.0%} by predicted margin: actual margin/order {M[lo].mean():6.1f} (n={lo.sum()}), total {M[lo].sum()/len(set(G)):.0f}/week")
lo = pm <= np.quantile(pm, 0.05)
for i, n in enumerate(NAMES):
    print(f"  {n:12s} bottom5% mean {X[lo, i].mean():7.3f}  all mean {X[:, i].mean():7.3f}")
for name, rule in [("drive<30", np.exp(X[:, 0]) - 10 < 30), ("drive<30 & slack<6", (np.exp(X[:, 0]) - 10 < 30) & (X[:, 5] < 6)),
                   ("ref<30eur", np.exp(X[:, 1]) < 3000), ("load>0.07", X[:, 14] > 0.07), ("private", X[:, 12] > 0)]:
    print(f"  rule {name:22s} n={rule.sum():5d} share={rule.mean():.2f} margin/order {M[rule].mean():6.1f}")
