# Overnight summary (14 Nov, 02:00-07:30)

**Where we stand.** Tag rc5 (= main): rc3 + batch cap 6 + quote ratio 1.45. On fresh weeks it never trained on: rc7+rc8+rc9 ranked 35/36, rc10 11/12, so 46 of 48 (96%), mean margin about €6,000-6,300 a week. `make check` passes; the chaos test (killed twice mid-week) passes on rc5.

**Kept tonight.**
| Change | Evidence |
|---|---|
| batch cap 6 (`driver.max_per_batch`) | rc4 fresh 10/12 -> 12/12, rc5 fresh 12/12, mean +€165 |
| quote ratio 1.45 (was 1.4) | 36 fresh weeks: ranked 35 vs 33, same mean, worst week -€345 vs -€2,732 |

**Killed tonight (no gain beyond the spread between seeds, or worse).** Lane table, week price level, low opening fee with two raises, trust investment, chain offers, per-dealer price level, margin floor €25, outage and price-war detectors, loose governor, trouble towns, explicit stop windows, warning weight 1.0, same_day extra only with a slower option, price by slack, high-fee regimes, chains v2, ratio 1.5, Thursday bump, late raise 1.5 (closest call: +€106, 26/36 up, worse worst week), min slack 360, same_day extra 0.3, short fee 1.5, Monday -0.05 (+€179, 24/36 up, one more unranked week), raise 1.5 + Monday -0.05 on rc10 (+€103, 6/12 up).

**What the data says about the gap to the top teams** (they make €40-49 an order on about 300 orders a week, we make about €28 on 190-240):
- Drivers are the limit. Every change that adds orders (lower prices, looser caps, cheaper fees, more same_day) loses money and on-time share.
- Fees are already at the cheapest level that books in time (1.0x the typical fee with a day of slack); lower fees lose on-time share, higher fees lose orders.
- Direct offers almost never land (2 of 323 at 0.8x, 0 of 305 at 1.8x); two-car chains form only about 20 times a week.
- The missed weeks (about 1 in 24) are weeks with a deep driver shortage where late orders pile up in small towns or after a burst of early wins; no early signal we tried (booking speed, warnings, town trouble) flags them in time.

**For the human.** Ranking round at 09:00: `git pull && for i in (seq 5); while not make board; sleep 20; end; end`. Test final at 14:00: `make final` in its own terminal, on the machine that will run the final.
