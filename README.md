# Elysa's Secret: a Spread dispatcher that never loses a week

Junction 2026 · Bahn Express "Spread". The bot quotes dealers' requests against a hidden competitor, posts every won car as a gig to
freelance drivers, and learns the market live during the week. Python 3, standard library only, deterministic, restart-safe.

**Results** (level 8): final € ____ (rank __) · best ranking round **€87,491, 6th of 57** (Sun 00:00) · Sun 06:00 round €77,833
· test finals **9th of 75** and **4th of 41** · **every one of 72 weeks it was never tuned on ran ≥ 90% on time.**

The model that plays is the preset **`v5S-an5`** (`src/spreadbot/presets.py`). Every other preset is an experiment kept for the record:
each idea sits behind a flag in `src/spreadbot/config.py` so it can be switched off and measured.

## How it decides

```
request ──► QUOTE ──► won ──► POST ──► PAIR ──► deliver
             │                 │        │
             │ price r that    │ one    │ two cars in one gig when it
             │ maximises       │ fee    │ ends near drivers' homes;
             │ P(win|r) ×      │ per    │ pair fee climbs 0.68 → 0.80 ×
             │ (price − fee    │ gig    │ the summed typical fees
             │  − late risk)   │        │
             └─ competitor level, fee level and late risk are learned live from the week's events
```

| step | where | rule |
|---|---|---|
| Quote | `desk.py` `Desk.price` · `policy.py` `Market` | pick the price ratio r (1.00–1.80 × list) maximising P(win \| r) × (price × (1 − 1.2·P(late)) − fee cost − load charge − late barrier); P(win) = sigmoid(6.7 (μ − r)), μ = competitor level learned per world, day, dealer and lane; decline if nothing pays |
| Late risk | `late_gbm.py` + `late_gbm.json` | P(late) per delivery option from gradient-boosted trees trained on 804k past orders (held-out AUC 0.90) |
| Guards | `desk.py`, `policy.py` `Governor`, `barrier_cents` | long-trip guard (no 4 h+ cars after 3 of ours were warned in 24 h); late barrier: an expected late car costs more as the week's projected on-time share nears 95.5% |
| Post | `fee1.py` | one fee per gig, read off a measured booking curve; fees anchored on a drive-time line learned live (`Desk.typ`) |
| Pair | `desk.py` (`pair_end`, `bundle_climb`) | later-day cars held to 16:00 and paired by where the gig ends |
| React | `desk.py` | dropped car with > 16 h left → re-posted at the opening fee; unbooked first post → one re-pick ~6 h before the last pickup; rescue at the 3 h deadline warning |
| Restart | `run.py`, `run_final.sh` | the state is rebuilt by replaying the world's events; the supervisor restarts the bot if it exits |

## The big ideas, each measured with and without on the same weeks

| idea | why (what we saw) | effect |
|---|---|---|
| **Price the late risk** | a car is late almost only when it is picked up after its last pickup (0.7% late vs 99%, 55,998 deliveries) | +€2,076/week on 12 unseen weeks; 12/12 ranked (was 11/12) |
| **Fees from the drive time** | at the same fee ÷ typical fee, cars whose typical fee is low for their drive book 38% within an hour, high 67%: drivers price the drive, the typical fee is ~11% noisy | +€326/week over 72 unseen weeks, all ranked |
| **One fee per gig from a booking curve** | P(booked before the warning) = 60 / 75 / 89 / 93% at 0.85 / 0.95 / 1.05 / 1.20 × typical fee | +€383 and +€541/week on two unseen sets |
| **Gigs that end near home** | drivers book 14–17% of the gigs they see that end ≤ 30 min from home, < 2% beyond 4 h | +€400–600/week on two unseen sets |
| **Guards for the bad week** | older versions lost ~1 week in 10 under 90%; 73% of those late cars were 4 h+ drives | costs ~€300/week; 72/72 unseen weeks ranked, 0/27 replays of the 3 hardest weeks under 90% |

## What did not work (all measured, see `research/`)
- Cheaper prices to win more cars: −€321/week in cheap-competitor weeks (four rival teams found the same).
- Any loosening of the late barrier: fixed one weak week and put a flu week under 90% in 5–9 of 9 replays.
- Two good changes stacked (cheaper pairs + more note cars): a hard week went unranked.
- Direct offers to drivers (~1% accepted), 3–4 car gigs, long holds for partners, re-post caps, flat fees.

## What would break it
A flu night (many drivers drop their gigs in one hour), a deep price war (competitor below list: margin roughly halves),
a week with too few drivers.

## Run it
```
cp .env.example .env            # SPREAD_KEY=...  (never commit it)
PYTHONPATH=src python -m spreadbot.run practice --level 8 --seed dev-07 --preset v5S-an5
./run_final.sh --preset v5S-an5 # the final: waits for it, plays it, restarts on exit
```
Tests: `PYTHONPATH=src python -m pytest -q tests`. Validation tools and the full experiment log: `research/re/` (`HIVE.md`, `prun.py`,
`pair_vs.py`, `jitter.sh`).
