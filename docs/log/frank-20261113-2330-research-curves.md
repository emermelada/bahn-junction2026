# Research week: dealer curve, flat-fee driver curve, what makes a car late

**What we saw.** The kit starter at level 8 (seed spread-1) loses €72.6k: it raises fees 10%/h up to 1.5x, and most bookings sit exactly at 1.5x the typical fee, so drivers learned to wait for the top step. List price is only ~1.11x the typical fee (median), so at 1.5x every car loses money.

**The test.** 3 level 8 weeks (`exp-01..03`, flag `experiment_quote` + `experiment_fee`): each request quoted at a random ratio 1.0–1.8 x list (first option); each won car posted at a flat fee drawn from {0.9, 1.1, 1.3, 1.5, 1.8, 2.2} x typical fee, no raises until the deadline warning. Scripts: `lab/frank/curves.py`, `flat.py`, `hard.py`.

**Numbers.**
- Dealer (3,101 quotes, trust removed): win 0.87 at 1.00x list, 0.74 at 1.10, 0.57 at 1.20–1.25, 0.45 at 1.30, 0.30 at 1.35–1.40, 0.19 at 1.45–1.50, 0.06 at 1.60. Logistic: mu ≈ 1.28, slope ≈ 6.7. Day-to-day swings are large (one week: Thu win 0.02 at 1.2–1.5 = price war).
- Driver, flat fee, booked before the deadline warning: 0.9x 64%, 1.1x 65%, 1.3x 79%, 1.5x 77%, 1.8x 81%, 2.2x 86%. Median wait to booking 3–8 minutes when it books at all. Above ~1.3x, fee hardly matters: ~20% of cars are hard at any fee.
- What makes a car late (logistic, 1,403 orders, CV AUC 0.78): slack = deadline − max(now, ready) − drive (+0.31/h up to 12 h; <4 h slack ≈ 50% on time, 8–12 h ≈ 93%), overnight work (−1.18), premium/experienced-only (−1.19), Friday (−0.57), long drives (−0.42 per log-minute), a note (−0.38), car ready later (+0.88). Keeping only p ≥ 0.85 kept ~48% of cars at 89–93% on time on a held-out week.

**Keep / kill.** Keep: flat-ish fees that do not teach waiting; an on-time model to choose which options to quote; EV pricing on a live-learned competitor curve. Kill: the starter's rising 10%/h ladder.
