"""Price ladder: win rate against quote/list, per seed, from runs played with --flag dealer.ladder=0.7.
Monday and Tuesday only, before trust and the competitor's reactions blur it.

    PYTHONPATH=src .venv/bin/python lab/a/price_ladder.py <tag>
"""
import json
import os
import sys
from collections import defaultdict

from spread.client import Client

DAY = 1440


def reveal(client, run_dir, world_id):
    path = os.path.join(run_dir, "reveal.json")
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(client.world(world_id).reveal(), f)
    return json.load(open(path))


def main(tag):
    client = Client()
    rows = [json.loads(line) for line in open(f"data/results/{tag}.jsonl")]
    bins = [1.0 + 0.05 * k for k in range(15)]
    total = defaultdict(lambda: [0, 0])
    print("seed      " + "".join(f"{b:>6.2f}" for b in bins))
    for row in rows:
        rev = reveal(client, os.path.join("data/runs", row["worldId"]), row["worldId"])
        seen = defaultdict(lambda: [0, 0])
        for r in rev["requests"]:
            if r["quote"] is None or r["request"]["arrivedAt"] >= 2 * DAY:
                continue
            kind, price = next(iter(r["quote"].items()))
            listed = next(o["listPriceCents"] for o in r["request"]["options"] if o["kind"] == kind)
            b = min(len(bins) - 1, int((price / listed - 1.0) / 0.05))
            seen[b][0] += r["outcome"] == "won"
            seen[b][1] += 1
            total[b][0] += r["outcome"] == "won"
            total[b][1] += 1
        print(f"{row['seed']:<10}" + "".join(f"{seen[k][0] / seen[k][1]:>6.0%}" if seen[k][1] else "     -" for k in range(len(bins))))
    print("all       " + "".join(f"{total[k][0] / total[k][1]:>6.0%}" if total[k][1] else "     -" for k in range(len(bins))))
    print("n         " + "".join(f"{total[k][1]:>6}" for k in range(len(bins))))


if __name__ == "__main__":
    main(sys.argv[1])
