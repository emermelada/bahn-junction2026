# Same_day extra 0.3 and short-slack fee 1.5: both worse

**What we saw.** same_day orders run 7% late against 2% for next_day; gigs with little slack miss more often.

**The ideas.** `dealer.same_day_extra` 0.3 instead of 0.2 (steer more dealers to next_day); `driver.fee_open` 1.5 instead of 1.4 for short-slack gigs.

**The test.** rc7, rc8, rc9 (36 weeks), paired against rc5 defaults.

| Tag | Ranked (36) | Mean delta | Seeds up | Worst three weeks | Min on-time |
|---|---|---|---|---|---|
| rc5 | 35 | | | -€345, €1,627, €2,503 | 84.4% |
| same_day extra 0.3 | 34 | -€98 | 14/36 | -€341, €1,612, €2,100 | 81.2% |
| short-slack fee 1.5 | 34 | -€222 | 8/36 | €166, €1,462, €2,252 | 84.2% |

Win rate of our real quotes by weekday on the rc5 runs: Monday 18.2%, Tuesday 27.1%, Wednesday 26.2%, Thursday 26.8%, Friday 31.3%. The competitor raises its prices each morning for dealers whose requests we mostly lose, and on Monday it has not reacted yet.

**Keep or kill.** Kill both. Next: price Monday lower (monday_extra -0.05 and -0.1), where we win least and the wins are the least often late (3.3%).

## Monday price (same 36 weeks)

| Tag | Ranked (36) | Mean delta | Seeds up | Worst three weeks | Min on-time |
|---|---|---|---|---|---|
| rc5 | 35 | | | -€345, €1,627, €2,503 | 84.4% |
| monday_extra -0.05 | 34 | +€179 | 24/36 | -€78, €2,009, €2,170 | 83.2% |
| monday_extra -0.10 | 33 | +€44 | 19/36 | -€466, €1,608, €1,794 | 80.7% |

-0.05 is the second near-miss (after fee_raise 1.5): a small, broad gain, but one more unranked week. Next: both together on a new fresh set (rc10).
