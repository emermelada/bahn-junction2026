# rc2: fresh seeds expose the last-Monday crunch

**What we saw.** The defaults after b18 (long-slack fee 1.0x), on 12 new seeds (rc2-01..12): ranked 8/12, median €8,440, p10 €5,908, on-time 87.1% to 98.5%. The four misses (rc2-01, -09, -10, -11) are at 87.1-89.3%. Tuning on rc1 thinned the margin above the gate on unseen weeks.

Late orders by the day of their last pickup (won / late):

| Seed | Drivers | On time | Busiest day | Last Monday (d7) |
|---|---|---|---|---|
| rc2-09 | 726 | 88.4% | d4 58/6 | 130/22 |
| rc2-01 | 815 | 89.3% | d4 85/15 | 123/14 |
| rc2-11 | 635 | 87.1% | d1 54/13 | 105/13 |
| rc2-10 | 735 | 89.0% | d3 70/14 | 79/4 |
| rc2-06 | 940 | 96.5% | d4 118/9 | 190/5 |
| rc2-08 | 949 | 98.5% | d4 66/2 | 140/2 |

Every Friday next_day order has its last pickup on the last Monday; the backlog cap only counts orders due within a day, so it never sees them. Weekday spikes (for example rc2-11 d1, rc2-03 d2) look like outage days in towns with few drivers.

**The ideas.** b22: no cheap long-slack fee when the last pickup is on the last Monday. b23: cap won orders per last-pickup day at 0.14 x the drivers in the world.

**Keep or kill.** Pending (both on rc2, paired against rc2).
