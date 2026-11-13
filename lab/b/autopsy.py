"""Starter autopsy: where do late cars come from? Per pickup town: drivers living near it, cars won, on-time share.

    PYTHONPATH=src .venv/bin/python lab/b/autopsy.py data/runs/<world id>
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

from spread.client import Client


def km(a, b):
    """Straight-line km between two places (the app's 30 km notification radius is straight-line)."""
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def main(run_dir):
    client = Client()
    meta = json.load(open(os.path.join(run_dir, "meta.json")))
    world = client.world(meta["worldId"])
    places = {p["id"]: p for p in client.map()["places"]}
    homes = Counter(d["homePlaceId"] for d in world.roster())
    near = {t: sum(n for h, n in homes.items() if km(places[t], places[h]) <= 30) for t in places}
    orders, late = {}, Counter()
    for line in map(json.loads, open(os.path.join(run_dir, "log.jsonl"))):
        if line["t"] == "ev" and line["e"]["kind"] in ("order_won", "order_changed"):
            orders[line["e"]["order"]["id"]] = line["e"]["order"]
        if line["t"] == "ev" and line["e"]["kind"] == "ledger" and line["e"]["line"]["kind"] in ("late_refund", "undelivered_penalty"):
            late[line["e"]["line"]["orderId"]] += 1
    by_town = defaultdict(lambda: [0, 0])
    for oid, o in orders.items():
        if o["status"] == "cancelled":
            continue
        town = o["legs"][0]["pickup"]["placeId"]
        by_town[town][0] += 1
        by_town[town][1] += oid not in late
    print(f"{meta['seed']} L{meta['level']}: {sum(homes.values())} drivers")
    print(f"{'town':<16}{'drivers':>8}{'near30':>8}{'won':>6}{'ontime':>8}")
    for town, (won, ok) in sorted(by_town.items(), key=lambda kv: -kv[1][0]):
        print(f"{town:<16}{homes[town]:>8}{near[town]:>8}{won:>6}{ok / won:>8.0%}")


if __name__ == "__main__":
    main(sys.argv[1])
