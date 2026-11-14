"""At a given minute: our open orders by state (booked / posted unbooked / not posted yet), and how many ended on time.
usage: python lab/build/openstate.py MINUTE RUN_DIR ..."""
import gzip, json, sys, collections
T = int(sys.argv[1])
for run in sys.argv[2:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    truth = {o["orderId"]: o for o in d["reveal"]["orders"]}
    gig_orders = {g["id"]: {s["orderId"] for s in g["stops"]} for g in d["gigs"]}
    posted = collections.defaultdict(lambda: 10 ** 9)
    for g in d["gigs"]:
        for o in gig_orders[g["id"]]:
            posted[o] = min(posted[o], g["postedAt"])
    held_by = collections.defaultdict(int)  # orders -> number of bookings live at T
    live = collections.defaultdict(set)
    won, canc, delivered = {}, set(), {}
    for e in sorted(d["events"], key=lambda e: e["seq"]):
        if e["at"] > T:
            if e["kind"] == "order_cancelled":
                canc.add(e["orderId"])
            continue
        k = e["kind"]
        if k == "order_won":
            won[e["order"]["id"]] = e["order"]
        elif k == "gig_booked":
            for o in gig_orders.get(e["gigId"], ()):
                live[o].add(e["gigId"])
        elif k in ("gig_dropped", "no_show", "gig_expired"):
            for o in gig_orders.get(e["gigId"], ()):
                live[o].discard(e["gigId"])
        elif k == "order_cancelled":
            canc.add(e["orderId"])
    c = collections.Counter()
    for oid, o in won.items():
        if oid in canc or oid not in truth:
            continue
        t = truth[oid]
        dead = lambda l: min(o["deadline"], l["noteDeadline"]) if l["noteDeadline"] else o["deadline"]
        if all(l["deliveredAt"] is not None and l["deliveredAt"] <= T for l in t["legs"]):
            continue  # done before T
        late = not all(l["deliveredAt"] is not None and l["deliveredAt"] <= dead(l) for l in t["legs"])
        st = "booked" if live[oid] else ("posted-unbooked" if posted[oid] <= T else "not-posted")
        c[st, "n"] += 1
        c[st, "late"] += late
    print(run.split("/")[-2], run.split("/")[-1][:6], " ".join(f"{s}: {c[s,'late']}/{c[s,'n']} late" for s in ("booked", "posted-unbooked", "not-posted")))
