# Load pricing: win only what the drivers of that day can move

**What we saw.** Lateness was ~7.5% on average and spread evenly over lanes, hours and local driver supply, so no static feature could pick the late cars. One week (dev-08) put 157 of our cars due on Friday against 36–96 on other days, and 35 of the 157 went late. Over 108 (seed, day) pairs from 4 policies, the late rate follows our load that day: cars due / drivers in the world under 0.06 → 2.7% late, 0.06–0.09 → 5.4%, 0.09–0.12 → 8.7%, 0.12–0.15 → 10.0%, above 0.15 → 12%. The marginal car on a day at 0.10 load adds about 0.14 expected late orders (its own risk plus what it does to the others), above the 10% the gate allows.

**The idea.** Each option's quote carries a shadow cost that grows with our load on its deadline day: one typical fee per 0.05 of load above 0.07. The EV pricing then quotes higher on busy days and steers dealers to options due on quiet days. The world's driver count comes from the roster, so nothing depends on a seed.

**The test.** 12 seeds dev-07..dev-18, level 8, same code otherwise (v1o = refit on-time model + dilution bar + bundles + 6 h alarm).

| | Ranked | Min on-time | p10 margin | Median | Mean | Orders |
|---|---|---|---|---|---|---|
| v1o (no load cost) | 9/12 | 0.875 | 3,957 | 6,882 | 7,371 | 364 |
| v1p (load cost) | 11/12 | 0.896 | 5,629 | 8,652 | 8,958 | 341 |

Margin rose on 10 of 12 weeks with 6% fewer orders: the cars we stopped winning were the ones that went late or needed escalated fees.

**Keep.** Default from now on (`load_free = 0.07`, `load_slope = 1.0`).

Also in this round, on fresh seeds dev-07..12: the on-time model refit on 6,291 orders of the current policy (held-out-seed AUC 0.71, calibrated within 1–2 points) plus a dilution bar in rescue took ranked weeks from 3/6 to 5/6. Killed: view-triggered raise (−€1.0k/week), same-day-only steering (no gain), crunch detector (rarely fires).
