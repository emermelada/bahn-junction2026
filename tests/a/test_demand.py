"""Demand (V2 forecast of future wins): totals match the prior, past days and weekends are empty, the forecast is
deterministic and replay-safe, wins move the win scale, and any region map works.
Run: PYTHONPATH=src python -m pytest tests/a/test_demand.py"""
from spreadbot import demand as D
from spreadbot.geo import DAY


class Desk:
    supply = None


class OneRegion:
    def region(self, place):
        return "all"


def req(rid, at, place="vantaa", legs=1):
    leg = {"pickup": {"placeId": place}, "delivery": {"placeId": "tampere"}}
    return {"kind": "price_request", "at": at, "request": {"id": rid, "arrivedAt": at, "legs": [leg] * legs}}


def won(rid, at, ddl_day, option="next_day", place="vantaa"):
    return {"kind": "order_won", "at": at + 15, "order": {"id": rid, "option": option, "deadline": ddl_day * DAY + 1000,
                                                         "legs": [{"pickup": {"placeId": place}}]}}


def lost(rid, at):
    return {"kind": "order_lost", "at": at + 15, "requestId": rid}


def week_events(n_won):
    ev = []
    for i in range(200):
        at = 9 * 60 + i
        ev.append(req(f"R{i}", at))
        ev.append(won(f"R{i}", at, 1) if i < n_won else lost(f"R{i}", at))
    return ev


def build(events, desk=None):
    d = D.Demand(desk or Desk())
    for e in events:
        d.on_event(e)
    return d


def test_requests_left_matches_prior():
    d = D.Demand(Desk())
    regions = sorted(set(D.REGION.values()))
    total = sum(d.requests_left(g, 0, 0) for g in regions)
    assert abs(total / sum(v for (dd, _), v in D.ARRIVALS.items() if dd == 0) - 1) < 1e-3  # shares rounded to 4 places
    # half of 12:00-13:00 is gone at 12:30
    half = sum(d.requests_left(g, 0, 12 * 60 + 30) for g in regions)
    after13 = sum(v for (dd, h), v in D.ARRIVALS.items() if dd == 0 and h >= 13)
    assert abs(half / (after13 + 0.5 * D.ARRIVALS[(0, 12)]) - 1) < 1e-3


def test_past_day_and_weekend_are_empty():
    d = D.Demand(Desk())
    assert d.expected("cap", 0, 1 * DAY + 600) == []
    assert d.expected("cap", 5, 0) == [] and d.expected("cap", 6, 0) == []
    assert d.expected("nowhere", 1, 0) == []


def test_expected_shape_and_determinism():
    a, b = build(week_events(80)), build(week_events(80))
    ea, eb = a.expected("cap", 2, 9 * 60), b.expected("cap", 2, 9 * 60)
    assert ea == eb and ea
    days = [e.deadline_day for e in ea]
    assert days == sorted(days) and min(days) >= 2
    for e in ea:
        assert e.n_cars > 0 and e.mean_drive_min > 0
        assert abs(sum(e.option_mix.values()) - 1.0) < 1e-9
        dd, mix, n, drive = e  # unpacks as the 4-tuple of the interface


def test_replay_and_duplicates_change_nothing():
    ev = week_events(80)
    a = build(ev)
    b = build(ev + ev)  # a restart replays every event again
    assert a.state() == b.state()
    assert a.wins_so_far("cap", 0) == 80.0 == b.wins_so_far("cap", 0)


def test_wins_move_the_scale_within_bounds():
    low, high = build(week_events(10)), build(week_events(190))
    assert low.win_scale() < 1.0 < high.win_scale()
    assert D.SCALE_MIN <= low.win_scale() and high.win_scale() <= D.SCALE_MAX
    n_low = sum(e.n_cars for e in low.expected("cap", 1, 9 * 60))
    n_high = sum(e.n_cars for e in high.expected("cap", 1, 9 * 60))
    assert n_high > n_low


def test_option_shares_follow_this_weeks_wins():
    d = build(week_events(150))  # every win is next_day
    mix = {}
    for e in d.expected("cap", 1, 9 * 60):
        for k, v in e.option_mix.items():
            mix[k] = mix.get(k, 0.0) + v * e.n_cars
    p = D.Demand(Desk())
    mix0 = {}
    for e in p.expected("cap", 1, 9 * 60):
        for k, v in e.option_mix.items():
            mix0[k] = mix0.get(k, 0.0) + v * e.n_cars
    assert mix["next_day"] / sum(mix.values()) > mix0["next_day"] / sum(mix0.values())


def test_any_region_map():
    desk = Desk()
    desk.supply = OneRegion()
    d = D.Demand(desk)
    total = sum(e.n_cars for e in d.expected("all", 1, 0))
    per_region = sum(e.n_cars for g in sorted(set(D.REGION.values())) for e in D.Demand(Desk()).expected(g, 1, 0))
    assert abs(total - per_region) < 1e-6
