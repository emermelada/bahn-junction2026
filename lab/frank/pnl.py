"""Per-order P&L with quote-time features: where is money made and lost?

usage: python lab/frank/pnl.py data/runs/<tag>/*-L8
"""
import collections
import gzip
import json
import sys

sys.path.insert(0, "src")
from spreadbot.config import Config  # noqa: E402
from spreadbot.desk import Desk  # noqa: E402
from spreadbot.geo import Geo  # noqa: E402

geo = Geo(json.load(open("data/map.json")))
rows = []
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev, rev, gigs = d["events"], d["reveal"], d["gigs"]
    desk = Desk(geo, Config(), 8, 0, d["roster"])
    reqs = {r["request"]["id"]: r["request"] for r in rev["requests"]}
    for rid, q in reqs.items():
        desk.requests[rid] = q
    gig_orders = {g["id"]: [s["orderId"] for s in g["stops"] if s["kind"] == "pickup"] for g in gigs}
    for e in ev:
        if e["kind"] == "picked_up":
            gig_orders.setdefault(e["gigId"], [e["orderId"]])
    pnl = collections.defaultdict(lambda: collections.Counter())
    for e in ev:
        if e["kind"] != "ledger":
            continue
        line = e["line"]
        oid = line.get("orderId")
        if not oid and line.get("gigId"):
            os_ = gig_orders.get(line["gigId"], [])
            oid = os_[0] if os_ else None
        if oid:
            pnl[oid][line["kind"]] += line["cents"] / 100
    won = {e["order"]["id"]: e["order"] for e in ev if e["kind"] == "order_won"}
    cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    for oid, o in won.items():
        if oid in cancelled:
            continue
        q = reqs[oid]
        f = desk.ontime.features(q, o["deadline"], o["option"])
        p, _ = desk.ontime.p_ok(q, o["deadline"], o["option"])
        lp = next(x["listPriceCents"] for x in q["options"] if x["kind"] == o["option"])
        m = pnl[oid]
        rows.append(dict(run=run[-9:], oid=oid, opt=o["option"], p=p, slack=f["slack"], drive=geo.drive(q["legs"][0]["pickup"]["placeId"], q["legs"][0]["delivery"]["placeId"]),
                         sup_p=desk.supply_near(q["legs"][0]["pickup"]["placeId"], 30), sup_d=desk.supply_near(q["legs"][0]["delivery"]["placeId"], 30),
                         price=o["priceCents"] / 100, list=lp / 100, ref=q["referenceFeeCents"] / 100, fee=-m["driver_fee"], loss=-(m["late_refund"] + m["undelivered_penalty"] + m["failed_visit"] + m["release_fee"] + m["waiting"] + m["fine"]),
                         margin=sum(m.values()), late=m["late_refund"] < 0 or m["undelivered_penalty"] < 0, premium=f["premium"] > 0, hour=(q["respondBy"] % 1440) // 60, day=q["respondBy"] // 1440))
json.dump(rows, open("data/pnl_rows.json", "w"))
print("orders", len(rows), "margin", round(sum(r["margin"] for r in rows)), "fee/ref mean", round(sum(r["fee"] for r in rows) / sum(r["ref"] for r in rows), 3))


def tab(name, key, edges):
    out = []
    for lo, hi in zip(edges, edges[1:]):
        xs = [r for r in rows if lo <= key(r) < hi]
        if xs:
            out.append(f"[{lo},{hi}) n={len(xs)} m/order={sum(r['margin'] for r in xs)/len(xs):6.1f} fee/ref={sum(r['fee'] for r in xs)/sum(r['ref'] for r in xs):.2f} late={sum(r['late'] for r in xs)/len(xs):.2f}")
    print(name)
    for o in out:
        print("   ", o)


tab("p_ok", lambda r: r["p"], [0, 0.8, 0.9, 0.95, 0.98, 1.01])
tab("slack h", lambda r: r["slack"], [-99, 3, 5, 7, 9, 12, 24, 99])
tab("drive min", lambda r: r["drive"], [0, 60, 120, 180, 240, 360, 900])
tab("supply pickup 30km", lambda r: r["sup_p"], [0, 5, 15, 40, 100, 2000])
tab("supply delivery 30km", lambda r: r["sup_d"], [0, 5, 15, 40, 100, 2000])
tab("price/list", lambda r: r["price"] / r["list"], [0, 1.2, 1.4, 1.6, 1.8, 3])
tab("hour", lambda r: r["hour"], [0, 10, 12, 14, 16, 18, 24])
tab("day", lambda r: r["day"], [0, 1, 2, 3, 4, 5])
tab("option", lambda r: ["same_day", "next_day", "within_3_days"].index(r["opt"]), [0, 1, 2, 3])
tab("premium", lambda r: r["premium"], [0, 1, 2])
