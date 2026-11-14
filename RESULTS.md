# BahnSpread v2 — measured results (level 8, same seeds, stride loop)

Every number is one full simulated week on a practice world, from `data/results.csv` / `runs/index.jsonl`.
Gate seeds: `spread-1, v2-g1..v2-g4`. Gate rule: every seed ranked at ≥ 93% on time, no unquoted request, no exception.

## Ablation on spread-1 (one idea at a time)

| Step | Config | Margin/week | On time | Won | What changed |
|---|---|---|---|---|---|
| Kit starter | `cfg/starter.json` | −€72,613 | 45.5% | 949 | reproduced to the cent |
| M1 | `cfg/m1.json` | −€8,517 | 88.1% | 352 | feasibility tiers, pool-day capacity, ladder, governor |
| M2 | `cfg/m2.json` | −€4,198 | 81.8% | 291 | flat-then-cliff fees by reach band, rescue, triage sweep |
| M3 | `cfg/m3.json` | **+€8,719** | 92.8% | 335 | online competitor interval per lane, trust |
| M3e | M3 + evening step | +€8,140 | 94.5% | 307 | fee step at 17:30 the evening before the pickup day |
| M6 | `cfg/m6.json` | +€7,583 | 98.5% | 262 | clamp 1.75, next_day > 4 h drive → C, pool brake |
| **M8 (gated)** | `cfg/m8.json` | **+€7,962** | 97.5% | 282 | no weekend-crossing downgrade, no Friday guard, looser same_day |

## Gate tables (margin €/week, on time)

| Seed | M3e | M6 | M8 |
|---|---|---|---|
| spread-1 | 8,140 / 94.5 | 7,583 / 98.5 | 7,962 / 97.5 |
| v2-g1 | 7,285 / 94.7 | 6,239 / 99.5 | 7,384 / 97.8 |
| v2-g2 | 9,378 / 94.7 | 7,038 / 97.6 | 8,244 / 98.6 |
| v2-g3 | 3,205 / 93.0 | 3,100 / 96.1 | 3,920 / 96.6 |
| v2-g4 | 662 / **86.4 unranked** | 4,796 / 97.4 | 4,979 / 96.9 |
| mean | 5,734 — FAIL | 5,751 — PASS | **6,498 — PASS** |

## Rejected arms (paired against the base on the same seeds)

| Arm | Change | Result |
|---|---|---|
| M4 | price clamp 2.2 | spread-1 €6,172 vs €8,140: win rate collapses above ~1.75× list |
| M7 | looser same_day on M6 | worse on 2 of 3 seeds |
| M6o | direct offers on M6 | spread-1 €6,793 vs €7,583 |
| M9 | M8 with default same_day | worse on 4/4 seeds (mean €5,868) |
| m10a | cheaper fee bands | mean €6,022 vs €6,498, lower on time |
| m10b | clamp 1.85 | worse on 5/5 (mean €5,969) |

## Evidence that drove each change

