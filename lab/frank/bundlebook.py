"""Which posted bundles get a driver? By chain length, transit, start hour, lead time.

usage: python lab/frank/bundlebook.py data/runs/<tag>/*-L8
"""
import gzip, json, sys, collections
sys.path.insert(0, "src")
from spreadbot.geo import Geo
geo = Geo(json.load(open("data/map.json")))
rows = []
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    won = {e["order"]["id"]: e["order"] for e in d["events"] if e["kind"] == "order_won"}
    booked = set()
    for g in d["gigs"]:
        cars = tuple(s["orderId"] for s in g["stops"] if s["kind"] == "pickup")
        if g.get("driverId") and len(set(cars)) == 2:
            booked.add(cars)
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        if code != "BUNDLE":
            continue
        a, b = rest.split()[0].split("+")
        A, B = won[a]["legs"][0], won[b]["legs"][0]
        dA = geo.drive(A["pickup"]["placeId"], A["delivery"]["placeId"]); tr = geo.drive(A["delivery"]["placeId"], B["pickup"]["placeId"]); dB = geo.drive(B["pickup"]["placeId"], B["delivery"]["placeId"])
        start = max(int(t), A["pickup"]["window"]["from"])
        rows.append(dict(ok=(a, b) in booked, tot=dA + tr + dB, tr=tr, hour=(start % 1440) // 60, lead=(start - int(t)) / 60,
                         same=A["pickup"]["placeId"] == B["delivery"]["placeId"], dA=dA, dB=dB))
print("bundles", len(rows), "booked", sum(r["ok"] for r in rows) / len(rows))
def by(key, edges):
    for lo, hi in zip(edges, edges[1:]):
        rs = [r for r in rows if lo <= r[key] < hi]
        if rs:
            print(f"  {key} {lo}-{hi}: n={len(rs):4d} booked {sum(r['ok'] for r in rs)/len(rs):.2f}")
by("tot", [0, 120, 240, 360, 480, 600, 720])
by("tr", [0, 1, 15, 30, 60, 999])
by("hour", [0, 7, 9, 11, 13, 15, 24])
by("lead", [0, 2, 6, 12, 18, 30, 200])
rs = [r for r in rows if r["same"]]; print("  round trip (B ends where A started):", len(rs), sum(r["ok"] for r in rs) / max(1, len(rs)))
