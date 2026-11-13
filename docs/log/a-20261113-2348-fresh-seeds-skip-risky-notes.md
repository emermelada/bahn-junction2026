# Fresh seeds, risky request kinds, and the notes reader

**What we saw.** rc1, the b7 defaults on 9 fresh level 8 seeds: ranked 8/9, median €3,588, worst week €907; rc1-01 missed the gate at 89.7%. Late rate by request kind over all 9 weeks:

| Kind | Option | Won | Late |
|---|---|---|---|
| dealer to dealer | next_day | 565 | 2% |
| dealer to dealer | same_day | 564 | 7% |
| private pickup | next_day | 39 | 23% |
| private delivery | next_day | 10 | 20% |
| trade-in | next_day | 44 | 32% |

On rc1-01, 6 of 15 late orders had a private delivery (due 30 minutes after the booked hour) and 3-4 had a note that the delivery site closes early.

**The ideas and tests.** All on the same 9 rc1 seeds, paired.

| Tag | Change | Ranked | Min on-time | p10 | Median | Sum vs rc1 |
|---|---|---|---|---|---|---|
| rc1 | b7 defaults | 8/9 | 89.7% | €907 | €3,588 | |
| b11 | skip trade-ins and private addresses | 9/9 | 94.0% | €1,154 | €3,606 | -€394 |
| b12 | notes reader (plates, manual, windows) | 9/9 | 90.0% | €962 | €3,600 | +€1,416 |

Notes reader on the corpus of 1,686 distinct notes: plates 50 of 50 found, 3 false alarms (trade-ins, cautious); manual gearbox 53 of 53 found, 2 false alarms. Windows use the kit starter's keyword reader unchanged.

b10 (b7 plus the learned price, DEV seeds): 3/3 ranked, €3,017 / €3,123 / €6,430 against b7's €3,186 / €3,841 / €4,937. Within noise; not adopted yet.

**Keep or kill.** Keep b11 (the gate margin goes from 89.7% to 94.0% for almost no money) and b12. Both are defaults now. Next: the learned price and looser caps on top (b13, b14), now that on-time share has room.
