# Counting deadline warnings as whole late orders: no change

**What we saw.** On rc7-06 (82.0% on time) the governor went tight only on Thursday, though Wednesday had 7 deadline warnings; each unheld order with a warning counted as half a late order in the projection.

**The idea.** `driver.gov_warning_weight` 1.0 instead of 0.5, so the projection crosses 5% a day earlier.

**The test.** rc7-01..12 and rc8-01..12, paired against rc4 defaults.

| Tag | Ranked | Min on-time | p10 | Median | Mean delta | Seeds up |
|---|---|---|---|---|---|---|
| rc7-base | 11/12 | 82.0% | €3,589 | €8,341 | | |
| rc7 warning weight 1.0 | 11/12 | 82.0% | €3,589 | €8,341 | -€98 | 0/12 |
| rc8-base | 12/12 | 92.0% | €3,719 | €5,763 | | |
| rc8 warning weight 1.0 | 12/12 | 91.8% | €3,690 | €5,770 | -€38 | 1/12 |

rc7-06 is identical to the cent: the governor is not what lets those orders in. They are next_day orders with their last pickup on Thursday, which tight mode does not block.

**Keep or kill.** Kill. Note for the next idea: requests that offer only same_day are about 31% of all requests, and we win almost none of them (10 in four rc8 weeks), because the same_day extra (+0.2) meant to steer dealers to next_day also applies when there is nothing to steer to.
