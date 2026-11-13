"""Plays one practice week with `advance`: fold events into State, quote new requests, dispatch, send the
actions with the next advance. Writes data/runs/<world id>/: meta.json, log.jsonl (what State is folded
from), decisions.jsonl, summary.json and score.json.

    python -m spreadbot.runtime.practice_runner --level 8 --seed dev-01
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import Any, Optional

from spread.client import Client
from spread.types import Action, DeskEventKind, WorldMap

from spreadbot.core.declog import DecLog
from spreadbot.core.state import State
from spreadbot.dealer.quote import decline, quote
from spreadbot.driver.dispatch import dispatch

# Outside request hours: wake on the events that need an answer, and at least every hour.
WAKE_ON: list[DeskEventKind] = ["price_request", "order_won", "order_changed", "order_cancelled", "visit_failed", "gig_expired",
                                "deadline_close"]
TICK = 60
# In request hours (weekdays 08:00-18:00) a request comes every few minutes, so waking on each costs ~1,900
# steps a week. A fixed 10 minute tick answers every request inside its 15 minute window in ~300 steps.
BUSY_TICK = 10
DAY = 24 * 60
RUNS, REGISTRY = "data/runs", "data/worlds_a.jsonl"


def next_stop(now: int, ends_at: int) -> dict[str, Any]:
    """The advance arguments for the next step from `now`."""
    busy = now // DAY < 5 and 8 * 60 <= now % DAY < 18 * 60
    if busy:
        return {"to": min(ends_at, now + BUSY_TICK)}
    return {"until": WAKE_ON, "max": min(ends_at, now + TICK)}


def decide(state: State, requests: list[dict]) -> list[Action]:
    """Quotes first, then dispatch. One bad request or a dispatch bug never stops the loop."""
    actions: list[Action] = []
    for request in requests:
        try:
            prices = quote(request, state)
            code = "quote"
        except Exception as error:  # noqa: BLE001 - fail safe: decline instead
            prices, code = decline(request), "quote_error"
            state.log(state.now, code, request["id"], error=repr(error))
        actions.append({"type": "quote", "requestId": request["id"], "prices": prices})
        if code == "quote":
            state.log(state.now, code, request["id"], prices=prices)
    try:
        actions += dispatch(state, state.now)
    except Exception as error:  # noqa: BLE001
        state.log(state.now, "dispatch_error", "", error=repr(error))
    return actions


def play(level: int, seed: Optional[str], client: Optional[Client] = None, world_map: Optional[WorldMap] = None,
         tag: str = "") -> dict[str, Any]:
    client = client or Client()
    world_map = world_map or client.map()
    started = time.monotonic()
    world = client.create(level=level, seed=seed)
    run_dir = os.path.join(RUNS, world.id)
    os.makedirs(run_dir, exist_ok=True)
    meta = {"worldId": world.id, "seed": seed, "level": level, "tag": tag, "commit": commit()}
    write_json(os.path.join(run_dir, "meta.json"), meta)
    with open(REGISTRY, "a", encoding="utf-8") as registry:
        registry.write(json.dumps({**meta, "runDir": run_dir}) + "\n")
    declog = DecLog(os.path.join(run_dir, "decisions.jsonl"))
    try:
        with open(os.path.join(run_dir, "log.jsonl"), "w", encoding="utf-8") as log:
            snapshot = world.snapshot()
            state = State(world.id, level, snapshot["now"], snapshot["endsAt"], world_map, log=declog)
            state.ext["roster"] = world.roster()
            outbox: list[Action] = []
            steps = 0
            while state.now < state.ends_at:
                step = world.advance(**next_stop(state.now, state.ends_at), actions=outbox)
                steps += 1
                for action, result in zip(outbox, step["results"]):
                    state.applied(action, result)
                    log.write(line({"t": "res", "a": action, "r": result}))
                state.now = step["now"]
                log.write(line({"t": "now", "now": state.now}))
                requests = []
                for event in step["events"]:
                    if state.apply(event):
                        log.write(line({"t": "ev", "e": event}))
                        if event["kind"] == "price_request":
                            requests.append(event["request"])
                outbox = decide(state, requests)
        score = world.score()
    except BaseException:
        try:
            world.delete()  # an unfinished world holds one of the team's 8 slots
        finally:
            declog.close()
        raise
    declog.close()
    summary = {**state.summary(), "steps": steps, "seconds": round(time.monotonic() - started, 1), "decisions": declog.counts}
    write_json(os.path.join(run_dir, "summary.json"), summary)
    write_json(os.path.join(run_dir, "score.json"), score)
    return {**meta, **score, "runDir": run_dir, "digest": summary["digest"], "steps": steps, "seconds": summary["seconds"]}


def commit() -> str:
    try:
        return subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def line(record: dict) -> str:
    return json.dumps(record, separators=(",", ":")) + "\n"


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Play one practice week.")
    parser.add_argument("--level", type=int, default=8, choices=range(1, 9))
    parser.add_argument("--seed")
    args = parser.parse_args()
    r = play(args.level, args.seed)
    print(f"{r['worldId']} seed={r['seed']} L{r['level']}  margin €{r['marginCents'] / 100:,.2f}  on time {r['onTimeShare']:.1%}  "
          f"orders {r['wonOrders']}  ranked={r['ranked']}  {r['steps']} steps {r['seconds']}s  {r['runDir']}")


if __name__ == "__main__":
    main()
