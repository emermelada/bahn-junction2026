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
# Candidates (claude/re-drivers), research/re/drivers/NOTES.md. d-fee: PASSES dev-07..18 +369, dev-43..54 +429, WAR +708 vs c3g.
PRESETS["d-fee"] = PRESETS["c3g"] + ["fee_open_rule=((24,0,0.92),(12,80,0.95))"]  # opening fee by slack and drivers near the delivery
PRESETS["d-fee2"] = PRESETS["c3g"] + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92))"]  # deeper: drivers near the delivery skip the dear trip home
PRESETS["d-feer"] = PRESETS["d-fee"] + ["relook_minutes=90", "relook_mult=1.05"]  # a low opening unbooked after 90 min goes back to 1.05 now
# d-fee's low openings where < 40 drivers live near the delivery doubled the warned share (3.2% -> 6.7%) for 7% less fee; >= 40: flat, -11%.
PRESETS["d-fee3"] = PRESETS["c3g"] + ["fee_open_rule=((24,40,0.92),(12,80,0.95))"]
PRESETS["d-pair"] = PRESETS["c3g"] + ["bundle_empty_end=(240,11)"]  # no long pairs ending where nobody lives
# killed: hold_min_left=1440 (-434), offer_home_n=3 (-220, 1.5% of offers accepted)
PRESETS["d-pfee"] = PRESETS["c3g"] + ["bundle_open_dense=(12,80,0.76)"]  # cheaper pairs that end where many drivers live
PRESETS["d-fee4"] = PRESETS["c3g"] + ["fee_open_rule=((24,0,0.92),(12,0,0.95))"]  # d-fee3 (cut only near drivers) gave +65: cut wider instead
# re-market: menu pricing (one effective price, slower options cheaper by the dealer's speed value, every option at one margin).
PRESETS["m1menu"] = PRESETS["c3g"] + ["menu=true"]
# re-market: no load charge on cars due the last Monday (Friday noev is the load charge; Mon2 cars are our safest).
PRESETS["m2mon2"] = PRESETS["c3g"] + ["load_free_mon2=0.2"]
# re-market: same_day capped at next_day + €9 (the dealer's speed value), and pricing with damped mu parts.
PRESETS["m3scap"] = PRESETS["c3g"] + ["s_cap_cents=900"]
PRESETS["m4muw"] = PRESETS["c3g"] + ["mu_w=(0.65,0.4,0.6)"]
# re-capacity: load charge as a barrier at the measured knee (fee/typical flat 1.11-1.12 up to day load 0.12, then 1.16/1.24;
# late 5% -> 12%; research/re/feeload.py). dev-07..18 +944 (se 246) 11/12 vs c3g, min on-time 0.929.
PRESETS["k-load"] = PRESETS["c3g"] + ["load_free=0.12", "load_slope=2"]
# Stacks: + re-drivers' opening-fee rule (d-fee), + re-market's last-Monday load room (m2mon2 at a gentler 0.15).
PRESETS["k-s1"] = PRESETS["k-load"] + ["fee_open_rule=((24,0,0.92),(12,80,0.95))"]
PRESETS["k-s2"] = PRESETS["k-s1"] + ["load_free_mon2=0.15"]
# k-s1 with the governor tightened by its measured error: projection at the last win is up to +0.021 above the final share
# (research/re/projerr.py, 69 high-volume weeks), so the bar tightens under 0.945 to keep the worst week >= 0.93.
PRESETS["k-s1g"] = PRESETS["k-s1"] + ["gov_tight=0.945", "gov_rescue=0.93", "gov_relaxed=0.95"]
# k-s3: the safer stack. load_slope 0.5 (34/34 ranked, worst 0.929) + re-drivers' d-feer (opening rule + 90-min look back to 1.05,
# worst 0.936-0.947) + re-market's last-Monday room at 0.15 (Mon2 late 1-3% up to load 0.12, 5-6% at 0.14-0.16; dev-43..50 +1,271, 8/8).
PRESETS["k-s3"] = PRESETS["c3g"] + ["load_slope=0.5", "fee_open_rule=((24,0,0.92),(12,80,0.95))", "relook_minutes=90", "relook_mult=1.05",
                                    "load_free_mon2=0.15"]
