"""Dispatch, v0 stub: the kit starter's behaviour, written as a reconciler over State.

Each call compares what should be on the road with what is, and returns the actions that close the gap:
every undelivered leg of a live order sits on a live gig; a gig of an order whose plan changed is posted
again; once the deadline warning comes, the order's open gigs go at steep fees. Because it reads only
State, the same code serves a normal step and a restart."""
from __future__ import annotations

from typing import Optional

from spread.types import Action, FeeStep, Order, StopRef

from spreadbot.core.rng import rng
from spreadbot.core.state import State, legs_of
from spreadbot.driver.chains import chain_offers
from spreadbot.driver.flags import FLAGS
from spreadbot.notes.reader import needs_manual, needs_plates, window_from_note

HOUR, DAY = 60, 24 * 60
MID_SLACK = 8 * HOUR  # fee ladder: with 8-24 h to the last pickup, gigs near the typical fee still booked in time
SPLIT_MINUTES = 12 * HOUR  # RULES: a gig with more than one car may plan at most 12 hours of driving
EXPLICIT_MIN = 30  # a pickup window shorter than this is not worth posting: no driver could plan around it
DROP_RAISE_LEAD = 12 * HOUR  # a gig given back with less than this to its last pickup is repriced at once
BUNDLE_REPOST_AGE = 180  # minutes: an open single this young has shown few drivers its fee, so re-posting it as a chain costs little
BUNDLE_BUFFER = 60  # minutes of spare time a chain keeps before each car's deadline, for real driving times
REFUSED_BACKOFF = 30  # minutes before we try a refused post again; refusals name a window, so the next try usually differs


def dispatch(state: State, now: int) -> list[Action]:
    actions: list[Action] = []
    waiting: list[Order] = []  # new single cars held back a while to find a partner for a two-car chain
    for order in state.active_orders():
        oid = order["id"]
        gig_ids = list(dict.fromkeys(state.gig_of[(oid, leg)] for leg in state.undelivered(order) if (oid, leg) in state.gig_of))
        freed: set[int] = set()
        for gid in gig_ids:
            gig = state.gigs[gid]
            if gig["status"] != "open":
                continue
            if oid in state.changed and gig["postedAt"] < state.changed[oid]:
                actions.append({"type": "withdraw", "gigId": gid})
                freed.update(leg for o, leg in legs_of(gig) if o == oid)
                state.log(now, "withdraw_changed", gid, order=oid)
            elif oid in state.urgent and gig["scheduledAt"] < state.urgent[oid]:
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now, base=gig_base(state, gig))})
                state.log(now, "reprice_urgent", gid, order=oid)
            elif FLAGS["drop_raise"] and oid not in state.urgent and dropped_at(state, gid) > gig["scheduledAt"] \
                    and order["lastPickupAt"] - now < DROP_RAISE_LEAD:
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now, raised=FLAGS["drop_raise"],
                                                                                  base=gig_base(state, gig))})
                state.log(now, "reprice_dropped", gid, order=oid)
            elif oid not in state.urgent and (ratio := raise_due(order, gig, now)):
                actions.append({"type": "reprice", "gigId": gid, "schedule": fees(state, order, _cars(gig), now, raised=ratio,
                                                                                  base=gig_base(state, gig))})
                state.log(now, "reprice_early", gid, order=oid, ratio=ratio)
        need = [leg for leg in state.undelivered(order) if (oid, leg) not in state.gig_of or leg in freed]
        need = [leg for leg in need if not _backing_off(state, (oid, leg), now)]
        if not need:
            continue
        if FLAGS["bundle"] and need == [0] and pairable(state, order, now):
            waiting.append(order)
            continue
        groups = [need] if len(need) == 1 or drive_minutes(state, order, need) <= SPLIT_MINUTES else [[leg] for leg in need]
        for legs in groups:
            actions.append(post(state, order, legs, now))
            state.log(now, "post", oid, legs=legs, retry=any((oid, leg) in state.failures for leg in legs))
    paired: set[str] = set()
    if waiting:
        chains, paired = bundles(state, waiting, now)
        actions += chains
    for order in waiting:  # cars without a partner go out alone at once
        if order["id"] not in paired:
            actions.append(post(state, order, [0], now))
            state.log(now, "post", order["id"], legs=[0], retry=False)
    return actions + chain_offers(state, now)


