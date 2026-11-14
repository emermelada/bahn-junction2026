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
