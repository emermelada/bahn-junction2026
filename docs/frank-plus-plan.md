# Improving Franko's v1 (preset `chains`, k18): findings and plan

## Handoff to Franko (14 Nov, ~11:00)

Javier moves to another challenge. Everything we found is on branch **`a/frank-plus`**, two commits on top of `origin/branch-v1-frank` (6030678), nothing else changed:

| Commit | What | Evidence |
|---|---|---|
| 629708e | preset `chains_plus` = `chains` (k18) + `max_per_batch=6` | rc10, 12 fresh weeks: mean €11,041 vs €10,791, ranked 12/12 vs 12/12, min on-time 91.8% vs 90.1% |
| 48a67ba | flag `bundle_price_strict` (default off): chain-aware quoting only when the planner's own chain test passes against a held car | see "Chain-aware quoting" below |

To take them: `git fetch && git checkout branch-v1-frank && git merge origin/a/frank-plus` (or cherry-pick the two commits). Then play with `--preset chains_plus`. On Linux from Javier's repo: `make final-frank` (final or test final) and `make board-frank` (one ranking run) run `chains_plus` from a worktree `../frank-plus`.

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

## Why k18 turns orders away (rc10, 12 weeks, from `log.txt`)

| Per week | Requests |
|---|---|
| quoted or declined | 1,033 |
| declined | 310 |
| - no option with positive EV at any price (`noev`) | 225 |
| - every option under the on-time bar (`skip`) | 76 |
| - both | 10 |

The cost model is not biased: on 3,920 single-car gigs, booked fee / modelled cost has median 0.98 (p10 0.93, p25 0.95, p75 1.21, p90 1.81; the tail is escalations). So the 225 `noev` requests a week are lanes where one car alone costs too much for the price the competitor allows.

**Design idea: chain-aware quoting.** Your measurements: a two-car gig costs about 0.85x the typical fees, a single 1.14x; 71% of won cars could ride in chains in hindsight, k18 chains about 41 a week. Today the quote prices every car as a single. If, at quote time, the request's pickup lies near the delivery of a car we hold (won, unbooked or held for pairing) and the timing fits (the same test as the chain planner), price it with the chain cost. That should turn part of the 225 `noev` requests into profitable wins, and every such win is a ready-made chain partner, so the planner forms more chains instead of fewer.

## Plan (in order)

1. Done: `max_per_batch=6` confirmed on all 12 rc10 weeks (mean 11,041 vs 10,791, 12/12, min on-time 0.918 vs 0.901); preset `chains_plus` on branch `a/frank-plus`.
2. Chain-aware quoting (above): price a request at chain cost when it fits a car we hold; measure orders a week, chains a week, mean and min on-time on rc10 against k18.
3. Escalation cost: your own log shows 66 escalated singles costing €2.5k a week above typical. Measure which of them were predictable at quote time (slack, town supply, hour) and price or decline those.
4. The thinnest week (rc10-02, 90.1%): find what went late there before loosening anything.
5. Make the emulator survive `Unreachable` so the live rehearsal runs to the end.
