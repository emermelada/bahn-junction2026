# Chain-aware quoting on k18: more orders, a worse worst week; diagnosed

**What we saw.** k18 declines about 225 requests a week for having no positive EV as a single car; a two-car chain costs about 0.85x the typical fees against 1.14x for a single. Franko's `bundle_price` flag (quote a car at chain cost when it fits one of our held cars or open singles) existed but was off and untested.

**The idea.** k18 + `bundle_price=1` (bundle_mult 0.8).

**The test.** rc10-01..12, paired against k18.

| Tag | Ranked | Min on-time | p10 | Median | Mean | Orders a week | Worst week |
|---|---|---|---|---|---|---|---|
| k18 | 12/12 | 90.1% | €6,731 | €10,797 | €10,791 | 361 | €6,731 |
| k18 + bundle_price | 12/12 | 91.1% | €4,629 | €11,850 | €11,197 | 392 | €4,629 |

+€406 mean and +31 orders a week, but rc10-07 falls from €6,731 to €4,629. In rc10-07 the flag posted 76 more cars (307 vs 231) yet formed only 8 more chains (43 vs 35); escalations rose from 75 to 116 and deadline warnings from 30 to 55. The quote-time check (`chainable`: any held or open single delivering within 25 km, same deadline day) is far looser than the planner's chain test (5 h driving cap, lead, both deadlines with an hour to spare), so most cars priced as chain partners went out as discounted singles.

**Keep or kill.** Do not keep as is (worse worst week). Fix instead of kill: `bundle_price_strict` on a/frank-plus prices at chain cost only when the planner's own test passes against a held car. Running: chains_plus + bundle_price + strict on rc10.

## Strict version (on chains_plus)

| Tag | Ranked | Min on-time | p10 | Median | Mean | Orders a week | Worst week |
|---|---|---|---|---|---|---|---|
| chains_plus (k18 + batch cap 6) | 12/12 | 91.8% | €6,731 | €11,729 | €11,041 | 357 | €6,731 |
| + bundle_price + bundle_price_strict | 12/12 | 91.0% | €3,745 | €11,161 | €10,889 | 380 | €3,745 |

The strict test still lets 23 more orders a week in, loses €152 a week on average, and rc10-07 falls again (€6,731 to €3,745): in that week drivers do not take chains, however carefully the partners are chosen. Kill: `bundle_price_strict` stays in the code on a/frank-plus, default off. chains_plus stays the recommendation.
