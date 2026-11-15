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
# Flu nights (>= 8 drops 00-01h): cars due that day priced and projected at 1.9x P(late).
FLU = ["flu_drops=8", "flu_mult=1.9"]
PRESETS["k-safef"] = PRESETS["k-safe"] + FLU
PRESETS["k-s5f"] = PRESETS["k-s5"] + FLU
PRESETS["c3gf8"] = PRESETS["c3g"] + FLU
# re-drivers arms on the new bar k-safe: its fee part swapped for d-fee2d's deeper openings (d-fee2d vs c3g +732/+710).
KSAFE_BASE = PRESETS["c3g"] + MON2S + ["desert_n=11", "desert_alarm=720"]
PRESETS["k-safe-f2"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92))"]
PRESETS["k-safe-pf"] = PRESETS["k-safe"] + ["bundle_open_dense=(12,80,0.76)"]  # + cheaper pairs that end where many drivers live
# k-safe-f2 cost dev-46 0.942 -> 0.924; keep only the dense-town deep cut (0.85 where >= 80 drivers live near the delivery) on k-safe.
PRESETS["k-safe-f5"] = PRESETS["k-safe"] + ["fee_open_rule=((24,80,0.85),(24,0,0.92),(12,80,0.95))"]
# Pairs: k-safe pays 0.85x for paired cars (31% of cars); bahn67 0.76x (49-58% paired), Halal 0.70x for two new cars (GITHUB_LEADS.md 6-7).
PRESETS["k-safe-pm"] = PRESETS["k-safe"] + ["bundle_mult=0.72"]  # pair opening 0.72 x 1.05 = 0.76 of the two typical fees
# re-market: the outage detector (pickup region, 08-18, flagged at log-likelihood 4.5 of +30%, priced +30%), on the k-safe bar.
PRESETS["m11out"] = PRESETS["k-safe"] + ["outage_z=4.5", "outage_up=0.3"]
# re-market: the weekly change of shape of the competitor's price list, as a slope on ln(km), on the k-safe bar.
PRESETS["m12dist"] = PRESETS["k-safe"] + ["dist_lr=0.002"]
# re-market: quote the fee rule's cheaper opening as the cost (wins the cars drivers near the delivery take cheaply), on k-safe.
PRESETS["m13mc"] = PRESETS["k-safe"] + ["quote_move_cost=true"]

