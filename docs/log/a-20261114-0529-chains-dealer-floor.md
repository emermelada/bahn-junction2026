# Chain offers, per-dealer level, higher floor: all within noise

**What we saw.** The top teams earn €40-49 an order; we earn about €28. Three more ideas aimed at cost per car and price per dealer.

**The ideas.**
- Chain offers: when a driver on one of our booked gigs will finish within 45 road minutes of an open gig's pickup, in time, offer them that gig at 0.8x or 0.6x the typical fee (HANDBOOK: for a driver who already has one of our gigs, a second costs only the extra time and tickets).
- Dealer level: each dealer's ratio moves by its win rate relative to this week's average (logit difference / 8, pulled to the average for 30 quotes, capped at ±0.2).
- Margin floor €25 instead of €15, to keep drivers for the better orders.

**The test.** 12 fresh seeds rc6-01..12, paired against rc4 defaults.

| Tag | Ranked | Min on-time | p10 | Median | Mean delta | Orders a week |
|---|---|---|---|---|---|---|
| rc6-base (rc4) | 11/12 | 89.6% | €4,422 | €5,723 | | 225 |
| chain offers 0.8x | 12/12 | 90.6% | €4,697 | €5,789 | +€160 | 227 |
| chain offers 0.6x | 11/12 | 89.6% | €4,422 | €5,809 | +€48 | 225 |
| dealer level 1.0 | 11/12 | 87.8% | €4,306 | €5,845 | +€43 | 229 |
| floor €25 | 11/12 | 85.9% | €4,049 | €4,643 | -€545 | 168 |

Chain offers on one week: 323 sent at 0.8x, 2 accepted; 474 at 0.6x, 1 accepted. Drivers almost never take a direct offer below the app's fee.

**Keep or kill.** Kill all three: no gain beyond the spread between seeds. The 12/12 of chain 0.8x is one seed moving from 89.6% to 90.6%, not a mechanism. Next: the level 8 events nobody announces (the outage day and the price-war day) and a looser governor early in the week.
