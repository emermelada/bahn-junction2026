# One branch with both hold mechanisms (claude/best)

**What we saw.** Two branches forked from 119734b each found a way to pair cars for one driver.
`claude/evening-release` (y4): hold cars for a later day and release them at 16:00 the day before, then pair greedily;
late_cost_frac 2.0, load_free 0.07. `branch-v1-frank` (k18, `--preset chains`): hold a won car up to 8 h to find a
chain partner, plus money settings with the on-time guard at 92%. dev-31..35: y4 12,602/week (on-time >= 0.939),
k18 13,402 (on-time 0.919-0.937). dev-07..18: y4 11,579, k18 11,268, both 12/12.

**The idea.** Put both behind flags on one branch (`claude/best`), defaults = y4, `--preset chains` = k18, and try
combinations. The two mechanisms keep separate state: `held` (evening release) and `chain_held` (chain planner).

**Port check.** Config of every preset compared key by key with the reference runs' saved config: no difference.
Scores to the cent (practice, level 8):

| Run | dev-31 | dev-32 |
|---|---|---|
| defaults (y4) vs r5-y4 | 11,307.82 = 11,307.82 | 7,132.32 = 7,132.32 |
| `--preset chains` vs x-k18 | 9,902.16 = 9,902.16 | 8,297.96 = 8,297.96 |

## Combinations on dev-07..18

| Tag | Change | Ranked | Min on-time | p10 | Mean | Orders |
|---|---|---|---|---|---|---|
| ref y4 | defaults | 12/12 | 0.932 | 8,066 | 11,579 | 291 |
| ref k18 | --preset chains | 12/12 | 0.907 | 9,052 | 11,268 | 354 |
