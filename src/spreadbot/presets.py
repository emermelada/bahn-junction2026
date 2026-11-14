"""Named sets of overrides on Config. Config defaults are y4 (evening release). `--preset chains` is k18."""
PRESETS = {
    # y4 = Config defaults (rc3): evening release at 16:00, late_cost_frac 2.0, load_free 0.07.
    # dev-31..35: 12,602/week, on-time 0.939-0.984, 5/5 ranked; dev-07..18: 11,579, 12/12.
    "y4": [],
    # m12 on dev-07..18: mean 11,462 vs 9,661 for rc2 (+19%), ranked 8/12, on-time 0.884-0.937.
    "money": [
        "hold=false", "late_cost_frac=0.6",              # the pre-rc3 defaults it was measured with
        "gov_tight=0", "gov_rescue=0", "gov_relaxed=0",  # no on-time governor: the bar and escalation ignore the gate
        "theta=0.7",                                      # take cars down to P(on time) 0.7
        "lane_w=1.0",                                     # competitor lane factor from 443 weeks (Javier's lanes.json)
        "steep_relaxed=(1.2,1.4)",                        # pay little to rescue a car: a late refund is 10-25%
        "load_free=0.07",                                 # more cars per day; money peaks at 0.06-0.07
    ],
    # k18 (branch-v1-frank): money settings with an on-time guard at 92%, plus the hold-and-pair chain planner.
    # Gated mean (weeks under 90% count 0): 11,268 on dev-07..18 and 11,534 on dev-19..30, ranked 24/24, min on-time 0.907.
    "chains": [
        "hold=false", "late_cost_frac=0.6",              # k18 ran on the pre-rc3 defaults: no evening release, late cost 0.6
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",  # governor only near the gate: dilution bar and steep fees under 92%
        "theta=0.7", "lane_w=1.0", "steep_relaxed=(1.2,1.4)", "load_free=0.07",
        "hold_minutes=480", "hold_lead=900",              # hold a won car up to 8 h (posted 15 h before pickup) to find a chain partner
        "unbundle_minutes=480",                           # an unbooked chain splits 8 h before its last start
        "bundle_max_drive=300", "bundle_min_lead=360",    # chains under 5 h of driving, formed 6 h ahead: 85% booked
    ],
}
PRESETS["best"] = PRESETS["y4"]  # the current best version; replaced when a combination beats y4 and k18
