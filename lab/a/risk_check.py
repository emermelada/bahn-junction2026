"""A3: runtime check of risk.py. Replays played weeks through a Desk (c3, v2 off), adding each gig when it was posted, and
asks Risk.p_late at every order_won with the car's real first-post day and chain size. Prints predicted vs actual late per
run set, AUC, and the mean features of c3 vs the volume probes (what grows with volume).
usage: PYTHONPATH=src python -I lab/a/risk_check.py <runs dir>[:seed,seed] [...]"""
import collections, gzip, json, os, sys
sys.path.insert(0, "src")
from spreadbot.config import Config
from spreadbot.desk import Desk, GigRec
from spreadbot.geo import DAY, Geo
from spreadbot.presets import PRESETS
from spreadbot.risk import RISK_COEF, Risk

geo = Geo(json.load(open("data/map.json", encoding="utf-8")))


def auc(s, y):
    pos = [a for a, b in zip(s, y) if b]; neg = sorted(a for a, b in zip(s, y) if not b)
    import bisect
    return sum(bisect.bisect_left(neg, p) + 0.5 * (bisect.bisect_right(neg, p) - bisect.bisect_left(neg, p)) for p in pos) / max(1, len(pos) * len(neg))


for arg in sys.argv[1:]:
    path, _, seeds = arg.partition(":")
    P, Y, F = [], [], collections.Counter()
    W = 0
    for x in sorted(os.listdir(path)):
        f = os.path.join(path, x, "reveal.json.gz")
        if not (x.endswith("-L8") and os.path.exists(f)) or (seeds and x[:-3] not in seeds.split(",")):
            continue
        d = json.load(gzip.open(f)); W += 1
        desk = Desk(geo, Config.parse(PRESETS["c3"]), 8, 0, d["roster"]); risk = Risk(desk)
        late = {e["line"]["orderId"] for e in d["events"] if e["kind"] == "ledger" and e["line"]["kind"] in ("late_refund", "undelivered_penalty")}
        canc = {e["orderId"] for e in d["events"] if e["kind"] == "order_cancelled"}
        gigs = sorted(d["gigs"], key=lambda g: g["postedAt"]); gi = 0
        first_post, n_orders = {}, {}
        for g in d["gigs"]:
            os_ = sorted({s["orderId"] for s in g["stops"]})
            for o in os_:
                first_post[o] = min(first_post.get(o, 10 ** 9), g["postedAt"]); n_orders[o] = max(n_orders.get(o, 1), len(os_))
        for e in d["events"]:
            while gi < len(gigs) and gigs[gi]["postedAt"] <= e["at"]:
                g = gigs[gi]; desk.gigs[g["id"]] = GigRec(g["id"], g["stops"], g["audience"], g["schedule"], g["postedAt"]); gi += 1
            desk.now = max(desk.now, e["at"])
            if e["kind"] == "order_won" and e["order"]["id"] not in canc and e["order"]["id"] in desk.requests:
                o = e["order"]; post = first_post.get(o["id"], e["at"])
                pday = post // DAY + (1 if post % DAY >= 16 * 60 else 0)
                feats = risk.features(desk.requests[o["id"]], o["option"], pday, n_orders.get(o["id"], 1))
                P.append(risk.p_late(desk.requests[o["id"]], o["option"], pday, n_orders.get(o["id"], 1))); Y.append(o["id"] in late)
                for k, v in feats.items():
                    F[k] += v
            desk.outbox.clear()
            desk.handle(e)
    n = len(P)
    print(f"== {path}{':' + seeds if seeds else ''} {W} weeks, {n/W:.0f} cars/wk: predicted late {sum(P)/W:.1f}/wk ({sum(P)/n:.3f}), "
          f"actual {sum(Y)/W:.1f}/wk ({sum(Y)/n:.3f}), AUC {auc(P, Y):.3f}")
    print("   mean features: " + " ".join(f"{k}={F[k]/n:.2f}" for k in RISK_COEF if k != "intercept"))