# Tail-risk guard: under 0.94 projected on time, a car with P(on time) >= 0.95 is worth up to EUR 40 more (full at 0.92): it dilutes
# the late ones. c3g is unranked on 2/20 fresh weeks; the governor's late tightening (k-s1g) cannot undo cars already won.
GATE = ["gate_bonus_cents=4000", "gate_target=0.94", "gate_span=0.02", "gate_safe_p=0.95"]
PRESETS["k-s1d"] = PRESETS["k-s1"] + GATE
PRESETS["k-s3d"] = PRESETS["k-s3"] + GATE
PRESETS["c3gd"] = PRESETS["c3g"] + GATE
# Stronger guard: the projection is up to +0.02..0.03 optimistic (projerr.py), so start diluting under 0.955, full bonus at 0.925.
PRESETS["k-s3e"] = PRESETS["k-s3"] + ["gate_bonus_cents=4000", "gate_target=0.955", "gate_span=0.03", "gate_safe_p=0.95"]
# k-s3 + full load charge for cars delivering where <= 10 drivers live within 60 road min (re-drivers' DEV46.md: the stacks starve
# the cars c3g also won by adding long drives into such towns).
PRESETS["k-s3x"] = PRESETS["k-s3"] + ["load_desert_n=10"]
# k-s3d with the bonus only on deadline days under load 0.12 (the knee), so dilution does not overload a day.
PRESETS["k-s3dl"] = PRESETS["k-s3d"] + ["gate_load_max=0.12"]
PRESETS["k-s3xdl"] = PRESETS["k-s3x"] + GATE + ["gate_load_max=0.12"]
# k-s3dl with a hard cap on any deadline day's load: the stacks push days to 0.20-0.23 where piles go late.
PRESETS["k-s3c15"] = PRESETS["k-s3dl"] + ["load_cap=0.15"]
PRESETS["k-s3c17"] = PRESETS["k-s3dl"] + ["load_cap=0.17"]
# d-fee2's 0.85 where >= 80 drivers live near the delivery: 1 warned of ~60 such gigs; its 0.9 elsewhere drove dev-46 to 0.917.
PRESETS["d-fee5"] = PRESETS["c3g"] + ["fee_open_rule=((24,80,0.85),(24,0,0.92),(12,80,0.95))"]
PRESETS["d-fee2r"] = PRESETS["d-fee2"] + ["relook_minutes=90", "relook_mult=1.05"]  # deeper openings with d-feer's guard
# Desert delivery towns (DEV46.md): no fee cut and an alarm 12 h before the last pickup for cars to towns with <= 10 drivers within 60 min.
PRESETS["d-feerd"] = PRESETS["d-feer"] + ["desert_n=11", "desert_alarm=720"]
PRESETS["d-fee2d"] = PRESETS["d-fee2"] + ["desert_n=11", "desert_alarm=720"]
# Safe low openings (SAFE_OPEN.md): cut only where warned and waited-to-1.25 stayed at c3g; 1.05 where <= 40 drivers live near the delivery.
PRESETS["d-safe"] = PRESETS["c3g"] + ["fee_open_day=((0,3,81,24,0.85),(0,6,41,24,0.92),(0,1,81,12,0.95))",
                                      "relook_minutes=90", "relook_mult=1.05"]
