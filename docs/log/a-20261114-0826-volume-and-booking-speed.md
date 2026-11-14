# Booking speed and volume: the gap is cost per car, not drivers' reach

**What we saw.** Round "Saturday 00:00", same five weeks for every team: the top ten make €15,095-17,185 a week on 373-458 orders at €35-43 an order and 95-98% on time; we made €7,453 on 254 orders at €29. On rc9 (rc5 defaults), 96% of our posted gigs get a driver, median 3 minutes after posting (p25 1 minute, p75 24); every gig is viewed; the 4% that never book were seen by many drivers. Drivers take our cars almost at once at about 1.0x the typical fee.

**The idea.** If drivers are not the limit at our prices, win more orders: ratio 1.35, backlog 25, margin floor €10 (vol1); vol1 plus private addresses and trade-ins (vol2).

**The test.** rc10-01..12, paired against rc5.

| Tag | Ranked | Min on-time | p10 | Median | Mean | Orders a week |
|---|---|---|---|---|---|---|
| rc5 | 11/12 | 88.4% | €3,462 | €5,552 | €5,371 | 173 |
| vol1 | 11/12 | 84.4% | €2,707 | €6,185 | €5,680 | 243 |
| vol2 | 10/12 | 80.9% | €2,942 | €5,321 | €4,952 | 263 |

**Keep or kill.** Kill both for now: vol1 wins 70 more orders a week but earns only about €4 on each and lowers the worst on-time week; vol2 loses money. The top teams earn €35-40 on 430 cars, so their cost per car must be far lower than ours: since our gigs book within minutes, we very likely pay drivers more than they need. Next (after the 09:00 round): flat lower fees with no raise ladder, then volume on top.