def post(state: State, order: Order, legs: list[int], now: int) -> Action:
    oid = order["id"]
    reasons = [r for leg in legs for r in state.failures.get((oid, leg), [])]
    note = state.requests[oid]["note"] if FLAGS["read_notes"] else None
    audience = {"experienced": any(leg["car"]["premium"] for leg in order["legs"]),
                "manualLicence": "licence" in reasons or needs_manual(note)}
    stops: list[StopRef] = []
    for leg in legs:
        car, pickup, delivery = order["legs"][leg]["car"], order["legs"][leg]["pickup"], order["legs"][leg]["delivery"]
        first: StopRef = {"orderId": oid, "leg": leg, "kind": "pickup", "withPlates": "no_plates" in reasons or needs_plates(note),
                          "withCharging": bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30)}
        second: StopRef = {"orderId": oid, "leg": leg, "kind": "delivery"}
        noted = window_from_note(note, pickup["window"], "pickup")
        if noted != pickup["window"]:
            first["window"] = noted
        base = {"from": delivery["window"]["from"], "to": max(delivery["window"]["from"], order["deadline"])}
        noted = window_from_note(note, base, "delivery")
        if noted != base:
            second["window"] = noted
        last = state.failures.get((oid, leg), [None])[-1]
        if last in ("not_ready", "closed"):
            start = max(retry_from(state, order, leg, now), first.get("window", pickup["window"])["from"])
            first["window"] = {"from": start, "to": max(pickup["window"]["to"], start)}
        w = first.get("window", pickup["window"])
        if FLAGS["explicit_windows"] and not pickup["privateAddress"] and order["lastPickupAt"] > max(now, w["from"] + EXPLICIT_MIN):
            # Without its own window the pickup closes with the site on the ready day and the gig expires, though the
            # car could still be collected later and arrive on time; a re-post without windows then lets a driver
            # come after lastPickupAt (rc7/rc8: 3 of 163 next_day re-posts booked in time). Keep the gig open exactly
            # as long as an on-time delivery is possible, and only for drivers who can make it.
            first["window"] = {"from": w["from"], "to": max(w["from"], min(order["lastPickupAt"], first.get("window", {}).get("to", order["lastPickupAt"])))}
            d = second.get("window", base)
            second["window"] = {"from": d["from"], "to": max(d["from"], min(d["to"], order["deadline"]))}
        stops += [first, second]
    expired = any((oid, leg) in state.expired for leg in legs)
    keep = FLAGS["explicit_windows"] and order["lastPickupAt"] > now
    stops = without_windows(stops, now if keep or not expired else float("inf"))
    return {"type": "post", "stops": stops, "audience": audience, "schedule": fees(state, order, len(legs), now)}


