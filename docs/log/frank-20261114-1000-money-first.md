# Money first: Javier's main compared, and a preset that drops the gate guards

## Javier's main vs rc2 on the same 12 weeks (dev-07..18)
Full difference list: `docs/compare-javier-main.md`. Main ran from a worktree (`data/javier-main`, origin/main @ 6475883) with its own defaults.

| | Ranked | Min on-time | Median | Mean |
|---|---|---|---|---|
| main | 12/12 | 0.903 | 6,176 | 6,059 |
| rc2 (v1) | 12/12 | 0.938 | 9,422 | 9,661 |

rc2 earns more on every one of the 12 weeks. Borrowed from main and tested on v1: the lane table (`lane_w`, kept in the money preset) and the per-batch cap (`max_per_batch 6`: -€915, killed).

## Money-first variants (gate ignored), 12 seeds dev-07..18
"No gate" = gov_tight 0, gov_rescue 0, gov_relaxed 0 (no governor tightening, always the cheap escalation), theta 0.7.

| Tag | Change | Ranked | Min on-time | p10 | Median | Mean |
|---|---|---|---|---|---|---|
| rc2 (v1am) | base | 12/12 | 0.938 | 5,608 | 9,422 | 9,661 |
| m1 | no gate | 12/12 | 0.903 | 6,125 | 9,973 | 10,099 |
| m3 | lane table only | 12/12 | 0.930 | 5,593 | 9,267 | 9,810 |
| m5 | no gate + lane | 12/12 | 0.916 | 7,396 | 9,155 | 10,248 |
| m6 | no gate + theta 0.6 | 10/12 | 0.895 | 6,078 | 9,587 | 10,042 |
| m7 | no gate + escalation 1.2-1.4x | 10/12 | 0.890 | 6,183 | 10,140 | 10,468 |
| m8 | no gate + load 0.06 | 9/12 | 0.891 | 6,048 | 10,271 | 10,565 |
| m2 | no gate + load 0.07 | 9/12 | 0.885 | 6,748 | 9,926 | 10,411 |
| m9 | no gate + load 0.09 | 5/12 | 0.830 | 5,994 | 10,346 | 10,263 |
| m10 | no gate + load 0.12 | 4/12 | 0.813 | 4,486 | 8,670 | 9,546 |
| m11 | no gate + lane + cheap escalation + load 0.06 | 8/12 | 0.870 | 7,346 | 10,838 | 11,120 |
| **m12** | **same, load 0.07 (= preset `money`)** | 8/12 | 0.884 | 6,967 | 11,342 | **11,462** |
| m13 | m12 + lane weight 1.5 | 8/12 | 0.881 | 8,208 | 10,373 | 11,403 |
| m14 | m12 + escalation 1.1x only | 5/12 | 0.835 | 7,675 | 10,729 | 11,260 |

Money peaks at load 0.06-0.07: more volume past that loses money even with the gate ignored (late refunds and escalated fees grow faster than revenue).

## Fresh check, preset `money` on dev-19..30

| | Ranked | Min on-time | p10 | Median | Mean |
|---|---|---|---|---|---|
| rc2 | 12/12 | 0.935 | 5,394 | 8,868 | 9,364 |
| money | 9/12 | 0.870 | 6,159 | 12,131 | 12,063 |

+€2,700/week (+29%), more margin on all 12 weeks; 3 of 12 weeks fall under the 90% delivery minimum.

**Use:** `./run_final.sh --preset money` (or `--preset money` on any practice/board command). rc2 without the preset stays the gate-safe choice.
