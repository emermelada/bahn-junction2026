# V5 quote/volume part (branch claude/v5-quote)

## Flags (config.py, all default off)
- `safe_admit=(p_min, cost_mult, max_load)`: in Desk.price(), an option that would be `noev` (or ratio <= 0) gets a second
  best_ratio at cost = referenceFee x cost_mult. Conditions: p_ok >= p_min, drive < `safe_admit_drive` (240), the delivery is not a
  desert (desert_n), due_load(deadline day) < max_load, not scarce, not menu. It only admits cars that would otherwise be declined
  and never reprices a car we already quote (MARKET: -396/wk). Log: `<kind>:admit(r=,p=,ev=,c=,L=,n=<admits today>)`.
- `safe_admit_fri=false`: no admits for options due on Friday (day 4).
- `safe_admit_fee1=false`: also take min with fee1.quote_cost()'s expected fee + rescue. It stays off because on the dev31 fixture
  fee1 planned 0.76-0.85x typical, while lone cars actually cost ~1.04x under the release.
- Admit counter `desk.admits[day]` counts requests, not options (set `desk.admitted`). It is rebuilt exactly after a restart,
  because rejoin replays every price_request through price(). It is only used for logging.
- `scarcity=(fee_typ, warned_share)`: `check_scarcity()` runs from handle() before each event, at every hour boundary H in
  [`scarcity_from`=2880, `scarcity_until`=4320]. It uses only events with at < H in [H-1440, H). The week is scarce if the mean booked
  fee/typical of single-order gigs (>= `scarcity_min_n`=20 bookings) >= fee_typ, or if distinct warned orders / won orders
  (>= 20 wins) >= warned_share. The switch is sticky. Because it depends only on event timestamps, a restart flips at the same H
  (test `ScarcityTest`, rebuilds at 2350/3300/4300/6000). Logs one `SCARCE` line.
- Once scarce: no safe_admit; risk_frac x `scarcity_risk`; `scarcity_long`>0 declines cars with drive >= it
  (`DECLINE scarce long`); `scarce_set=((name, value), ...)` swaps desk.cfg for cfg.with_(...) via `switch_cfg()`. The market's
  cfg follows, and so does the cached strict config. `desk.scarce` is the flag FLEET reads.

## Presets
v5q1 = v5a + safe_admit=(0.97,0.95,0.12) | v5q2 = v5q1 + scarcity=(1.08,0.06), scarcity_long=240, scarcity_risk=1.5 |
v5q3 = v5q2 + safe_admit_fri | v5q2V = k-f1h5fV2 + long_warn_distinct + SCARCITY + scarce_set back to (0.07, 1.0, 1.0) |
v5q2f = v5q1 + scarcity=(1.08, 9.0) (the fee signal only), scarcity_until=3600, risk 1.5, no long declines.

## Offline switch check (scarce_check.py, scarce_series.py, scarce_sweep.py; holdouts excluded)
The exact rule was recomputed hour by hour from the reveals. "bad" is PROBE's label (whole-week fee/typ >= 1.10 or warned/won >= 0.15).

| rule, fee1 family (773 weeks) | fires: bad / normal / on-time < .93 / >= .93 |
|---|---|
| spec (1.08 or 0.06), Tue24 only | 65% / 28% / 43% / 32% |
| spec, to Wed 12h | 90% / 49% / 78% / 51% |
| spec, to Thu 00h | 100% / 70% / 96% / 72% |
| fee >= 1.08 only, to Wed 12h (v5q2f) | 72% / 20% / 48% / 24% |
| fee >= 1.10 or w >= 0.10, to Thu 00h | 86% / 43% / 78% / 45% |

In the k-safe family (516 weeks) the spec rule fires on 96% of bad weeks vs 65% of normal ones. The rule as specified is not
selective: warned/won >= 0.06 over a rolling 24 h is crossed on Wednesday in most normal weeks. So v5q2 is close to
"v5q1 with admits off from Wednesday", and with long declines too, which SWITCH.md priced at -1.7k to -2.6k per week.

LEAD seeds (first flip by Thu 00, release runs sc-f1h5f / V2 runs sc-V2 / v5a):
fresh-12 Wed 09h (warn 9/133) / Wed 09h / Wed 10h | fresh-20 Wed 11h (warn 8/103) / Wed 11h / Wed 10h |
fresh-07 Tue24 (fee 1.13) / Tue24 / Tue24 | fresh-10 none (Thu 08h) / Wed 16h (warn 6/94) / none (Thu 12h) |
fresh-11 Wed 07h / Wed 07h / none | fresh-14 none (Thu 12h) in all fee1 runs | fresh-15 Tue24 (warn 6/87) / Tue24 / Wed 10h.
FLEET scV2m: fresh-10 none (Thu 13h), fresh-20 Wed 11h. v5aV2: fresh-10 Wed 16h, fresh-20 Wed 08h.
On fresh-10 under fee1, Tuesday's fee/typ is 0.95-0.97 and only 1 order is warned. The rule cannot see that week before Wednesday afternoon.
