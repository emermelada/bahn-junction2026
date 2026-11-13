# v1 iterations, Fri night (level 8, seeds dev-01..06)

Each row is the same seeds, same code except the change. Margin is € per week; on-time is the worst week.

| Tag | Change | Seeds | Ranked | Min on-time | Mean margin |
|---|---|---|---|---|---|
| v1a | on-time model picks options, EV price on live competitor curve, fees 0.95→1.85 over the slack | 1–3 | 2/3 | 0.861 | 3,301 |
| v1b | + no offers on warnings, escalation capped at 2.6x | 1–3 | 1/3 | 0.869 | 6,764 |
| v1c | + fee steps anchored to lastPickupAt, cheap plan for already-late cars, escalation picked by governor | 1–6 | 5/6 | 0.894 | 6,696 |
| v1d | v1c + offers to gig viewers + live calibration | 1–3 | 1/3 | 0.840 | 5,561 |
| v1e | v1c + own alarm (note deadlines) + gate bonus | 1–6 | 4/6 | 0.858 | 6,671 |

**What we saw.**
- v1a: fees were 85% of revenue. 50% of orders book at the opening fee (+€42 each); the 22% that end above 1.9x typical lose €26–148 each.
- Direct offers almost never land: 2 of ~560 on warnings (v1a), 93 of 9,171 to viewers (v1d). Most expire unread. Killed.
- 83% of late orders were never booked in time. Those gigs had a median of 95 viewers (on-time ones: 9): drivers saw them and waited. Lateness is ~7.5% and spread evenly over lanes, supply and hours, so it follows load against driver capacity rather than any static feature.
- A week can have one bad day (dev-01, Wednesday: drops and no bookings, probably the flu); the cars due that day go late together.

**Keep / kill.** Keep v1c as the base. Kill offers. Gate bonus and live calibration: no gain on these seeds, off.
