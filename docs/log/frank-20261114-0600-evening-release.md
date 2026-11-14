# Evening release: hold next-day cars, pair them at release

**What we saw.** Every car was posted the minute it was won. Single gigs book in a median 4 min, so `try_bundle` (partners posted in the last 2 h, still unbooked) found almost nothing: ~28 cars/week rode in bundles on rc2. Offline, on rc2's own wins, holding next-day cars until 18:00 the day before pickup allows ~110 chain links/week (165 cars). Bundles cost 0.86× the summed typical fee vs 1.20× for singles, and went late 1.2% vs 4.0% (`../research/scripts/pairs_policy.py`, `bundlecost.py`).

**The idea.** A car whose first pickup is on a later day waits in a held pool until `hold_hour` on the day before its pickup day. At each release, a greedy matching (shortest transfer first) pairs released cars with each other, with held cars for the same day, and with our open unbooked singles. Pairs post as one gig at `bundle_mult` × (refA + refB), using the existing `chain()` check (12 h limit, both deadlines with margin, 6 h of slack). Unpaired cars post as before. Flags: `hold`, `hold_hour`, `hold_all`, `hold_open`, `hold_km`, `hold_price`.

**The test.** Paired sweeps on dev-07..18 (level 8), then a fresh check on unused seeds.

**Numbers.** (filled in below)

**Keep or kill.** (below)