# Cuts in sparse towns pay (d-fee3 +65, d-safe +149/+248 vs d-feer +309/+344): widen d-feer's 12-24 h step to every town.
PRESETS["d-feer4"] = PRESETS["c3g"] + ["fee_open_rule=((24,0,0.92),(12,0,0.95))", "relook_minutes=90", "relook_mult=1.05"]
# Every team above us opens at 0.80-0.92 (Halal flat avg 0.93, alignas 0.90, RoutePulse 0.85-0.89 floor 0.74, umarbek 0.80; TOP_TEAMS.md).
PRESETS["d-low"] = PRESETS["c3g"] + ["fee_open_rule=((24,80,0.80),(12,0,0.88))", "desert_n=11", "desert_alarm=720"]
# ... and with no scheduled raises (drivers wait for raises they have seen; Halal: one flat fee per gig): only the own alarm escalates.
PRESETS["d-flat"] = PRESETS["d-low"] + ["fee_rel=()"]
# Stack + re-drivers' desert rule (no fee cut, alarm 12 h before the last pickup, for cars to towns with <= 10 drivers within 60 min)
# + my load_desert_n (full load charge there): both from DEV46.md.
DESERT = ["desert_n=11", "desert_alarm=720", "load_desert_n=10"]
PRESETS["k-s3dlx"] = PRESETS["k-s3dl"] + DESERT
PRESETS["k-s3c15x"] = PRESETS["k-s3c15"] + DESERT
PRESETS["k-s3c17x"] = PRESETS["k-s3c17"] + DESERT
# re-market: Mon2 cars free of the load charge only when the drive is under 4 h (long Mon2 gigs wait for Monday and go late).
PRESETS["m8mon2s"] = PRESETS["c3g"] + ["load_free_mon2=0.2", "mon2_max_drive=240"]
# re-market: a car won < 6 h before its last pickup with >= 4 h of driving paid 1.26x the fee the quote assumed (1.00-1.10 for every
# other lead x drive); quote its fee x1.25. 34 c3g weeks replayed: -1.9 orders, -0.32 late, -0.8 warned, +10 EUR/week (SHORT_NOTICE.md).
PRESETS["m7short"] = PRESETS["c3g"] + ["short_fee=(6,240,1.25)"]
# re-market: the lateness trees fed the site-hours last pickup they were trained on.
PRESETS["m9lead"] = PRESETS["c3g"] + ["gbm_site_lead=true"]
# Stack with re-market's narrower last-Monday room: 0.2 only for drives under 4 h (long Mon2 gigs wait ~77 h, 29-44% late; MON2_LATE.md).
MON2S = ["load_free_mon2=0.2", "mon2_max_drive=240"]
PRESETS["k-s5"] = PRESETS["k-s3dlx"] + MON2S
PRESETS["k-s5c17"] = PRESETS["k-s5"] + ["load_cap=0.17"]
PRESETS["k-s5c15"] = PRESETS["k-s5"] + ["load_cap=0.15"]
# The conservative stack: only changes whose worst week stayed near c3g's on all three tuning sets.
# re-market m8mon2s (Mon2 room for drives < 4 h: +594/+834/+519, 34/34, worst 0.944-0.948) + re-drivers d-feerd (worst 0.938-0.941).
PRESETS["k-safe"] = PRESETS["c3g"] + MON2S + ["fee_open_rule=((24,0,0.92),(12,80,0.95))", "relook_minutes=90", "relook_mult=1.05",
                                              "desert_n=11", "desert_alarm=720"]
# re-drivers arms on the new bar k-safe: its fee part swapped for d-fee2d's deeper openings (d-fee2d vs c3g +732/+710).
KSAFE_BASE = PRESETS["c3g"] + MON2S + ["desert_n=11", "desert_alarm=720"]
PRESETS["k-safe-f2"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92))"]
PRESETS["k-safe-pf"] = PRESETS["k-safe"] + ["bundle_open_dense=(12,80,0.76)"]  # + cheaper pairs that end where many drivers live
# k-safe-f2 cost dev-46 0.942 -> 0.924; keep only the dense-town deep cut (0.85 where >= 80 drivers live near the delivery) on k-safe.
PRESETS["k-safe-f5"] = PRESETS["k-safe"] + ["fee_open_rule=((24,80,0.85),(24,0,0.92),(12,80,0.95))"]
# Pairs: k-safe pays 0.85x for paired cars (31% of cars); bahn67 0.76x (49-58% paired), Halal 0.70x for two new cars (GITHUB_LEADS.md 6-7).
PRESETS["k-safe-pm"] = PRESETS["k-safe"] + ["bundle_mult=0.72"]  # pair opening 0.72 x 1.05 = 0.76 of the two typical fees
# Fee push (board 15:00: EUR 35.4/order vs leaders 44.9; the gap is the fee): deep openings + cheap pairs; and one more opening step at 12 h everywhere.
PRESETS["k-safe-f2pm"] = PRESETS["k-safe-f2"] + ["bundle_mult=0.72"]
PRESETS["k-safe-f6"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92),(12,0,0.95))"]
# k-safe bill: singles posted 12-24 h before the last pickup (held cars released at 16:00) open at 1.05 and book in a median 3 min.
PRESETS["k-safe-f7"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(12,0,0.9),(6,80,0.95))"]
