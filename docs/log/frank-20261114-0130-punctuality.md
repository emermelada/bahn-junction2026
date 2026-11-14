# Punctuality first: a tighter load threshold (12 seeds dev-07..18)

**What we saw.** Saturday's board: the top teams make ~€14k/week at ~97% on time; we were at ~€9k and 92–96%. They are more punctual *and* earn more per car, so the gap is margin per car, not volume.

**The idea.** Lower the load at which a car starts to cost extra (load = our cars due that day / drivers). Fewer late cars keep dealer trust counts from being halved and shrink the escalated-fee tail.

| Tag | load_free | load_slope | Ranked | Min on-time | p10 | Median | Mean | Orders |
|---|---|---|---|---|---|---|---|---|
| v1aa (base) | 0.07 | 1 | 12/12 | 0.925 | 6,773 | 8,135 | 9,000 | 332 |
| v1am | 0.05 | 1 | 12/12 | 0.938 | 5,608 | 9,422 | 9,661 | 298 |
| v1an | 0.04 | 1 | 12/12 | 0.934 | 6,067 | 9,015 | 9,474 | 274 |
| v1ao | 0.05 | 2 | 12/12 | 0.931 | 6,132 | 7,738 | 8,541 | 263 |

**Keep.** load_free 0.05 (default from commit "load_free 0.05 (v1am)"): +€660/week, 10% fewer cars, better worst on-time. p10 dropped on one week (dev-11); within noise.
