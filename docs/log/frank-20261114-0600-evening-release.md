# Evening release: hold next-day cars, pair them at release

**What we saw.** Every car was posted the minute it was won. Single gigs book in a median 4 min, so `try_bundle` (partners posted in the last 2 h, still unbooked) found almost nothing: ~28 cars/week rode in bundles on rc2. Offline, on rc2's own wins, holding next-day cars until 18:00 the day before pickup allows ~110 chain links/week (165 cars). Bundles cost 0.86× the summed typical fee vs 1.20× for singles, and went late 1.2% vs 4.0% (`../research/scripts/pairs_policy.py`, `bundlecost.py`).

**The idea.** A car whose first pickup is on a later day waits in a held pool until `hold_hour` on the day before its pickup day. At each release, a greedy matching (shortest transfer first) pairs released cars with each other, with held cars for the same day, and with our open unbooked singles. Pairs post as one gig at `bundle_mult` × (refA + refB), using the existing `chain()` check (12 h limit, both deadlines with margin, 6 h of slack). Unpaired cars post as before. Flags: `hold`, `hold_hour`, `hold_all`, `hold_open`, `hold_km`, `hold_price`.

**The test.** Paired sweeps on dev-07..18 (level 8), then a fresh check on unused seeds.

**Numbers.** dev-07..18, paired. Base reproduces v1am to the cent (deterministic).

| Tag | Release | Ranked | Min on-time | p10 | Median | Mean | Orders |
|---|---|---|---|---|---|---|---|
| e0-base | off | 12/12 | 0.938 | 5,608 | 9,422 | 9,661 | 298 |
| e1-hold18 | 18:00 | 12/12 | 0.922 | 5,385 | 10,247 | 10,364 | 300 |
| **e2-hold16** | **16:00** | **12/12** | **0.931** | **6,826** | 9,452 | **10,690** | 299 |
| e3-hold20 | 20:00 | 12/12 | 0.931 | 5,074 | 10,188 | 9,987 | 297 |
| f1-hold14 (8 of 12 seeds, batch cut by a memory reap) | 14:00 | 8/8 | 0.944 | | | +1,149 vs base on the same 8 | 296 |
| f2-hold12 | 12:00 | 12/12 | 0.925 | 5,503 | 10,243 | 10,326 | 301 |
| f3-h16-keep | 16:00, dropped pair kept at 0.95x | 12/12 | 0.928 | 6,620 | 9,621 | 10,662 | 298 |
| f4-h16-price | 16:00, quote at bundle cost if a held car pairs | 12/12 | 0.924 | 5,357 | 9,128 | 9,745 | 311 |
| f5-h16-km40 | 16:00, pairs up to 40 km | 12/12 | 0.948 | 6,656 | 10,368 | 10,735 | 300 |
| f6-h16-mult85 | 16:00, pair fee 0.85x | 12/12 | 0.938 | 5,809 | 10,264 | 10,648 | 298 |

Release hour peaks at 14:00-16:00. Kill: bundle_keep (noise), hold_price (-945: wins 12 more cars a week at prices that do not pay), bundle_mult 0.85 (noise). hold_km 40 equals 16:00 on 8 of 12 seeds; its better min on-time is one seed (dev-18): noise, keep the simpler default.

hold16 vs base by seed: +1792, +3179, -666, +2631, +1218, +1315, -35, +833, -169, +1154, +1965, -870.
18:00 was too late: release pairs left unbooked into the night (no notifications 23:00-07:00) were split by the 6 h alarm the next day. About 105 cars/week rode in release pairs (offline estimate: 110-165).

**Keep or kill.** Keep, at 16:00 or earlier; 14:00 looks better still (incomplete). Next: finish 14:00 and 12:00, then bundle_keep, hold_price, hold_km, bundle_mult, then a fresh check on dev-19..30 against rc2.

## Fresh check, dev-19..30 (never used for tuning), `hold=true hold_hour=16` vs rc2

| | Ranked | Min on-time | p10 | Median | Mean | Orders |
|---|---|---|---|---|---|---|
| rc2 | 12/12 | 0.935 | 5,394 | 8,868 | 9,364 | 311 |
| **hold 16:00** | **12/12** | 0.930 | **5,605** | **10,463** | **10,707** | 312 |

+1,343/week (+14%). Up on 9 of 12 weeks; the three worst weeks all improve (5,394 -> 5,605, 6,704 -> 8,661, 6,854 -> 8,746).
By seed: +1655, +699, +211, -868, +1957, -1932, +4941, +3476, -655, +459, +1892, +4273.

**Keep.** `hold=true hold_hour=16` is the candidate default for rc3.

## Money preset and lateness pricing on top of the release (dev-07..18; "gated" = margin counted only on ranked weeks)

| Tag | Change on top of hold 16:00 | Ranked | Min on-time | p10 | Mean | Gated mean | Orders |
|---|---|---|---|---|---|---|---|
| e2-hold16 | none | 12/12 | 0.931 | 6,826 | 10,690 | 10,690 | 299 |
| x2-money-h16 | money preset | 9/12 | 0.890 | 9,305 | 12,733 | 9,211 | 367 |
| y1-money-g92-h16 | money + guard 0.92 (g2 alone: 12/12, 10,496) | 10/12 | 0.891 | 9,604 | 11,999 | 10,130 | 360 |
| y2-h16-late12 | late_cost_frac 1.2 | 12/12 | 0.948 | 5,718 | 10,425 | 10,425 | 280 |
| y3-h16-late12-load06 | late 1.2, load_free 0.06 | 12/12 | 0.943 | 7,706 | 11,085 | 11,085 | 301 |
| **y4-h16-late20-load07** | **late 2.0, load_free 0.07** | **12/12** | 0.932 | **8,066** | **11,579** | **11,579** | 291 |

Fresh dev-19..30, money + hold 16: mean 13,234 but 10/12 ranked (gated 11,245) vs money alone 12,063, 9/12.

y4 beats the base on all 12 seeds (+1,918/week, +20%); its worst week is 8,066 vs 5,608. Pricing lateness harder (P(late) x 2.0 x price) moves the gate risk into the quote: long and thin-town cars get dear, and the freed on-time budget buys more safe cars (load_free 0.07). Next: push further (late 3-4, load 0.08-0.10), then a fresh check.

Money line with stricter guards (all + hold 16): y5 guard 0.93: 11/12, mean 10,865. y6 guard 0.94: cut at 4 seeds by a memory reap, 4/4 ranked, 13,057 vs 14,198 for y4 on the same seeds. y7 guard 0.93 + load 0.06: 12/12, min on-time 0.919, mean 10,894.
**Kill the money line**: every ranked variant is below y4 (late 2.0, load 0.07: 11,579, 12/12). Candidate for rc3: `hold=true hold_hour=16 late_cost_frac=2.0 load_free=0.07`, pending a fresh check on dev-19..30.
