# Thursday price bump: no gain; rc5 passes the gate

**What we saw.** Over 60 fresh base weeks, late share by the day the order was won: Monday 3.3-3.5%, Tuesday 5.2-5.9%, Wednesday 4.5-6.6%, Thursday 7.2-7.7%, Friday 3.3-5.4%. rc9-05, the week that fails even at ratio 1.45, lost on 108 orders won Monday and Tuesday in a week short of drivers (21-22% of those pickups late); it is an outlier, since Monday wins are the safest in general.

**The idea.** `dealer.thursday_extra` 0.1: price Thursday higher to win fewer of the most often late orders.

**The test.** rc7, rc8, rc9 (36 weeks), paired against rc5 defaults.

| Tag | Ranked (36) | Mean delta | Seeds up |
|---|---|---|---|
| rc5 (ratio 1.45) | 35 | | |
| Thursday +0.1 | 34 | -€93 | 13/36 |

`make check` on rc5 defaults: unit tests pass; dev-01 twice gives €4,812.81 with the same state digest; the replay rebuilds it; dev-01..03 ranked (97.3%, 94.2%, 94.0%).

**Keep or kill.** Kill the Thursday bump. rc5 stands.
