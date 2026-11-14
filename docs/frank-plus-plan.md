# Improving Franko's v1 (preset `chains`, k18): findings and plan

From Javier's side, 14 Nov. Franko's v1 is the team's bot from now on. These are measurements on seeds Franko never used (rc10-01..12) and what we propose next. Nothing here is committed to Franko's branches; code changes go on `a/frank-plus`.

## Where k18 stands

| rc10 (12 fresh weeks) | Ranked | Min on-time | Mean | Median | Worst week | Orders a week |
|---|---|---|---|---|---|---|
| Javier main (rc5) | 11/12 | 88.4% | €5,371 | €5,552 | €1,399 | 173 |
| Franko v1 k18 | 12/12 | 90.1% | €10,791 | €10,797 | €6,731 | 361 |
| top ten, round "Saturday 00:00" | | 95-98% | €15,100-17,200 | | | 373-458 |

k18 wins every rc10 week against our main. The gap to the top ten is about €4-6k a week: about 70 more orders a week and €5-10 more per order.

## Tested on k18 so far

| Change | Seeds | Ranked | Min on-time | Mean delta | p10 delta |
|---|---|---|---|---|---|
| `max_per_batch=6` (decline once we hold 6 orders from one batchId) | rc10, 9 of 12 paired | 9/9 | 92.4% vs 92.6% | +€60 | +€438 |

Small but safe: it removes bulk-yard bursts, which made our own bot miss the gate (rc4-11: 19 cars from one batch, 8 late).

## Live rehearsal

`harness/emulate.py --restart-at 3000` with the k18 settings crashed on a server read timeout (`spread.client.Unreachable`), in both the ticker thread and `run_live`. The real final loop (`spreadbot.run final`) catches `Unreachable` and rebuilds, so the final is protected; the emulator is not, so a slow server ends the rehearsal. Suggest: catch `Unreachable` in the emulator's ticker and around `run_live`, as `final()` does.

## Facts from our side that may help

- Our gigs (rc5) booked a driver in a median of 3 minutes after posting (p25 1 min, p75 24) at about 1.0x the typical fee; 96% booked at all. Opening fees near 1.0x leave little on the table for fast bookers, but k20 (opening 0.95) lost a ranked week for you.
- Late share by the day an order is won (60 weeks): Monday 3.3-3.5%, Tuesday-Wednesday 4.5-6.6%, Thursday 7.2-7.7%, Friday 3.3-5.4%. Our win rate at a fixed ratio: Monday 18%, Tuesday-Thursday 26-27%, Friday 31% (the competitor raises prices each morning for dealers whose requests we mostly lose).
- Dealers are concentrated: the top dealer sends 30% of requests, the top ten 78%. Trust (+1% per on-time order, up to 25%) is worth most there.
- `docs/log/` holds every experiment of ours, including the 25 that did not help (lane table at weight 1, week level, trust investment, direct offers, event detectors, explicit windows, ...).

## Plan (in order)

1. Add `max_per_batch=6` to the k18 preset after the last 3 rc10 seeds confirm it.
2. Diagnose the volume gap before tuning: on k18 runs, count declined requests by reason (on-time bar, load price, EV under the floor) and the margin of the orders the top teams take that we refuse.
3. Escalation cost: your own log shows 66 escalated singles costing €2.5k a week above typical. Measure which of them were predictable at quote time (slack, town supply, hour) and price or decline those.
4. The thinnest week (rc10-02, 90.1%): find what went late there before loosening anything.
5. Make the emulator survive `Unreachable` so the live rehearsal runs to the end.
