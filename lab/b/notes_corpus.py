"""Notes corpus: every won order with a note, its stated request and the truth from the reveal, from the
finished practice runs in data/runs. Writes data/notes_corpus.jsonl (one line per leg).

    PYTHONPATH=src .venv/bin/python lab/b/notes_corpus.py
"""
import json
import os

from spread.client import Client, SpreadError


def main():
    client = Client()
    rows = 0
    with open("data/notes_corpus.jsonl", "w") as out:
        for world_id in sorted(os.listdir("data/runs")):
            run = os.path.join("data/runs", world_id)
            if not os.path.exists(os.path.join(run, "score.json")):
                continue
            path = os.path.join(run, "reveal.json")
            if not os.path.exists(path):
                try:
                    reveal = client.world(world_id).reveal()
                except SpreadError:
                    continue
                with open(path, "w") as f:
                    json.dump(reveal, f)
            reveal = json.load(open(path))
            requests = {r["request"]["id"]: r for r in reveal["requests"]}
            for order in reveal["orders"]:
                r = requests.get(order["orderId"])
                if r is None or r["request"]["note"] is None:
                    continue
                req = r["request"]
                for i, truth in enumerate(order["legs"]):
                    leg = req["legs"][i]
                    out.write(json.dumps({
                        "world": world_id, "order": order["orderId"], "leg": i, "arrivedAt": req["arrivedAt"],
                        "note": req["note"]["text"], "language": req["note"]["language"], "option": r["option"],
                        "stated": {"readyAt": leg["pickup"]["window"]["from"], "pickupHours": leg["pickup"]["hours"],
                                   "deliveryHours": leg["delivery"]["hours"], "deadlines": {o["kind"]: o["deadline"] for o in req["options"]}},
                        "truth": truth}) + "\n")
                    rows += 1
    print(rows, "legs with notes")


if __name__ == "__main__":
    main()
