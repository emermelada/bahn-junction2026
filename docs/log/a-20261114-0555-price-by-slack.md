# Price by slack: more cheap work hurts; capacity binds

**What we saw.** Options with a day or more to their last pickup cost a 1.0x fee and rarely miss (1.3-6%); short-slack options cost 1.4x and miss more. We price both at the same ratio.

**The idea.** `dealer.ratio_long` / `ratio_short`: price long-slack options lower to win more of the cheap work and short-slack options higher.

**The test.** Paired against rc4 defaults.

| Tag | Change | Ranked | Min on-time | Median | Mean delta | Orders a week |
|---|---|---|---|---|---|---|
| rc8-base | | 12/12 | 92.0% | €5,763 | | 194 |
| rc8 slackpx | long -0.1, short +0.1 | 11/12 | 88.9% | €4,743 | -€865 | 210 |
| rc7-base | | 11/12 | 82.0% | €8,341 | | 240 |
| rc7 slackpx | long -0.1, short +0.1 | 8/12 | 88.0% | €5,434 | -€1,231 | 263 |
| rc8 slackpx2 | short +0.2 only | 12/12 | 92.7% | €5,828 | +€137 | 187 |

**Keep or kill.** Kill. Every idea that adds orders (lower prices, looser caps, cheaper same_day) has cost money and on-time share: drivers, not requests, are the limit, also for long-slack work. The top teams move about 300 orders a week at 97% on time against our 190-240, so their dispatch reaches more drivers in time. Our fees are the cheapest we found (1.0x); the next test is the opposite regime: higher fees to reach more drivers, paid for by higher prices.
