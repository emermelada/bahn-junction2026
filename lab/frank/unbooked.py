"""For orders never booked in time: did drivers view them? at what fee? vs booked orders."""
import collections, gzip, json, sys, statistics as st
sys.path.insert(0, "src")
from spreadbot.geo import Geo
geo = Geo(json.load(open("data/map.json")))
A = collections.defaultdict(list)
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    ev = d["events"]; homes = collections.Counter(x["homePlaceId"] for x in d["roster"])
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    truth = {o["orderId"]: o["legs"] for o in d["reveal"]["orders"]}
    won = {e["order"]["id"]: (e["order"], e["at"]) for e in ev if e["kind"] == "order_won"}
    g2o = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code == "GIG": g2o[rest.split()[0]] = rest.split()[1]
    views = collections.defaultdict(set); booked = collections.defaultdict(int); expired = set()
    for e in ev:
        o = g2o.get(e.get("gigId", ""))
        if not o: continue
        if e["kind"] == "gig_viewed": views[o].add(e["driverId"])
        if e["kind"] == "gig_booked": booked[o] += 1
        if e["kind"] == "gig_expired": expired.add(o)
    for oid, (o, at) in won.items():
        if oid not in truth: continue
        tl = truth[oid]
        dead = min([o["deadline"]] + [t["noteDeadline"] for t in tl if t["noteDeadline"]])
        ok = all(t["deliveredAt"] is not None and t["deliveredAt"] <= dead for t in tl)
        q = reqs[oid]; L = q["legs"][0]
        cls = "ontime" if ok else ("unbooked" if (not booked[oid] or oid in expired) else "other")
        p = L["pickup"]["placeId"]
        sup = sum(c for h, c in homes.items() if geo.air(h, p) <= 30)
        A[cls].append(dict(views=len(views[oid]), sup=sup, drive=geo.drive(p, L["delivery"]["placeId"]), slack=(o["lastPickupAt"] - at) / 60, hour=(at % 1440) // 60, day=at // 1440))
for cls, xs in A.items():
    print(cls, len(xs), "views med", st.median(x["views"] for x in xs), "zero-view share", round(sum(x["views"] == 0 for x in xs) / len(xs), 2),
          "sup30 med", st.median(x["sup"] for x in xs), "drive med", st.median(x["drive"] for x in xs), "slack(h) med", round(st.median(x["slack"] for x in xs), 1),
          "hour", collections.Counter(x["hour"] for x in xs).most_common(4), "day", sorted(collections.Counter(x["day"] for x in xs).items()))
