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
    # c1 (Sat 14 Nov, from claude/evening-release 87e14e4): y4 (evening release 16:00, late_cost_frac 2.0, load_free 0.07,
    # the defaults) plus the money settings of k18 with its guard at 92%. Candidate under the team's decision to maximise
    # raw margin and accept gate risk. dev-07..18, 6 of 12 weeks: 13,088 vs 12,572 for y4, 6/6 ranked, min on-time 0.943.
    "c1": [
        "gov_tight=0.92", "gov_rescue=0.92", "gov_relaxed=0.93",  # governor only near the gate
        "theta=0.7",                                      # take cars down to P(on time) 0.7
        "lane_w=1.0",                                     # competitor lane factor from 443 weeks
        "steep_relaxed=(1.2,1.4)",                        # cheap rescue escalation
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
# c3 (from claude/evening-release 3aee9bd): c1 with late_cost_frac 1.2. dev-07..18: 12,927 vs 12,365 for c1 and 11,579 for y4,
# 12/12 ranked, min on-time 0.912, best p10 (9,756). Fresh dev-43 (hard week): on-time 0.873, unranked (c1 0.892, y4 0.909).
PRESETS["c3"] = PRESETS["c1"] + ["late_cost_frac=1.2"]  # milder lateness price: more cars won
# Candidate (franc-08 builder, not accepted): today's competitor level as normal-day / war-day Kalman hypotheses.
PRESETS["c3k"] = PRESETS["c3"] + ["day_kalman=true"]
# chains_plus (Javier, origin/a/frank-plus 629708e): k18 + decline once we hold 6 orders from one batch (bulk-yard bursts).
# rc10-01..12: mean 11,041 vs 10,791 for k18, 12/12 ranked, min on-time 0.918 vs 0.901.
PRESETS["chains_plus"] = PRESETS["chains"] + ["max_per_batch=6"]
PRESETS["c1_plus"] = PRESETS["c1"] + ["max_per_batch=6"]
PRESETS["best"] = PRESETS["c1"]  # the current best version (team objective: raw mean margin); replaced when a combination beats it
# Candidates (claude/main-relook, not accepted), from Halal's ablation (research/TOP_TEAMS.md §2, §5.1):
# board pairs = a new car may pair with one of our singles sitting unbooked >= bundle_window, at 0.85x, split back after 60 min;
# second look = a single unbooked for 6 h gets one raise to 1.2x now.
PRESETS["c3bp"] = PRESETS["c3"] + ["repair_pairs=true", "repair_lead=180", "repair_mult=0.85", "repair_split=60"]
PRESETS["c3rl"] = PRESETS["c3"] + ["relook_minutes=360"]
PRESETS["c3bprl"] = PRESETS["c3bp"] + ["relook_minutes=360"]
# The lateness model from all our weeks (late_gbm.py, AUC 0.897 vs 0.737) in place of the logistic: the main line since Sat 14 Nov.
PRESETS["c3g"] = PRESETS["c3"] + ["ontime_model=gbm"]
# Candidates (claude/re-drivers): post next-day cars with an early last pickup at once; opening fee by slack and drivers near the delivery.
PRESETS["c3gh"] = PRESETS["c3g"] + ["hold_min_left=1440"]
PRESETS["c3gf"] = PRESETS["c3g"] + ["fee_open_rule=((24,0,0.92),(12,80,0.95))"]
PRESETS["c3gf2"] = PRESETS["c3g"] + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92))"]  # deeper: drivers near the delivery skip the dear trip home
