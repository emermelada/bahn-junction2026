# Price ladder and the shape of driver bookings

**What we saw.**
1. With quotes at 1.3x list and fees rising from 1.2x to 2.0x the typical fee in five hourly steps (5 DEV seeds, level 8), the bot wins 536 to 687 orders, 58% to 70% on time, margin -€24k to -€42k. Not ranked on any seed.
2. Bookings are bimodal (dev-02, 804 bookings): 306 at the 1.2x opening fee, mostly in the first minutes, and 298 at the 2.0x top. Almost none in between. Drivers learn the raise pattern and wait for the top, as the rules say.
3. 121 of 175 late orders on dev-02 were first booked after their `lastPickupAt`: no driver took them in time. Visit failures (15), drops and no-shows (29) are smaller causes.
4. Economics (dev-01, 1,035 requests): list price over typical fee has median 1.13 (p10 0.94, p90 1.50). At 1.4x list and a 1.4x fee, a car earns about 0.16 of its list price, about €12.

**The idea.** Price ladder: quote one random option at a random ratio in [1.0, 1.7] of list, Monday and Tuesday only, to map win rate against price.

**The test.** `--flag dealer.ladder=0.7`, seeds lab-p1 and lab-p2 (lab-p3 failed to start: the team's 8 practice slots were full).

| Ratio | 1.00 | 1.10 | 1.20 | 1.25 | 1.30 | 1.40 | 1.50 | 1.60 |
|---|---|---|---|---|---|---|---|---|
| Win rate, both seeds | 78% | 85% | 70% | 50% | 36% | 43% | 21% | 10% |
| lab-p1 | 85% | 81% | 77% | 68% | 45% | 50% | 27% | 15% |
| lab-p2 | 71% | 88% | 65% | 33% | 28% | 35% | 12% | 6% |

About 60 requests per bin. The two worlds differ by about 0.1 in ratio at the same win rate: the competitor level is a property of the week and must be learned live.

**Keep or kill.** Keep: flat fees (no ladder of raises), a cap on how many won orders wait for a driver, and prices well above list. Next: a fee ladder to find the flat fee that books in time.
