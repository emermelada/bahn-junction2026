"""How many won cars could ride in two-car chains, if we held cars back to pair them?

usage: python lab/frank/chainpot.py KM data/runs/<tag>/*-L8
"""
import gzip, json, sys
sys.path.insert(0, "src")
from spreadbot.geo import Geo
geo = Geo(json.load(open("data/map.json")))
KM = float(sys.argv[1]); MAXD = int(sys.argv[2]); LEAD = int(sys.argv[3]); del sys.argv[2:4]
tot_cars = tot_pair = 0
save = 0.0
for run in sys.argv[2:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    canc = {e["orderId"] for e in d["events"] if e["kind"] == "order_cancelled"}
    won = [(e["at"], e["order"]) for e in d["events"] if e["kind"] == "order_won" and e["order"]["id"] not in canc]
    cars = []
    for at, o in won:
        if len(o["legs"]) != 1:
            continue
        L = o["legs"][0]
        p, q = L["pickup"]["placeId"], L["delivery"]["placeId"]
        cars.append(dict(id=o["id"], at=at, p=p, q=q, f=L["pickup"]["window"]["from"], t=L["pickup"]["window"]["to"],
                         dl=o["deadline"], dr=geo.drive(p, q), ref=reqs[o["id"]]["referenceFeeCents"], priv=L["pickup"]["privateAddress"]))
    tot_cars += len(cars)
    def ok(A, B):
        if geo.air(A["q"], B["p"]) > KM:
            return None
        post = max(A["at"], B["at"]) + 30
        start = max(post + LEAD, A["f"])
        a_del = start + A["dr"]
        if a_del > A["dl"] - 60 or A["priv"]:
            return None
        bp = max(a_del + geo.drive(A["q"], B["p"]), B["f"])
        if bp > B["t"] or bp + B["dr"] > B["dl"] - 60:
            return None
        if A["dr"] + geo.drive(A["q"], B["p"]) + B["dr"] > MAXD or bp - a_del > 180:  # chain must be one working day, little waiting
            return None
        return A["ref"] + B["ref"]
    pairs = []
    for A in cars:
        for B in cars:
            if A is not B:
                v = ok(A, B)
                if v:
                    pairs.append((-v, A["id"], B["id"]))
    pairs.sort()
    used = set()
    for v, a, b in pairs:
        if a in used or b in used:
            continue
        used |= {a, b}
        tot_pair += 2
        save += -v
n = len(sys.argv[2:])
print(f"km {KM}: single-leg cars/week {tot_cars/n:.0f}, in chains {tot_pair/n:.0f} ({tot_pair/tot_cars:.0%}), ref of chained cars/week {save/n/100:.0f} eur")