# Drops with time to spare: post again at the opening fee instead of escalating (claude/spec-drops).
PRESETS["k-safe-dc"] = PRESETS["k-safe"] + ["drop_calm_hours=16"]
# k-safe-dc + repost an unbooked gig 1 min after its last pickup, so a driver can book the late car at once (Burger Han).
PRESETS["k-safe-dcr"] = PRESETS["k-safe-dc"] + ["repost_past_last=1"]
# + decline long (>= 4 h) cars while >= 3 of our long cars were warned in the last 24 h (H2 autopsy rule 1).
PRESETS["k-safe-dcl"] = PRESETS["k-safe-dc"] + ["long_warn=(240,3,1440)"]
PRESETS["k-safe-dcrl"] = PRESETS["k-safe-dcr"] + ["long_warn=(240,3,1440)"]
# Fee push (board 15:00: EUR 35.4/order vs leaders 44.9; the gap is the fee): deep openings + cheap pairs; and one more opening step at 12 h everywhere.
PRESETS["k-safe-f2pm"] = PRESETS["k-safe-f2"] + ["bundle_mult=0.72"]
PRESETS["k-safe-f6"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(24,0,0.9),(12,80,0.92),(12,0,0.95))"]
# k-safe bill: singles posted 12-24 h before the last pickup (held cars released at 16:00) open at 1.05 and book in a median 3 min.
PRESETS["k-safe-f7"] = KSAFE_BASE + ["fee_open_rule=((24,80,0.85),(12,0,0.9),(6,80,0.95))"]
# Deep openings with a safety net: cut only for cars with P(on time) >= 0.97, while the projection is >= 0.955 and the week's booked/first fee <= 1.12.
PRESETS["k-safe-f2g"] = PRESETS["k-safe-f2"] + ["fee_cut_guard=(0.97,0.955,1.12)"]
# Pair share (k-safe 31% of cars paired at 0.85x vs leaders 49-58% at ~0.76x; ~EUR 23 saved per car moved; GITHUB_LEADS.md 6-8):
PRESETS["k-safe-bp"] = PRESETS["k-safe"] + ["repair_pairs=true", "repair_lead=180", "repair_mult=0.85", "repair_split=60"]  # board pairs (Halal +1.9k)
PRESETS["k-safe-hold"] = PRESETS["k-safe"] + ["hold_minutes=60"]  # a new car waits up to 60 min for a partner (Halal +829/wk at 60 min)
PRESETS["k-safe-km50"] = PRESETS["k-safe"] + ["bundle_km=50"]  # pair links up to 50 km (bahn67 +2.4% on one set)
PRESETS["k-safe-kd"] = PRESETS["k-safe"] + ["bundle_keep_drop=true"]  # a dropped pair with time left stays a pair (re-external: split pairs 5-13% late; kept 78% rebooked at 0.86x)
PRESETS["k-safe-ls"] = PRESETS["k-safe"] + ["long_split=(360,180)"]  # long pairs unbooked 3 h after posting go out as singles
PRESETS["k-safe-b3"] = PRESETS["k-safe"] + ["bundle3=true", "bundle3_mult=0.75"]  # three-car chains (bahn67 +370/wk; never run on c3g)
# PAIRS_MISSED.md: 66% of missed pairs = the partner was already booked (lone cars book in minutes); est. km50 + 120-min hold +472-583/wk.
PRESETS["k-safe-kmh"] = PRESETS["k-safe"] + ["bundle_km=50", "hold_minutes=120", "hold_lead=360"]
# k-safe-dc + re-drivers' long_split: a pair with >= 6 h of driving still unbooked 3 h after posting goes out as singles
# (long pairs carry 4.4 of 20.5 warned singles a week; k-safe-ls vs k-safe: +540/+220, worst 0.960/0.948 vs 0.942).
PRESETS["k-safe-dcls"] = PRESETS["k-safe-dc"] + ["long_split=(360,180)"]
# FLEET v4: one fee per single gig chosen by a booking model (fee1.py + book_gbm.py) instead of the opening + raises + relook;
# re-pick as a new post after 6 h; the alarm's steep rescue kept. Target: lone cars 1.08x -> <= 0.97x typical at the same on-time.
PRESETS["k-f1"] = PRESETS["k-safe-dcl"] + ["fee1=true"]
# MARKET: the quote cost level held at k-safe-dcl's mean cost_mult (1.05), so fee1's savings stay margin instead of lowering our
# prices on the same cars (the load charge binds: quoting at a 5% lower cost was -396/wk at equal orders, m25-fma).
PRESETS["kdcl-hold"] = PRESETS["k-safe-dcl"] + ["quote_cost_hold=1.05"]
PRESETS["k-f1h"] = PRESETS["k-f1"] + ["quote_cost_hold=1.05"]
# fee1 v5 on the stack: long cars (>= 4 h drive, long_warn's class) never under 1.0; a last-call new post 150 min before the alarm;
# relative weight 0.05 (PROBE's causal forks, research/re/probe/relstat.py).
PRESETS["k-f1h5"] = PRESETS["k-f1h"] + ["fee1_long=(240,1.0)", "fee1_last_call=150", "fee1_rel_share=0.05"]
PRESETS["k-f1h5f"] = PRESETS["k-f1h5"] + ["quote_cost_floor=true"]  # MARKET: quote cost = max(1.05, cost_mult): fee1 savings only stop the fall below 1.05
# long_warn on distinct cars (ARCHIVE D_LONGWARN.md: the guard counted warning events; one re-planned car warned 5x set off 85 declines).
PRESETS["k-f1h5fD"] = PRESETS["k-f1h5f"] + ["long_warn_distinct=true"]
PRESETS["k-safe-dclD"] = PRESETS["k-safe-dcl"] + ["long_warn_distinct=true"]
# V5 (franc-5c, research/prompts/teamv4/6-V5.md): bold fee-first version on the release k-f1h5f. Each arm below is one step.
# V5a: long cars (>= 4 h drive) may go down to 0.90 under fee1 (they paid 1.00-1.05x at 24 h+ leads: EUR ~900/wk above 0.90x,
# research/re/v5/lead_open_f1h5f.out); the guard counts warned cars, not warning events (ARCHIVE D_LONGWARN.md).
PRESETS["v5a"] = PRESETS["k-f1h5f"] + ["long_warn_distinct=true", "fee1_long=(240,0.9)"]
# V5r: the rescue fee capped near Halal's (urgent <= 1.6x, measured: 2x rescue bought +0.1 pt for -EUR 740). Every collapse week is a
# governor spiral at steep_rescue 2.0-4.0x (escalation EUR 5.9-12k vs ~750 normal; research/re/archive/R1_BADWEEKS.md point 1).
PRESETS["v5r"] = PRESETS["k-f1h5fD"] + ["steep_plan=(1.5,1.7,1.9)", "steep_rescue=(1.6,1.8,2.0)"]
# V5 + FLEET's volume arm V2 (pairs count 0.6 in the day's load; load barrier at the knee 0.12, slope 2): +779 WAR on the release, but
# fresh-10/20 0.891/0.893 (LEAD sc-V2). The scarcity switch (claude/v5-quote) is meant to turn it off in such weeks.
PRESETS["v5aV2"] = PRESETS["v5a"] + ["load_bundle_w=0.6", "load_free=0.12", "load_slope=2"]
# V5 quote (research/re/v5/QUOTE_BUILD.md). v5q1: a car declined for no margin (noev) gets a second look at the true fleet cost
# (0.95x typical, or fee1's own estimate if lower) when P(on time) >= 0.97, drive < 4 h, not a desert, its day's load < 0.12, not Friday.
PRESETS["v5q1"] = PRESETS["v5a"] + ["safe_admit=(0.97,0.95,0.12)"]
# v5q2: + the scarcity switch from Tue 24:00 (last 24 h fee/typ >= 1.08 or warned/won >= 0.06): no admits, long cars declined, risk x1.5.
SCARCITY = ["scarcity=(1.08,0.06)", "scarcity_long=240", "scarcity_risk=1.5"]
PRESETS["v5q2"] = PRESETS["v5q1"] + SCARCITY
# v5q3: v5q2 with admits allowed on Friday too.
PRESETS["v5q3"] = PRESETS["v5q2"] + ["safe_admit_fri=true"]
# FLEET's volume arm V2 (load_bundle_w 0.6, load_free 0.12, load_slope 2: +779 on WAR, but fresh-10 0.891 / fresh-20 0.893 vs release
# 0.939 / 0.927) with the scarcity switch turning its load params back to the release's (0.07, 1.0, 1.0) once the week is scarce.
PRESETS["k-f1h5fV1"] = PRESETS["k-f1h5f"] + ["load_bundle_w=0.6"]  # as on claude/fleet-run (v1-fleet-run presets.py)
PRESETS["k-f1h5fV2"] = PRESETS["k-f1h5fV1"] + ["load_free=0.12", "load_slope=2"]
PRESETS["v5q2V"] = PRESETS["k-f1h5fV2"] + ["long_warn_distinct=true"] + SCARCITY + [
    "scarce_set=(('load_free',0.07),('load_slope',1.0),('load_bundle_w',1.0))"]
