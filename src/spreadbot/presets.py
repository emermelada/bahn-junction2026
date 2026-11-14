"""Named sets of overrides on Config. `--preset money` maximises margin and accepts weeks under the 90% gate."""
PRESETS = {
    # m12 on dev-07..18: mean 11,462 vs 9,661 for rc2 (+19%), ranked 8/12, on-time 0.884-0.937.
    "money": [
        "gov_tight=0", "gov_rescue=0", "gov_relaxed=0",  # no on-time governor: the bar and escalation ignore the gate
        "theta=0.7",                                      # take cars down to P(on time) 0.7
        "lane_w=1.0",                                     # competitor lane factor from 443 weeks (Javier's lanes.json)
        "steep_relaxed=(1.2,1.4)",                        # pay little to rescue a car: a late refund is 10-25%
        "load_free=0.07",                                 # more cars per day; money peaks at 0.06-0.07
    ],
    # k18: money settings with an on-time guard at 92%, plus the hold-and-pair chain planner.
    # Gated mean (weeks under 90% count 0): 11,268 on dev-07..18 and 11,534 on dev-19..30, ranked 24/24, min on-time 0.907.
    "chains": [
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",  # governor only near the gate: dilution bar and steep fees under 92%
        "theta=0.7", "lane_w=1.0", "steep_relaxed=(1.2,1.4)", "load_free=0.07",
        "hold_minutes=480", "hold_lead=900",              # hold a won car up to 8 h (posted 15 h before pickup) to find a chain partner
        "unbundle_minutes=480",                           # an unbooked chain splits 8 h before its last start
        "bundle_max_drive=300", "bundle_min_lead=360",    # chains under 5 h of driving, formed 6 h ahead: 85% booked
    ],
    # chains_plus: k18 plus a cap of 6 orders per batchId (a yard sending many cars at once).
    # On Javier's fresh rc10 (12 weeks): mean 11,041 vs 10,791, ranked 12/12 vs 12/12, min on-time 0.918 vs 0.901,
    # 2nd/3rd worst weeks 8,262/8,514 vs 7,824/8,262. See bahn-junction2026 docs/frank-plus-plan.md.
    "chains_plus": [
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",
        "theta=0.7", "lane_w=1.0", "steep_relaxed=(1.2,1.4)", "load_free=0.07",
        "hold_minutes=480", "hold_lead=900", "unbundle_minutes=480",
        "bundle_max_drive=300", "bundle_min_lead=360",
        "max_per_batch=6",                                # at most 6 orders from one batch: bulk yards made weeks late
    ],
}