def fees(state: State, order: Order, cars: int, now: int, raised: float = 0.0, base: Optional[float] = None) -> list[FeeStep]:
    fee = base if base is not None else state.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
    if FLAGS["fee_ladder"]:
        ratio = 0.8 + rng(state.world_id, order["id"], cars).random() * FLAGS["fee_ladder"]
        return [{"at": now, "feeCents": max(1, int(fee * ratio + 0.5))}]
    lo, hi = FLAGS["fee_open"], FLAGS["fee_top"]
    left = order["lastPickupAt"] - now
    weekend = order["lastPickupAt"] // DAY >= 5
    if FLAGS["fee_open_long"] and left >= DAY and (FLAGS["long_fee_over_weekend"] or not weekend):  # time to wait for cheaper drivers
        lo, hi = FLAGS["fee_open_long"], FLAGS["fee_open_long"]
    elif FLAGS["fee_open_weekend"] and weekend:
        lo, hi = FLAGS["fee_open_weekend"], FLAGS["fee_open_weekend"]
    elif FLAGS["fee_open_mid"] and left >= MID_SLACK:
        lo, hi = FLAGS["fee_open_mid"], FLAGS["fee_open_mid"]
    if order["id"] in state.urgent:  # the top fee or 1.5 times at once, then a quarter more every half hour
        steps = [(k * 30, max(1.5, hi) + k / 4) for k in range(5)]
    elif raised:  # a raise for a gig still open as its last pickup nears, before the deadline warning
        steps = [(0, raised)]
    elif hi <= lo:  # one flat fee: drivers who see no raises have nothing to wait for
        steps = [(0, lo)]
    else:  # from the opening fee up to the top, in five hourly steps (the starter: 1.0 to 1.5)
        steps = [(k * HOUR, lo + (hi - lo) * k / 5) for k in range(6)]
    if state.level == 1:
        steps = steps[:1]
    return [{"at": now + dt, "feeCents": max(1, int(fee * f + 0.5))} for dt, f in steps]


def dropped_at(state: State, gig_id: str) -> int:
    """The minute a driver last gave this gig back (drop or no-show), or -1."""
    return state.ext.get("driver", {}).get("dropped", {}).get(gig_id, -1)


def observe(event, state: State) -> None:
    """Remembers when a booked driver gave a gig back: it reopens at a fee that already failed to hold a driver."""
    if event["kind"] in ("gig_dropped", "no_show"):
        state.ext.setdefault("driver", {}).setdefault("dropped", {})[event["gigId"]] = event["at"]


def raise_due(order: Order, gig, now: int) -> float:
    """The fee ratio of the latest raise that is due and not yet applied, or 0. Raises come only for a gig still
    open as its last pickup nears: the early one (raise_mid_lead) to fee_raise_mid, the late one (raise_lead) to
    fee_raise. A gig that books at its opening fee never shows drivers a raise."""
    for lead, ratio in ((FLAGS["raise_lead"], FLAGS["fee_raise"]), (FLAGS["raise_mid_lead"], FLAGS["fee_raise_mid"])):
        due = order["lastPickupAt"] - lead
        if lead and now >= due and gig["scheduledAt"] < due:
            return ratio
    return 0.0


def retry_from(state: State, order: Order, leg: int, now: int) -> int:
    """After a visit found the car not ready or the site closed: two hours on, or later when the dealer
    moved the deadline by a delay."""
    request = state.requests[order["id"]]
    promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), order["deadline"])
    return max(now + 2 * HOUR, order["legs"][leg]["pickup"]["window"]["from"] + max(0, order["deadline"] - promised))


def without_windows(stops: list[StopRef], before: float) -> list[StopRef]:
    """Drops stop windows that end before `before`, so the order's window applies, which runs to the end of
    the world once it has ended."""
    return [{k: v for k, v in s.items() if k != "window"} if "window" in s and s["window"]["to"] < before else s for s in stops]


def drive_minutes(state: State, order: Order, legs: list[int]) -> int:
    """Road minutes from the first pickup to the last delivery, legs in order."""
    places = [p for leg in legs for p in (order["legs"][leg]["pickup"]["placeId"], order["legs"][leg]["delivery"]["placeId"])]
    return sum(state.minutes(a, b) for a, b in zip(places, places[1:]))


def gig_base(state: State, gig) -> float:
    """The typical fee of all the cars on a gig, which may come from two orders."""
    return sum(state.requests[st["orderId"]]["referenceFeeCents"] / len(state.orders[st["orderId"]]["legs"])
               for st in gig["stops"] if st["kind"] == "pickup")


# --- two-car chains ----------------------------------------------------------------------------------------------
# A driver who delivers car A where car B waits saves a trip home and a trip out (HANDBOOK: a gig that ends near
# the next pickup is cheap). Each new single car is paired with another new car, or with a single still open and
# unbooked, whose pickup lies near its delivery; both go out as one gig at a discount on the two fees. Nothing is
# held back. In a shortage a driver-day is the scarce thing; a chain moves two cars with one.