# V5 FLEET (research/re/v5/FLEET_BUILD.md). v5f1: fee1 cars with >= 8 h lead open at a flat 0.90 (floors kept), the one re-pick
# posts at 1.03 (a 0.90 opening ends at 0.945x over all attempts vs 0.80 picks' 0.91x after 1.6-1.7 gigs/car; openings2.py).
PRESETS["v5f1"] = PRESETS["v5a"] + ["v5_open=(8,0.9)", "v5_repost=1.03"]
# v5f2: + at the re-pick, pair the sitting car with another open unbooked single of ours (one driver, two cars, bundle_mult).
PRESETS["v5f2"] = PRESETS["v5f1"] + ["v5_pair2=true"]
# v5f3: + ladder singles under 8 h to the last pickup (fee1 cannot choose) open at 0.95 instead of 1.05; raises unchanged.
PRESETS["v5f3"] = PRESETS["v5f2"] + ["v5_short_open=0.95"]
# V5 stacks (fleet + quote): the fee-first fleet's saving spent on safe volume, with the Tuesday scarcity switch turning both off.
PRESETS["v5s1"] = PRESETS["v5f1"] + ["safe_admit=(0.97,0.95,0.12)"]
PRESETS["v5s3"] = PRESETS["v5f3"] + ["safe_admit=(0.97,0.95,0.12)"] + SCARCITY
# v5q2f: the switch on the fee signal alone, checked Tue 24:00 - Wed 12:00, no long declines (QUOTE_BUILD.md: the spec rule fires on 70%
# of normal fee1 weeks by Thu 00:00, mostly via warned/won >= 0.06; fee >= 1.08 alone to Wed 12:00: 72% of bad weeks, 20% of normal).
PRESETS["v5q2f"] = PRESETS["v5q1"] + ["scarcity=(1.08,9.0)", "scarcity_until=3600", "scarcity_risk=1.5"]
# v5p: v5a + at the 6 h re-pick, pair a sitting single with another open single of ours (pairs pay 0.84x vs ~1.03x for a re-post).
PRESETS["v5p"] = PRESETS["v5a"] + ["v5_pair2=true"]
# v5so: v5a + ladder singles under 8 h to the last pickup open at 0.95 instead of 1.05 (6-8 h 1.05 openings booked 97% on the first gig).
PRESETS["v5so"] = PRESETS["v5a"] + ["v5_short_open=0.95"]
# ARCHIVE (research/re/archive/R1_BADWEEKS.md): our weeks < EUR 7k are a rescue spiral (escalation 5.9-12k vs ~0.75k normally).
# Spec A: cap escalation near Halal's 1.6x (their 2x rescue: -740 for +0.1 pt). Spec B: Halal's late price in the quote from Monday.
STEEP_CAP = ["steep_rescue=(1.6,1.8,2.0)", "steep_plan=(1.5,1.7,1.9,2.1)"]
LATE_BARRIER = ["late_barrier=(0.955,300,4,20)"]
PRESETS["k-f1h5f-cap"] = PRESETS["k-f1h5f"] + STEEP_CAP
PRESETS["k-f1h5f-lb"] = PRESETS["k-f1h5f"] + LATE_BARRIER
PRESETS["k-f1h5f-lbc"] = PRESETS["k-f1h5f"] + LATE_BARRIER + STEEP_CAP
PRESETS["k-safe-dcl-cap"] = PRESETS["k-safe-dcl"] + STEEP_CAP
PRESETS["k-safe-dcl-lb"] = PRESETS["k-safe-dcl"] + LATE_BARRIER
# ARCHIVE: RoutePulse's backlog brake (research/re/archive/R2_BADWEEKS.md 5.1) on V5's volume arm, for V5's scarcity gate (fresh-10/20 >= 0.91).
BRAKE = ["backlog_brake=(0.03,10,16,24,0.24,0.10,0.86)"]
PRESETS["v5aV2b"] = PRESETS["v5aV2"] + BRAKE
PRESETS["k-f1h5f-bk"] = PRESETS["k-f1h5f"] + BRAKE
PRESETS["v5aV2b0"] = PRESETS["v5aV2"] + ["backlog_brake=(0.03,10,16,24,0.0,0.0,1.0)"]  # dry: logs BRAKE U only, no effect
# Offline calibration (research/re/archive/c_brake_cal.csv): hours with U > 0.03 x roster Mon-Thu: bad weeks fresh-10/20/15, dev-48 19-27,
# good weeks 0-9; U peaks Wed-Thu (fresh-20 max 49-52 vs good <= 31). RoutePulse's charge is small (<= ~EUR 34/car); the strong arm
# reacts twice as fast (scale 8) and cuts free load up to 30%.
PRESETS["v5aV2bs"] = PRESETS["v5aV2"] + ["backlog_brake=(0.03,10,8,24,0.5,0.2,0.7)"]
# V5L: FLEET's volume V2 held by ARCHIVE's late barrier (Halal: volume + a smooth late price toward the on-time target from Monday).
# V2 alone: fresh-20 0.889 unranked; + barrier: fresh-20 0.920, fresh-10 0.948, scarcity set +578 (se 338) 7/7 ranked vs the release.
LB = ["late_barrier=(0.955,300,4,20)"]
# v5a failed the holdouts (LEAD 22:10: H1 -130, H3 -87, nf-04 0.890): v5L drops its cheap long cars, keeps the distinct guard.
PRESETS["v5L"] = PRESETS["k-f1h5fD"] + ["load_bundle_w=0.6", "load_free=0.12", "load_slope=2"] + LB
PRESETS["v5La"] = PRESETS["v5aV2"] + LB  # the first test (v5-run3 tag v5V2lb): with v5a's long cars down to 0.90
PRESETS["v5L45"] = PRESETS["v5L"] + ["late_barrier=(0.945,300,4,20)"]  # looser target: keep more of V2's volume in normal weeks
PRESETS["v5L14"] = PRESETS["v5L"] + ["load_free=0.14"]                   # bolder volume under the same barrier
# V5 HUB (research/re/v5/HUB_BUILD.md): pairs book by their END (research/re/drivers/PAIRS.md). Pair score in hours = old key / 60 + w x
# ln(1 + nd30 of the final delivery). w = 2: nd30 5 -> 100 adds 2 x 2.8 = 5.6 h, above the usual spread of the old keys among a car's
# feasible partners (latest start: p75 spread on the fixture week in HUB_BUILD.md; release hop: <= ~1 h, 98% of pairs hop <= 30 min);
# that move is worth ~+18-24 pts of 60-min booking and warned 9.7% -> 1.6-3%, the strongest pair term after drive.
PRESETS["v5h1"] = PRESETS["v5La"] + ["pair_end=(2.0,0)"]
PRESETS["v5h2"] = PRESETS["v5h1"] + ["pair_long_empty=(240,10)"]  # + R2: no chain > 4 h of road into an end with nd30 <= 10 (18.5% warned)
PRESETS["v5h3"] = PRESETS["v5La"] + ["pair_long_empty=(240,10)"]  # R2 alone
# ARCHIVE: RoutePulse's climbing pair fee on v5La. Our pairs book at once at the 0.84 opening (59% within 10 min, 95% at the opening);
# a low first step catches the instant bookers cheaper and is back at 0.84 within ~75-110 min (research/re/archive/c_pairbook.py).
PRESETS["v5La-pc1"] = PRESETS["v5La"] + ["bundle_climb=((0,0.68),(25,0.74),(50,0.80))"]
PRESETS["v5La-pc2"] = PRESETS["v5La"] + ["bundle_climb=((0,0.60),(27,0.67),(54,0.74),(81,0.80))"]
# The barrier's other direction: v5La96 (target 0.96) lost -202 with 14 fewer orders; 0.95 lets more volume through it.
PRESETS["v5La95"] = PRESETS["v5aV2"] + ["late_barrier=(0.95,300,4,20)"]
# pc1b: pc1's 0.68 start, back at the usual 0.84 by +50 min (pc1: +75): pc1 split 27% vs 23% and instant bookings 34% vs 59% (c_pairdrop.py).
PRESETS["v5La-pc1b"] = PRESETS["v5La"] + ["bundle_climb=((0,0.68),(25,0.76))"]
# V5 stack (V5, 23:05): the shipped v5La + end-at-hub pairs (v5h2: +134 se 167 vs v5La, worst 0.926, dev-05 no collapse) + ARCHIVE's climbing
# pair fee (pc1: +379 se 132 vs v5La, MARKET's arm). Both touch pairs (which partner / at what fee): tested together before holdouts.
PRESETS["v5S"] = PRESETS["v5h2"] + ["bundle_climb=((0,0.68),(25,0.74),(50,0.80))"]

