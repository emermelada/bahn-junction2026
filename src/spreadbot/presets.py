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
    # c1 (Sat 14 Nov): y4 (evening release 16:00, late_cost_frac 2.0, load_free 0.07, the defaults) plus the money
    # settings of k18 with its guard at 92%. Candidate under the team's decision to maximise raw margin and accept
    # gate risk. dev-07..18, 6 of 12 weeks (rest lost to a DNS outage): 13,088 vs 12,572 for y4, 6/6 ranked, min on-time 0.943.
    "c1": [
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",  # governor only near the gate
        "theta=0.7",                                      # take cars down to P(on time) 0.7
        "lane_w=1.0",                                     # competitor lane factor from 443 weeks
        "steep_relaxed=(1.2,1.4)",                        # cheap rescue escalation
    ],
    # c3 (Sat 14 Nov): c1 with late_cost_frac 1.2. dev-07..18: 12,927 vs 12,365 for c1 and 11,579 for y4, 12/12 ranked,
    # min on-time 0.912, best p10 (9,756). Candidate under the raw-margin decision.
    "c3": [
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",
        "theta=0.7", "lane_w=1.0", "steep_relaxed=(1.2,1.4)",
        "late_cost_frac=1.2",                             # milder lateness price: more cars won, still ranked on 12/12
    ],
}
