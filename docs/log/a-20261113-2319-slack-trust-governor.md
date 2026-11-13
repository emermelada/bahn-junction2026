# Minimum slack, trust pricing, governor and one early raise: ranked on all three DEV seeds

**What we saw.** After the margin floor (b4), late orders were mostly cars booked after `lastPickupAt`, and gigs posted with under 3 hours to it almost never booked.

**The idea.**
- b6: decline an option whose latest pickup (deadline minus road minutes, minus charging) is under 4 hours after `respondBy`; scale prices by the dealer's trust factor (1% per on-time order, level 8).
- b7: b6 plus the governor (projected late share above 5% means no same_day and half the backlog; above 8%, only pickups with 30 or more drivers within 30 km) and one raise to 1.8x the typical fee for a gig still open 6 hours before `lastPickupAt`.

**The test.** dev-01..03, level 8.

| Tag | dev-01 | dev-02 | dev-03 | On time | Ranked |
|---|---|---|---|---|---|
| b4 (floor) | €3,819 (201) | €2,940 (193) | €3,245 (253) | 87.4-90.5% | 1/3 |
| b6 (+slack, trust) | €3,670 (143) | €3,653 (181) | €5,140 (257) | 89.9-94.5% | 2/3 |
| b7 (+governor, raise) | €3,186 (124) | €3,841 (182) | €4,937 (228) | 91.1-96.2% | 3/3 |

On b6 dev-03, Friday alone won 139 orders (59 from Vantaa, 84 same_day): most likely the competitor's outage, when dealers in one region pay a backup 30% more. Most of that week's late cars came from that day.

**Keep or kill.** Keep all four; b7 is the default. Not yet tested on fresh seeds (rc1 is queued). Next: a cap per pickup town and day (b9), the learned price (b8).
