"""Why were cars late? Classifies each late or undelivered order of a run from its log.

    python3 lab/b/late_why.py data/runs/<world id>
"""
import json
import sys
from collections import Counter, defaultdict

DAY = 1440


def main(run_dir):
    orders, money, booked, events = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    gig_orders = {}
    for line in map(json.loads, open(f"{run_dir}/log.jsonl")):
        if line["t"] == "res" and line["a"]["type"] == "post" and line["r"]["ok"]:
            gig_orders[line["r"]["id"]] = {s["orderId"] for s in line["a"]["stops"]}
        if line["t"] != "ev":
            continue
        e = line["e"]
        if e["kind"] in ("order_won", "order_changed"):
            orders[e["order"]["id"]] = e["order"]
        elif e["kind"] == "ledger" and e["line"]["orderId"]:
            money[e["line"]["orderId"]].append((e["line"]["kind"], e["line"]["cents"]))
        elif e["kind"] in ("gig_booked", "gig_dropped", "no_show", "driver_late", "gig_expired", "deadline_close", "visit_failed"):
            for oid in gig_orders.get(e.get("gigId"), {e.get("orderId")}):
                events[oid].append((e["at"], e["kind"]))
    why = Counter()
    by_day = defaultdict(Counter)
    for oid, o in orders.items():
        if o["status"] == "cancelled":
            continue
        kinds = [k for k, _ in money[oid]]
        day = o["legs"][0]["pickup"]["window"]["from"] // DAY
        late = "late_refund" in kinds or "undelivered_penalty" in kinds
        by_day[day]["won"] += 1
        if not late:
            continue
        by_day[day]["late"] += 1
        ev = [k for _, k in sorted(events[oid])]
        first_book = next((at for at, k in sorted(events[oid]) if k == "gig_booked"), None)
        if "undelivered_penalty" in kinds:
            why["undelivered"] += 1
        elif first_book is None:
            why["never booked?"] += 1
        elif "visit_failed" in ev:
            why["visit failed"] += 1
        elif first_book > o["lastPickupAt"]:
            why["booked after lastPickupAt"] += 1
        elif "gig_dropped" in ev or "no_show" in ev:
            why["drop/no-show"] += 1
        elif "driver_late" in ev:
            why["driver late"] += 1
        else:
            why["booked in time, still late"] += 1
    print(dict(why))
    for day in sorted(by_day):
        c = by_day[day]
        print(f"day {day}: won {c['won']:>4}  late {c['late']:>4}  ({c['late'] / c['won']:.0%})")


if __name__ == "__main__":
    main(sys.argv[1])
