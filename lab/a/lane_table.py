"""Lane table: the part of the competitor's price that holds in every world (RULES, HANDBOOK "Dealers compare
prices": a lane factor, partly the same in every world). Fitted on every finished level 8 week in data/runs.

Model: P(win) = sigmoid(a_lane - beta * ratio), ratio = our lowest quoted price / list. beta and a global a0
first, then each lane's a with a Gaussian pull towards a0 (thin lanes stay near the average). The shift
(a_lane - a0) / beta is how much higher (or lower) a ratio wins equally often on that lane.

    python3 lab/a/lane_table.py      # writes src/spreadbot/dealer/lanes.json
"""
import glob
import json
import math
import os

PULL = 30.0  # prior weight: a lane needs about this many quotes to move halfway from the average
LO, HI = 1.0, 1.8  # quotes outside this ratio range are declines or noise


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def collect():
    data = []  # (lane, ratio, won)
    for d in glob.glob("data/runs/*/"):
        if not os.path.exists(d + "meta.json") or json.load(open(d + "meta.json")).get("level") != 8:
            continue
        reqs, quoted = {}, {}
        for line in map(json.loads, open(d + "log.jsonl")):
            if line["t"] == "res" and line["a"]["type"] == "quote" and line["a"]["requestId"] in reqs:
                r = reqs[line["a"]["requestId"]]
                listed = {o["kind"]: o["listPriceCents"] for o in r["options"]}
                ratio = min(p / listed[k] for k, p in line["a"]["prices"].items())
                if LO <= ratio <= HI:
                    quoted[r["id"]] = ratio
            elif line["t"] == "ev":
                e = line["e"]
                if e["kind"] == "price_request":
                    reqs[e["request"]["id"]] = e["request"]
                elif e["kind"] in ("order_won", "order_lost"):
                    rid = e["order"]["id"] if e["kind"] == "order_won" else e["requestId"]
                    if rid in quoted:
                        r = reqs[rid]
                        lane = r["legs"][0]["pickup"]["placeId"] + ">" + r["legs"][-1]["delivery"]["placeId"]
                        data.append((lane, quoted[rid], e["kind"] == "order_won"))
    return data


def fit_lane(rows, a0, beta, steps=20):
    a = a0
    for _ in range(steps):
        g = -(a - a0) / PULL * 4  # Gaussian prior; 4 = 1 / max p(1-p), so PULL counts in quotes
        h = 4 / PULL
        for r, y in rows:
            p = sigmoid(a - beta * r)
            g += y - p
            h += p * (1 - p)
        a += g / h
    return a


BETA = 8.0  # the price ladder (random ratios inside one week, docs/log price ladder): win 85% at 1.1x, 10% at 1.6x


def fit_a0(data, beta, steps=20):
    a = beta * 1.3  # start near 50% wins at 1.3x, where sigmoid has slope
    for _ in range(steps):
        g = h = 0.0
        for _, r, y in data:
            p = sigmoid(a - beta * r)
            g += y - p
            h += p * (1 - p)
        a += g / h
    return a


def main():
    data = collect()
    lanes = {}
    for lane, r, y in data:
        lanes.setdefault(lane, []).append((r, y))
    a0 = fit_a0(data, BETA)
    a = {lane: fit_lane(rows, a0, BETA) for lane, rows in lanes.items()}
    shift = {lane: round((a[lane] - a0) / BETA, 4) for lane in sorted(lanes)}
    out = {"beta": BETA, "a0": round(a0, 3), "quotes": len(data), "shift": shift,
           "n": {lane: len(rows) for lane, rows in sorted(lanes.items())}}
    with open("src/spreadbot/dealer/lanes.json", "w") as f:
        json.dump(out, f, indent=0, sort_keys=True)
    s = sorted(shift.values())
    print(f"{len(data)} quotes, {len(shift)} lanes, beta {BETA}, 50% win at ratio {a0 / BETA:.2f}")
    print(f"shift p10 {s[len(s) // 10]:+.3f}  median {s[len(s) // 2]:+.3f}  p90 {s[9 * len(s) // 10]:+.3f}")


if __name__ == "__main__":
    main()
