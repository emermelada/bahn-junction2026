"""Why were orders late? Per won order: first fee ratio, drops, failed visits, how late."""
import collections, gzip, json, sys
d = json.load(gzip.open(sys.argv[1], "rt"))
ev, rev, gigs = d["events"], d["reveal"], d["gigs"]
reqs = {r["request"]["id"]: r["request"] for r in rev["requests"]}
truth = {o["orderId"]: o["legs"] for o in rev["orders"]}
won = {e["order"]["id"]: e["order"] for e in ev if e["kind"] == "order_won"}
cancelled = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
gig_orders = {g["id"]: g["stops"][0]["orderId"] for g in gigs}
per = collections.defaultdict(lambda: collections.Counter())
for e in ev:
    if e["kind"] in ("gig_dropped", "no_show", "driver_late", "gig_expired", "visit_failed", "deadline_close"):
        oid = e.get("orderId") or gig_orders.get(e.get("gigId"))
        if oid: per[oid][e["kind"] + (":" + e["reason"] if e["kind"] == "visit_failed" else "")] += 1
first = {}
for g in sorted(gigs, key=lambda g: g["postedAt"]):
    first.setdefault(g["stops"][0]["orderId"], g)
rows = []
for oid, o in won.items():
    if oid in cancelled or oid not in truth: continue
    q = reqs[oid]
    dl = [t["deliveredAt"] for t in truth[oid]]
    noteDl = min([t["noteDeadline"] for t in truth[oid] if t["noteDeadline"]] or [o["deadline"]])
    dead = min(o["deadline"], noteDl)
    late = None if any(x is None for x in dl) else max(dl) - dead
    g = first.get(oid)
    f0 = g["schedule"][0]["feeCents"] / (q["referenceFeeCents"] * sum(1 for s in g["stops"] if s["kind"] == "pickup") / len(q["legs"])) if g else None
    rows.append((oid, o["option"], round(f0, 1) if f0 else None, late, dict(per[oid]), q["note"]["text"][:50] if q["note"] else ""))
L = [r for r in rows if r[3] is None or r[3] > 0]
print(len(rows), "orders,", len(L), "late")
c = collections.Counter()
for r in L:
    ev_ = r[4]
    cause = "failed" if any(k.startswith("visit_failed") for k in ev_) else "dropped" if "gig_dropped" in ev_ or "no_show" in ev_ else "expired" if "gig_expired" in ev_ else "warned" if "deadline_close" in ev_ else "driver_late" if "driver_late" in ev_ else "other"
    c[cause] += 1
print(c)
print("late by first fee ratio:", sorted(collections.Counter(r[2] for r in L).items(), key=str), "all:", sorted(collections.Counter(r[2] for r in rows).items(), key=str))
for r in L[:25]: print(r)
