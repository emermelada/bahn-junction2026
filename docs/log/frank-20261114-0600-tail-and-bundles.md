# The expensive-fee tail and bundle-aware pricing (A/B vs rc2 = v1am, 12 seeds dev-07..18)

## 1. Can we see the expensive cars coming?
**What we saw.** 22% of won cars end late or above 1.3x the typical fee; together they lose ~€2.3k/week.

**Analysis** (`lab/frank/expensive.py`, 14,181 orders of the current policy, held out by seed):
- Expensive or late is partly predictable: AUC 0.67 (min 0.59). Drivers: low typical fee, long drive, little slack, high load, overnight work, private address.
- But flagged cars still pay: the riskiest 20% earn €29/car vs €33 for the rest. Declining them loses money.
- A direct margin model (gradient boosting, held-out correlation 0.45) finds only the worst 5% at −€9/car: about €150/week to gain by declining. No simple rule (short hops, low fee, private) catches them; short hops still average +€11.6.

**Dispatch use tested** (open flagged cars at 1.3x so they book before drivers wait for raises):

| Tag | Change | Ranked | Min on-time | p10 | Median | Mean |
|---|---|---|---|---|---|---|
| v1am (rc2) | base | 12/12 | 0.938 | 5,608 | 9,422 | 9,661 |
| h1 | hot opening 1.3x for P(expensive) ≥ 0.3 | 12/12 | 0.936 | 5,032 | 8,565 | 9,274 |
| h2 | same, P ≥ 0.4 | 12/12 | 0.938 | 5,011 | 8,623 | 9,232 |

**Kill.** The tail is mostly not predictable from what a request says; it comes from how the day unfolds.

## 3. Pair return legs at quote time
Quote a car at the bundle cost when it chains with one of our open single-car gigs.

| Tag | Change | Ranked | Min on-time | p10 | Median | Mean | Bundles/week |
|---|---|---|---|---|---|---|---|
| v1am (rc2) | base | 12/12 | 0.938 | 5,608 | 9,422 | 9,661 | 27 |
| b1 | bundle-aware quote, 0.8x | 12/12 | 0.932 | 5,367 | 8,664 | 9,110 | 31 |
| b2 | same, 0.9x (8 runs; 4 lost to a local DNS failure) | 8/8 | 0.927 | 4,702 | 8,453 | 7,866 | 18 |

**Kill.** Cheaper quotes add only ~4 bundles a week. Most gigs book within minutes at the opening fee, so an open partner rarely exists when a new car is won. More bundling would need holding cars back before posting, which costs slack.

**Conclusion.** Neither lever closes the gap to the leaders; rc2 stays the release.