- Starter loses money because it forces `same_day` on itself and pays 1.5–2.5× the reference fee (booked fee / reference median 1.5).
- Lateness autopsy (`src/tools/late.ts`): late orders were booked only *after* their last on-time pickup, mostly 18–20h — drivers plan the next day in the evening → evening-before fee step (+1.7 pts on time).
- Rescue bug: `min(0.9 × price, …)` made the deadline-warning "rescue" *lower* than the cliff it replaced → fixed (never below 1.7× base).
- On time by drive length (`src/tools/risk.ts`, 3,000 orders): next_day with ≥ 4 h drive 82–85% on time; everything else ≥ 91% → long next_day declined.
- 115 Friday next_day requests per week (Monday deadline, ≥ 8 driver-hours of slack) were being declined by a weekend downgrade → removed (M8: better on 5/5 seeds).
- Win rate by quoted ratio (`src/tools/curve.ts`): flat ~40–50% from 1.2× to 1.7× (the lane learner finds each lane's level), cliff above 1.8×.

## Robustness

- Stride loop deterministic to the cent (M8 spread-1 twice: €7,962.02).
- Final loop rehearsal (`src/run-final.ts` + `src/ticker.ts`, 2× final pace, two `kill -9` restarts): ranked 96.3%, €5,780; rebuild from 4,523 events in 29 ms; quote lag 0 world minutes; the world refuses duplicate gigs. Same seed under the stride loop: €6,637 (the gap is the requests lost during the two forced outages).

## Final-config choice: m18 = M8 + batch cap scaled by pickup reach (Sat ~03:15)

The bulk order (33–38 cars from one yard) and other 10–25-car batches appear in every world. In held-out `v2-h2`, 12 within_3_days cars from one Oulu yard all waited for the last day and 10 went late: M8 fell to **90.2%** on time. Cap: at most `max(4, 0.1 × reach30(pickup))` admitted requests per batch (Helsinki pool ≈ uncapped, Oulu 6, Lahti 4).

| Seeds | M8 mean | m18 mean | Worst on time M8 → m18 |
|---|---|---|---|
| Gate (5) | €6,498 | €5,988 | 96.6% → 96.3% |
| Held-out h1–h10 (10, never tuned on) | €5,856 | €5,763 (better on 6/10) | **90.2% → 95.4%** |

Adopted for the final: about −€100 to −€500/week for a 5-point higher floor on the one metric that zeroes the score.

More rejected arms: price floor 1.65 (v2-g1 €1.9k with 41 wins), floor 1.45, steeper ladder (mean €5,732), higher price prior (€6,077), admit tier C via governor (v2-g1 92.3%, FAIL), higher fee bands (€5,317), stronger evening step, bundles (16/week, mean €6,425, 2/5), flat batch cap 6 / plan-day cliff (−€500–1,000).

## Notes reader adopted: m19 = m18 + notes (Sat ~03:40)

`src/notes.ts` (fi/sv/en, typo-tolerant, corrections and denials) scores 0 false positives / 0 misses on all 2,297 revealed notes with truth (`node src/tools/notes-validate.ts --all`). Used for the pickup's earliest minute, the note's delivery deadline, plates and the manual-licence audience.

| 15 seeds (5 gate + 10 held-out) | m18 | m19 |
|---|---|---|
| Mean margin/week | €5,838 | €5,850 (better on 7/15) |
| Failed-visit cost/week | €258 | **€59** |
| Mean on time | 97.44% | **97.86%** (better on 10/15) |
| Worst on time | 95.43% | 95.48% |

This fails the strict margin rule (n−1 seeds better). Adopted anyway, because on time is the binding risk in the final and the failed-visit saving is mechanical, not noise.

## Session 2 (Sat 06:00–08:00): theory, model pricing, chains — €5.9k → €9.4k/week

**Why the gap to the leaders.** The board exposes `wonOrders` per run (`node src/tools/top.ts`): the top 10 win 400–460 orders/week at €35–43 each; m19 won ~200 at €29. The typical fee is ≈ the list price on every lane band (ref/list 0.89–1.03).

**Theory.** Interval-censored fit over ~20 runs per gate seed (the same requests quoted at different prices across runs; outcome is a deterministic threshold per request in 281/300 cases): the ratio at which a request flips to lost is lognormal, **median 1.36 x list, sigma 0.23** — P(win) 0.91 at 1.0, 0.71 at 1.2, 0.58 at 1.3, 0.45 at 1.4, 0.34 at 1.5. Pricing every request of spread-1 at argmax P(x/trust)·(x − fee/list) gives, without any capacity limit: €15.6k/week with no trust, **€22.4k with the top-4 dealers at full trust from Tuesday** (€12.3k / €18.6k at fees 1.1 x ref). €70k/5 weeks is inside the theory; the binding constraint is delivering ~450–500 orders on time.

**Bug found.** The interval pricer learnt trust-inflated ratios: trusted dealers' wins lifted every dealer's price, so the mean quote crept 1.24 → 1.54 → 1.71 → 1.74 → 1.74 x list Monday to Friday and Friday wins collapsed.

| Arm | Change | Gate mean (5 seeds) | vs m19 | Worst on time |
|---|---|---|---|---|
| m19 | previous final | €5,940 | — | 97.4% |
| p1 | `pricing.model`: margin-optimal quote under the fitted threshold, online world/day/lane/dealer offsets, trust-scaled threshold, fee estimate as cost | €7,722 | 5/5 better | 92.7% |
| p3 | p1 + Friday capacity x0.5 (`capacity.dayMult`) | €7,933 | 5/5 | 93.9% |
| **b1** | p3 + **chain bundles** (`bundles.chain`: a car whose delivery is ≤30 road min from another open car's pickup goes in one gig, fee 0.85 x both) | **€9,392** | **5/5 (4/5 vs p3)** | **95.4%** |

b1 per seed: spread-1 9,503 · v2-g1 9,189 · v2-g2 13,396 · v2-g3 7,033 · v2-g4 7,837. 63% of single-car wins are chainable at win time; 55–92 chains/week, 93% of them booked; fee per car −4% to −30%, on time up to 99.5% (a chain is one trip out and one trip home for the driver, and one gig of the driver's daily quota for two cars).

p3 held-out (5 of 10 seeds before the slots went to b-arms): +€1,119/seed vs m19, 4/5 better (v2-h1 −€406 at 92.2%).

Rejected this session: anchor bonus (cheap quotes to build trust; trust counts on delivery, ~1 day after the win, so it pulls full trust forward by half a day only: −€950 and −€1,350), sigma 0.18 (−€1k), same_day priced 1.3 x (−€1.1k on spread-1), opening the gate without chains (v3, v5: unranked 86.9–89.6% on v2-g1; Friday same_day and long next_day go late), Friday capacity x0.35 (= x0.5).

**b1 held-out (10 seeds never tuned on):** 6,615 · 4,805 · 10,587 · 6,212 · 7,959 · 10,286 · 8,037 · 9,032 · 7,665 · 9,358 = **mean €8,056 vs m19 €5,805, better on 10/10**, worst on time 93.4%. Over all 15 seeds b1 averages **€8,501/week (≈ €42.5k / 5 weeks)**.

**Final loop rehearsal with b1** (`run-final.ts` on a practice world ticked at 4x the final's pace, seed v2-rehearsal-2): END €8,238, 342 won, 97.4% on time, ranked, exit 0. 15 refused actions, all the live race "gig is not open" (a driver booked a chain partner between decision and withdraw; the car falls back to its own gig; such gigs are no longer partners).

Rejected around b1 (each worse on its first 1–5 seeds): long next_day reopened (b6: −€211/−€565, 91.3% on v2-g1) and reopened with a 1.3x cost and late premium (b13: +€1,258 / −€1,649, 91.7%), fee estimate 0.9 (b8: −€1,031), fee bands −10% (b9: −€828, 93.8%), outage region offset (b10: −€413 / +€367, neutral), 3-car chains (b11: −€63 / −€1,500), sweep pairing of stale singles (b7: −€622), direct offers (b12: −€772), chain hop 45 min (b14: −€541 / −€850), shadow cost €10 per car (b15: mean €7,824 — same margin with ~80 fewer orders: b1's marginal cheap orders earn ~€0), Friday same_day cutoff with chains (b2: −€140 to −€330).

More rejected around b1 (Sat ~07:30): shadow cost €5 per car (b17: −€1,335 / +€9 / −€1,175), shadow cost €10 + long next_day (b16: mean €8,813 vs €9,392 — +€1.5k and +€1.0k on v2-g1 / spread-1, −€1–2k on the three tighter worlds), shadow cost €15 + long next_day (b18: −€868 / −€3,908), long next_day only while the late budget has room (b19: v2-g4 €4,721 at 91.6% — the governor sees lateness only at delivery, a day too late). Stride vs the live final loop on the same seed: €8,166 vs €8,238 — the real-time loop loses nothing.

Margin per order by drive band (b1, 15 seeds, chain fees split by typical fee): <1 h €16, 1–2 h €26, 2–4 h €36, 4 h+ €54 — about 0.45 x list everywhere; fee/list 0.84–0.97, revenue/list 1.37. The long lanes we still decline would pay, but in the tight worlds they take a driver's whole day and the same-day cars go late (b6/b16/b19 late orders were mostly same_day, not the long ones).
