"""The live runner: plays a world whose clock moves by itself (the final, a test final, or a practice world
that harness/emulate.py advances). Same State, quote and dispatch as practice.

    python -m spreadbot.runtime.live_runner --final          # wait for the final (or test final) and play it
    python -m spreadbot.runtime.live_runner --world <id>     # join a running world

Loop: follow the event stream; quote each request at once; about once a second read the snapshot for the
world clock and run dispatch. The final's limits are 20 actions a second (burst 50) and 50 reads a second,
so each cycle sends the quotes first and at most MAX_DISPATCH dispatch actions, most urgent first; the rest
come back next cycle, because dispatch recomputes what is missing from State. On any server failure the
runner waits, rebuilds State from snapshot and history, and goes on; it never resends an action blind."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

from spread.client import Client, SpreadError, Unreachable, World
from spread.types import Action

from spreadbot.core.declog import DecLog
from spreadbot.core.state import State
from spreadbot.runtime.practice_runner import RUNS, decide, line, observe, write_json
from spreadbot.runtime.recovery import rejoin

HEARTBEAT = 1.0  # real seconds between clock reads and dispatch cycles; a request has 4.5 s in the final
MAX_DISPATCH = 15  # dispatch actions per cycle, leaving tokens for the quotes of the next second
PRIORITY = {"quote": 0, "release": 1, "offer": 2, "post": 3, "reprice": 4, "withdraw": 5}


def send(world: World, state: State, actions: list[Action], log) -> None:
    """Sends actions in priority order, folds each result into State."""
    actions = sorted(actions, key=lambda a: PRIORITY[a["type"]])
    for i in range(0, len(actions), 50):
        batch = actions[i:i + 50]
        for action, result in zip(batch, world.act(batch)):
            state.applied(action, result)
            log.write(line({"t": "res", "a": action, "r": result}))
            if not result["ok"]:
                state.log(state.now, "refused", action.get("gigId", action.get("requestId", "")), type=action["type"], reason=result["reason"])


def play_live(client: Client, world: World, level: int) -> dict:
    run_dir = os.path.join(RUNS, world.id)
    os.makedirs(run_dir, exist_ok=True)
    declog = DecLog(os.path.join(run_dir, "decisions.jsonl"))
    world_map = client.map()
    with open(os.path.join(run_dir, "live.jsonl"), "a", encoding="utf-8") as log:
        while True:
            try:
                return follow(client, world, level, world_map, declog, log)
            except (Unreachable, ConnectionError, TimeoutError) as error:
                print(f"server unreachable: {error}. Rebuilding in 5 s.", file=sys.stderr, flush=True)
                time.sleep(5)
            except SpreadError as error:
                if error.status not in (429, 502, 503, 504):
                    raise
                time.sleep(2)


def follow(client: Client, world: World, level: int, world_map, declog: DecLog, log) -> dict:
    history = world.events()
    snapshot = world.snapshot()
    state = rejoin(world.id, level, snapshot, history, world_map, log=declog)
    state.ext["roster"] = world.roster()
    declog(state.now, "rejoin", world.id, events=len(history), orders=len(state.orders), gigs=len(state.gigs))
    print(f"joined {world.id} at minute {state.now}: {len(state.orders)} orders, {len(state.gigs)} gigs", flush=True)
    # Requests that are still open after a restart get an answer first.
    send(world, state, decide(state, [r for r in snapshot["openRequests"] if r["respondBy"] > state.now]), log)
    last_cycle = 0.0
    for event in world.stream(after=state.seq, idle=HEARTBEAT):
        requests = []
        if event is not None and state.apply(event):
            observe(event, state)
            log.write(line({"t": "ev", "e": event}))
            state.now = max(state.now, event["at"])
            if event["kind"] == "price_request":
                requests.append(event["request"])
        if requests:  # a request has 15 world minutes, 4.5 real seconds: answer it now, alone
            send(world, state, [a for a in decide_quotes(state, requests)], log)
        if time.monotonic() - last_cycle >= HEARTBEAT:
            last_cycle = time.monotonic()
            snap_now = world.snapshot()["now"]
            state.now = max(state.now, snap_now)
            log.write(line({"t": "now", "now": state.now}))
            actions = decide(state, [])
            if len(actions) > MAX_DISPATCH:
                declog(state.now, "throttled", "", waiting=len(actions) - MAX_DISPATCH)
            send(world, state, sorted(actions, key=lambda a: PRIORITY[a["type"]])[:MAX_DISPATCH], log)
            if state.now >= state.ends_at:
                break
    score = world.score()
    write_json(os.path.join(run_dir_of(world), "score.json"), score)
    return score


def decide_quotes(state: State, requests: list) -> list[Action]:
    """Only the quote part of decide()."""
    return [a for a in decide(state, requests) if a["type"] == "quote"]


def run_dir_of(world: World) -> str:
    return os.path.join(RUNS, world.id)


def next_final(client: Client) -> World:
    """The final or test final that is set or running; waits while none is."""
    said = False
    while True:
        try:
            world: Optional[World] = client.world(client.final()["worldId"])
        except SpreadError as error:
            if error.status != 404:
                raise
            world = None
        if world is not None:
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        if not said:
            print("No final is set yet. Waiting.", flush=True)
            said = True
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--world")
    parser.add_argument("--level", type=int, default=8)
    args = parser.parse_args()
    client = Client()
    world = next_final(client) if args.final else client.world(args.world)
    print(f"playing {world.id}", flush=True)
    score = play_live(client, world, args.level)
    print(json.dumps(score))


if __name__ == "__main__":
    main()
