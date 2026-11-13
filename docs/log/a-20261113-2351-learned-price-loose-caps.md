# Learned price and looser caps on fresh seeds: neither adopted

**What we saw.** Three of nine rc1 weeks earn under €1,500 (rc1-03, -07, -08) on 50-80 orders. On rc1-07 only 10% of our real quotes win (rc1-03: 12%), against 33% on rc1-05: the competitor is cheap in those worlds.

**The ideas.** b13: the learned price (live win curve, price that maximises P(win) x (price - fee - €15 floor)). b14: looser caps (backlog 25, floor €10), since on-time share had room (94-100%).

**The test.** Same 9 rc1 seeds, paired against b11.

| Tag | Ranked | Min on-time | p10 | Median | Sum vs b11 |
|---|---|---|---|---|---|
| b11 | 9/9 | 94.0% | €1,154 | €3,606 | |
| b13 learned price | 9/9 | 96.6% | €702 | €3,519 | +€1,968 |
| b14 backlog 25, floor €10 | 9/9 | 92.1% | €1,181 | €3,508 | -€566 |

On rc1-07 the learned price moved the quoted ratio up, from 1.6 (1.4 plus the same_day extra) to 1.75-1.8, and won 29 orders instead of 54. With fees at 1.4x the typical fee, a car needs about 1.43x list to clear the floor, so in a cheap-competitor week no lower price pays: the optimiser raises the price and wins less.

**Keep or kill.** Kill both for now: b13 makes the worst week worse (€1,382 to €702), b14 loses money and on-time share. In cheap-competitor weeks the lever is the driver fee, not the price.
