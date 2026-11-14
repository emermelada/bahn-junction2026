# v1 (branch-v1-frank, rc2) vs Javier's main (origin/main @ 6475883)

Both are Python bots on the same kit. Same-week results are at the end.

## Quoting

| | v1 (rc2) | main |
|---|---|---|
| Price | EV maximiser per option: argmax over ratio of P(win) x (price x (1 - risk) - cost - load cost) | One fixed ratio, 1.4 x list x trust, +0.2 on same_day; `learn_price` exists but is off |
| Competitor model | Live logistic, slope 6.7: world level + today's shift + per-dealer shift | Fixed ratio; a learned curve (prior from price ladder, half-life 4 h) only behind a flag |
| Lane factor | none (now behind the `lane_w` flag, using main's table) | `lanes.json`: per-lane shift fitted on 303,778 quotes over 443 weeks; `lane_weight` flag, off (+€180, in noise) |
| Margin floor | min EV €2 | decline if price - planned fee < €15 |
| Trust | prices x (1 + count/100), counted from the ledger | same |
| Options quoted | every option whose P(on time) clears the bar | every serviceable option |

## Which cars we take

| | v1 | main |
|---|---|---|
| On-time | logistic model refit on 6,291 of our orders (slack, drive, supply, premium, private, note...) | no model; hard rules |
| Bar | P(on time) >= 0.80; 0.88 when the projection is under 0.95; dilution bar under 0.93 | governor on projected late share: tight at 5% (no same_day, half backlog), rescue at 8% (only easy pickups) |
| Capacity | load price: cars due per day / drivers, one typical fee per 0.05 above 0.05 | backlog cap: decline while 15 orders due within a day have no driver |
| Slack | in the on-time model (+ 1.5 h floor) | decline options with under 4 h of slack |
| Trade-ins | priced by the model | declined (32% late) |
| Private addresses | priced by the model (-0.64) | declined (20-23% late) |
| Bulk batch | none (now `max_per_batch` flag) | `max_per_batch` 6 tested (+€165, 12/12 ranked on rc4) |
| Notes | full reader (FI/SV/EN, days, corrections): 993/993 on held-out notes | keyword reader (68 lines): plates, manual, windows near keywords |

## Fees and dispatch

| | v1 | main |
|---|---|---|
| Opening fee | 1.05 x typical | 1.4 x; flat 1.0 x when the last pickup is a day or more away (not over the weekend) |
| Raises | 1.25 x at 8 h and 1.6 x at 5 h before lastPickupAt (note deadlines count) | one raise to 1.8 x at 6 h before lastPickupAt |
| Escalation | own alarm 6 h before: 1.4-1.8 (projection >= 0.95), 1.7-2.6, or 2.0-4.0 (rescue) | after the world's warning: 1.5 x rising a quarter every 30 min to 2.5 x |
| Late cars | cheap late plan 1.2 -> 1.5 -> 2.0 x over 12 h | same steep fees as any urgent car |
| Bundles | on: pair a new car with an open single gig of ours (~27/week) | off: holding cars up to 2 h for a partner cost on-time share |
| Offers | off (2 of 560 accepted) | none |

## Runtime

| | v1 | main |
|---|---|---|
| Practice | 12-minute steps by day, event wakes at night (~500 requests a week) | advance to wake events |
| Live | stream, batched actions every 0.3 s, snapshot resync every 60 s, rebuild on restart | live runner, chaos test, emulator at real final speed (0 refused actions) |
| Tests | none beyond A/B harness | unit tests, determinism check, `make check` |

## Same weeks (dev-07..18, level 8)

| | Ranked | Min on-time | Median | Mean |
|---|---|---|---|---|
| main | 12/12 | 0.903 | 6,176 | 6,059 |
| rc2 (v1) | 12/12 | 0.938 | 9,422 | 9,661 |
| v1 preset `money` (m12) | 8/12 | 0.884 | 11,342 | 11,462 |

rc2 earns more than main on all 12 weeks. Details: `docs/log/frank-20261114-1000-money-first.md`.
