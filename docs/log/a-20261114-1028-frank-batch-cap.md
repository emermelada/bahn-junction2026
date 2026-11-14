# Batch cap on Franko's k18: kept as preset chains_plus

**What we saw.** k18 on our fresh rc10: 12/12 ranked but min on-time 90.1% (rc10-02); bulk batches (a yard sending many cars) made our own bot miss the gate.

**The idea.** k18 + `max_per_batch=6` (his existing flag, off in k18).

**The test.** Franko's harness from the worktree, rc10-01..12, paired.

| Tag | Ranked | Min on-time | p10 | Median | Mean | Orders a week | 2nd / 3rd worst |
|---|---|---|---|---|---|---|---|
| k18 | 12/12 | 90.1% | €6,731 | €10,797 | €10,791 | 361 | €7,824 / €8,262 |
| k18 + batch cap 6 | 12/12 | 91.8% | €6,731 | €11,729 | €11,041 | 357 | €8,262 / €8,514 |

**Keep or kill.** Keep: preset `chains_plus` on our branch `a/frank-plus` (629708e), Franko's branch untouched. `make final-frank` and `make board-frank` now play `chains_plus` from ../frank-plus. Next: `bundle_price` (chain-aware quoting) on top.
