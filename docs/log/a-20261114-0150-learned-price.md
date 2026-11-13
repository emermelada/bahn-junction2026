# Learned price (b8): ranked 3/3 with the highest on-time share so far

**The idea.** Replace the fixed 1.4x ratio with the live win model (acceptance curve on price / (list x trust), prior from the price ladder, half-life 4 hours), choosing the ratio that maximises P(win) x (price - fee - €15 floor), with a ±0.04 seeded jitter.

**The test.** b6 settings plus `dealer.learn_price=true` (no governor, no early raise), dev-01..03.

| Tag | dev-01 | dev-02 | dev-03 | On time | Ranked |
|---|---|---|---|---|---|
| b6 | €3,670 (143) | €3,653 (181) | €5,140 (257) | 89.9-94.5% | 2/3 |
| b7 (b6 + governor + raise) | €3,186 (124) | €3,841 (182) | €4,937 (228) | 91.1-96.2% | 3/3 |
| b8 (b6 + learned price) | €4,020 (120) | €2,914 (108) | €6,751 (216) | 95.4-97.2% | 3/3 |

**Keep or kill.** Promising, not yet the default: next test is b7 + learned price on the same seeds, then fresh seeds.
