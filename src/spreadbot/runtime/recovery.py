"""Rebuilding State after a start or a restart, from the world's snapshot and its full event history.

Events say what happened; the snapshot says where every gig and order stands now. Gigs are not in the
events (a post's id comes only in the action result), so the gigs and orders come from the snapshot and
everything else (requests, failures, warnings, changes, money) from folding the history."""
from __future__ import annotations

import copy

from spread.types import DeskEvent, DeskSnapshot, WorldMap

from spreadbot.core.state import LIVE, State, legs_of


def rejoin(world_id: str, level: int, snapshot: DeskSnapshot, history: list[DeskEvent], world_map: WorldMap, log=None) -> State:
    state = State(world_id, level, snapshot["now"], snapshot["endsAt"], world_map, log=log)
    for event in history:  # gig events hit no known gig and change nothing; the facts land
        state.apply(event)
    state.now = snapshot["now"]
    state.orders = {o["id"]: copy.deepcopy(o) for o in snapshot["orders"]}
    state.gigs = {}
    state.gig_of = {}
    for gig in snapshot["gigs"]:
        state.gigs[gig["id"]] = {**copy.deepcopy(gig), "scheduledAt": gig["postedAt"]}
        if gig["status"] in LIVE:
            for leg in legs_of(gig):
                state.gig_of[leg] = gig["id"]
                state.expired.discard(leg)
    return state
