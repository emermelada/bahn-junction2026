"""Late-order causes from the events (gig ids mapped to orders via the decision log)."""
import collections, gzip, json, sys
tot = collections.Counter()
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev = d["events"]
    truth = {o["orderId"]: o["legs"] for o in d["reveal"]["orders"]}
    won = {e["order"]["id"]: e["order"] for e in ev if e["kind"] == "order_won"}
    canc = {e["orderId"] for e in ev if e["kind"] == "order_cancelled"}
    g2o = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "GIG":
            g2o[rest.split()[0]] = rest.split()[1]
    per = collections.defaultdict(collections.Counter)
    for e in ev:
        oid = e.get("orderId") or g2o.get(e.get("gigId", ""))
        if oid and e["kind"] in ("gig_dropped", "no_show", "driver_late", "gig_expired", "visit_failed", "deadline_close", "gig_booked", "order_changed"):
            per[oid][e["kind"]] += 1
    c = collections.Counter()
    n = 0
    for oid, o in won.items():
        if oid in canc or oid not in truth: continue
        n += 1
        tl = truth[oid]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        if all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl): continue
        p = per[oid]
        if p["visit_failed"]: k = "failed_visit"
        elif p["order_changed"]: k = "changed"
        elif not p["gig_booked"] or p["gig_expired"]: k = "never_booked_in_time"
        elif p["gig_dropped"] or p["no_show"]: k = "dropped"
        elif p["driver_late"]: k = "driver_late"
        else: k = "booked_but_late"
        c[k] += 1
    tot += c
    print(run[-9:], n, dict(c))
print("total", dict(tot))
