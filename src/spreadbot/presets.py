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
}
