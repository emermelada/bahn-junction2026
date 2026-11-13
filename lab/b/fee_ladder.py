"""Fee ladder: chance a gig is booked before its last pickup, and within an hour, against flat fee / typical fee,
by slack at posting. From runs played with --flag driver.fee_ladder=1.2 (flat fees in [0.8, 2.0]).

    python3 lab/b/fee_ladder.py <tag>
"""
import json
import sys
from collections import defaultdict


def main(tag):
    bins = defaultdict(lambda: [0, 0, 0])  # (slack class, fee bin) -> [booked in time, booked within 60 min, posted]
    for row in map(json.loads, open(f"data/results/{tag}.jsonl")):
        posted, ratio, slack, booked, orders, refs = {}, {}, {}, {}, {}, {}
        for line in map(json.loads, open(f"data/runs/{row['worldId']}/log.jsonl")):
            if line["t"] == "now":
                now = line["now"]
            elif line["t"] == "res" and line["a"]["type"] == "post" and line["r"]["ok"]:
                g, a = line["r"]["id"], line["a"]
                oid = a["stops"][0]["orderId"]
                cars = sum(s["kind"] == "pickup" for s in a["stops"])
                posted[g] = now
                ratio[g] = a["schedule"][0]["feeCents"] / (refs[oid][0] * cars / refs[oid][1])
                slack[g] = orders[oid]["lastPickupAt"] - now
            elif line["t"] == "ev":
                e = line["e"]
                if e["kind"] == "price_request":
                    refs[e["request"]["id"]] = (e["request"]["referenceFeeCents"], len(e["request"]["legs"]))
                elif e["kind"] in ("order_won", "order_changed"):
                    orders[e["order"]["id"]] = e["order"]
                elif e["kind"] == "gig_booked" and e["gigId"] not in booked:
                    booked[e["gigId"]] = e["at"]
        for g in posted:
            s = "slack<8h" if slack[g] < 480 else "slack<24h" if slack[g] < 1440 else "slack>=24h"
            b = bins[(s, min(11, int((ratio[g] - 0.8) / 0.1)))]
            b[2] += 1
            b[0] += g in booked and booked[g] <= posted[g] + slack[g]
            b[1] += g in booked and booked[g] <= posted[g] + 60
    for s in ("slack<8h", "slack<24h", "slack>=24h"):
        print(s)
        for k in range(12):
            t, h, n = bins[(s, k)]
            if n:
                print(f"  fee {0.8 + 0.1 * k:.1f}-{0.9 + 0.1 * k:.1f}x  n {n:>3}  in time {t / n:5.0%}  within 1h {h / n:5.0%}")


if __name__ == "__main__":
    main(sys.argv[1])