def pairable(state: State, order: Order, now: int) -> bool:
    """A single-car order with time to spare: a candidate for a two-car chain."""
    oid = order["id"]
    return (len(order["legs"]) == 1 and oid not in state.urgent and (oid, 0) not in state.failures
            and (oid, 0) not in state.expired and order["lastPickupAt"] - now >= FLAGS["bundle_slack"])


def chain_ok(state: State, a: Order, b: Order, now: int) -> bool:
    """One driver can take car A, then car B, on time and within the 12-hour driving limit."""
    la, lb = a["legs"][0], b["legs"][0]
    pa, da, pb, db = la["pickup"]["placeId"], la["delivery"]["placeId"], lb["pickup"]["placeId"], lb["delivery"]["placeId"]
    gap = state.minutes(da, pb)
    if gap > FLAGS["bundle_gap"] or state.minutes(pa, da) + gap + state.minutes(pb, db) > SPLIT_MINUTES:
        return False
    at_da = max(now, la["pickup"]["window"]["from"]) + state.minutes(pa, da)
    at_pb = max(at_da + gap, lb["pickup"]["window"]["from"])
    return (at_da <= a["deadline"] - BUNDLE_BUFFER and at_pb <= lb["pickup"]["window"]["to"]
            and at_pb + state.minutes(pb, db) <= b["deadline"] - BUNDLE_BUFFER)


def open_singles(state: State, now: int) -> list[tuple[Order, str]]:
    """Single-car gigs still open, posted recently and never repriced: they can be withdrawn and re-posted as a chain."""
    out = []
    for gid, gig in state.gigs.items():
        if gig["status"] != "open" or len(gig["stops"]) != 2 or now - gig["postedAt"] > BUNDLE_REPOST_AGE \
                or gig["scheduledAt"] != gig["postedAt"]:
            continue
        order = state.orders.get(gig["stops"][0]["orderId"])
        if order is not None and pairable(state, order, now) and state.gig_of.get((order["id"], 0)) == gid:
            out.append((order, gid))
    return out


def bundles(state: State, waiting: list[Order], now: int) -> tuple[list[Action], set[str]]:
    """Pairs each new car with another new car or an open single, without holding anything back. Returns the
    actions (a withdraw for a paired open single, then the chain's post) and the new orders it paired."""
    actions: list[Action] = []
    used: set[str] = set()
    pool = [(o, None) for o in waiting] + open_singles(state, now)
    for a in waiting:
        if a["id"] in used:
            continue
        for b, gid in pool:
            if b["id"] in used or b is a:
                continue
            first, second = (a, b) if chain_ok(state, a, b, now) else (b, a) if chain_ok(state, b, a, now) else (None, None)
            if first is None:
                continue
            if gid is not None:
                actions.append({"type": "withdraw", "gigId": gid})
            pf, ps = post(state, first, [0], now), post(state, second, [0], now)
            fee = round((pf["schedule"][0]["feeCents"] + ps["schedule"][0]["feeCents"]) * FLAGS["bundle_factor"])
            audience = {k: pf["audience"][k] or ps["audience"][k] for k in pf["audience"]}
            actions.append({"type": "post", "stops": pf["stops"] + ps["stops"], "audience": audience,
                            "schedule": [{"at": now, "feeCents": fee}]})
            used.update((a["id"], b["id"]))
            state.log(now, "post_bundle", first["id"], with_order=second["id"], fee=fee, rebundled=gid)
            break
    return actions, used


def _backing_off(state: State, leg: tuple[str, int], now: int) -> bool:
    refused: Optional[tuple[int, str]] = state.refused.get(leg)
    return refused is not None and now - refused[0] < REFUSED_BACKOFF


def _cars(gig) -> int:
    return sum(1 for s in gig["stops"] if s["kind"] == "pickup")