PRESETS["v5S-an"] = PRESETS["v5S"] + ["fee_anchor=1.0"]  # fees and quote costs off the week's drive-time line (plain cars)
PRESETS["v5S-an5"] = PRESETS["v5S"] + ["fee_anchor=0.5"]
# MARKET teamv5: the quote cost hold on the anchored typical (v5S-an5). The 1.05 hold was set on k-safe-dcl's typical; check it still fits.
PRESETS["v6-market-h100"] = PRESETS["v5S-an5"] + ["quote_cost_hold=1.0"]
PRESETS["v6-market-h110"] = PRESETS["v5S-an5"] + ["quote_cost_hold=1.1"]
# MARKET bold arm (quote_cal.py on v5S-an5: same_day wins 2-7 pts above the learner's P, next_day short 6-10 below; PRICING.md saw the same
# on c3g): with both quoted, same_day costs at least next_day / 0.92 (+8.7%), so same-day buyers pay for speed and price-led ones step down.
PRESETS["v6-market-steer"] = PRESETS["v5S-an5"] + ["steer=0.92"]

# price_slope: price on a flatter win curve (real within-quote slope ~2-3 vs learner 6.7; research/re/market/v4/slope_fit.py)
PRESETS["v6-market-ps4"] = PRESETS["v5S-an5"] + ["price_slope=4.0"]
PRESETS["v6-market-ps3"] = PRESETS["v5S-an5"] + ["price_slope=3.0"]
PRESETS["v6-market-ps55"] = PRESETS["v5S-an5"] + ["price_slope=5.5"]
PRESETS["v6-market-h120"] = PRESETS["v5S-an5"] + ["quote_cost_hold=1.2"]
PRESETS["v6-market-mon05"] = PRESETS["v5S-an5"] + ["mon_shadow=0.05"]
PRESETS["v6-market-mon10"] = PRESETS["v5S-an5"] + ["mon_shadow=0.10"]
PRESETS["v6-market-ss"] = PRESETS["v5S-an5"] + ["share_shadow=(0.64,0.05,10)"]
PRESETS["v6-market-h110ss"] = PRESETS["v6-market-h110"] + ["share_shadow=(0.64,0.05,10)"]
PRESETS["v6-market-lf"] = PRESETS["v5S-an5"] + ["learn_fastest=true"]
