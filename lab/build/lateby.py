"""Late cars by deadline day, by won day, and booking history (reveal.json.gz of each run).
usage: python lab/build/lateby.py data/runs/<tag>/<seed>-L8 ..."""
import gzip, json, sys, collections
DAY = 1440
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    truth = {o["orderId"]: o for o in d["reveal"]["orders"]}
    won, cancelled = {}, set()
    booked_at = collections.defaultdict(list)
    drops = collections.Counter()
    gig_orders = {}
    for g in d["gigs"]:
        gig_orders[g["id"]] = {s["orderId"] for s in g["stops"]}
    for e in d["events"]:
        k = e["kind"]
        if k == "order_won":
            won[e["order"]["id"]] = (e["at"], e["order"])
        elif k == "order_cancelled":
            cancelled.add(e["orderId"])
        elif k == "gig_booked":
            for o in gig_orders.get(e["gigId"], ()):
                booked_at[o].append(e["at"])
        elif k == "gig_dropped":
            for o in gig_orders.get(e["gigId"], ()):
                drops[o] += 1
    byday = collections.defaultdict(lambda: [0, 0])
    bywon = collections.defaultdict(lambda: [0, 0])
    bybook = collections.defaultdict(lambda: [0, 0])
    for oid, (at, o) in won.items():
        if oid in cancelled or oid not in truth:
            continue
        t = truth[oid]
        dead = lambda l: min(o["deadline"], l["noteDeadline"]) if l["noteDeadline"] else o["deadline"]
        late = not all(l["deliveredAt"] is not None and l["deliveredAt"] <= dead(l) for l in t["legs"])
        dd = o["deadline"] // DAY
        byday[dd][0] += 1; byday[dd][1] += late
        bywon[at // DAY][0] += 1; bywon[at // DAY][1] += late
        b = booked_at.get(oid)
        if not b:
            k = "never booked"
        else:
            lead = o["lastPickupAt"] - b[0]
            k = "drop" if drops[oid] else ("bk<4h" if lead < 240 else "bk4-12h" if lead < 720 else "bk12-24h" if lead < 1440 else "bk>24h")
        bybook[k][0] += 1; bybook[k][1] += late
    n = sum(v[0] for v in byday.values()); L = sum(v[1] for v in byday.values())
    print(f"{run}: {n} orders, {L} late ({1-L/n:.3f} on time), drivers {len(d['roster'])}")
    print("  by deadline day:", {k: f"{v[1]}/{v[0]}" for k, v in sorted(byday.items())})
    print("  by won day     :", {k: f"{v[1]}/{v[0]}" for k, v in sorted(bywon.items())})
    print("  by booking     :", {k: f"{v[1]}/{v[0]}" for k, v in sorted(bybook.items())})
