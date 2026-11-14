# rc5: batch cap confirmed; week price level and low opening fee fail

**What we saw.** The top teams make €40-49 an order; we make about €29. Two levers were still fixed guesses: our price ignores this week's competitor level, and fees open at 1.0x even when cheaper drivers would book.

**The ideas.** (1) week_level: fit this week's competitor level from our own wins and losses (P(win) = sigmoid(A0 + d - 8 x ratio), fading, pulled to 0 while thin) and move the ratio by d / 8, capped at ±0.25. (2) Open long-slack gigs at 0.8x, raise to 1.0x 12 h before the last pickup and to 1.8x 6 h before, if still unbooked.

**The test.** 12 fresh seeds (rc5-01..12), all with the batch cap 6.

| Tag | Ranked | Min on-time | p10 | Median | Mean delta |
|---|---|---|---|---|---|
| rc5-base (rc3 + batch cap 6) | 12/12 | 90.4% | €4,661 | €5,675 | |
| + week_level 1.0 | 10/12 | 87.1% | €2,426 | €3,666 | -€2,383 |
| + fee 0.8x with two raises | 10/12 | 86.8% | €3,281 | €5,770 | -€786 |
| + both | 7/12 | 87.1% | €1,067 | €3,905 | -€3,001 |

Money per week on rc5-base: revenue €29,001, driver fees €21,895 (75% of revenue), late refunds €628, failed visits €226. Fees: 60% of orders pay about 1.0x the typical fee, 31% about 1.4x (+€2,372 a week over typical), 8% a raise (+€917), 1% urgent (+€461).

**Keep or kill.** Kill both. week_level's reference week sits above our real win rate, so it mostly cut prices and bought volume we cannot move. The low opening fee loses on-time share. Keep the batch cap: ranked 12/12 on a second fresh set, now the default (tag rc4).
