"""Every knob of the bot, with the reason for its default. Each idea can be switched off for an ablation."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace


@dataclass(frozen=True)
class Config:
    # --- quoting
    quote_options: tuple = ("same_day", "next_day", "within_3_days")
    mu_prior: float = 1.28             # competitor over list: 3 research weeks, P(win)=0.5 near 1.28 (lab/frank/curves.py)
    win_slope: float = 6.7             # same fit: win 0.87 at 1.0, 0.19 at 1.5
    mu_lr: float = 0.004               # world level: slow, ~100 quotes to move a lot
    day_lr: float = 0.012              # today's shift: fast, the day factor and the price war are per day
    day_kalman: bool = False           # today's competitor level as two Kalman hypotheses (normal day / price-war day at 0.8x) instead of
    kal_sd: float = 0.125              # the SGD day shift: prior sd of the day factor (log; alignas/Halal), times the world level here
    kal_war: float = 0.8               # war-day level over usual (RULES: 20% under everywhere, 08-18, one weekday)
    kal_war_sd: float = 0.04           # its sd (log)
    war_guard: bool = False            # freeze world and dealer learning on a day whose shift is below -war_shift
    war_shift: float = 0.12
    lane_w: float = 0.0                # weight of the cross-world lane table (Javier's lanes.json) in the competitor level
    max_per_batch: int = 0             # decline once we hold this many orders from one batch (a yard sending many cars)
    place_lr: float = 0.0              # per (pickup place, day) shift, spread over 80 km: the outage (0 = off)
    outage_z: float = 0.0              # the outage (HANDBOOK: one pickup region = town + 80 km, 08-18, one non-war day, backup ~30% dearer): flag the
                                       # region once the log-likelihood of +outage_up there reaches this, then price it up until 18:00 (0 = off)
    outage_up: float = 0.25            # the flagged region's competitor level, times (1 + this)
    outage_min: int = 4                # results in the region before it can be flagged
    quote_move_cost: bool = False      # quote each option at move_cost (the fee rule's opening: 0.92-0.95x where drivers live near the delivery), not the flat cost
    dist_lr: float = 0.0               # the competitor's price list changes shape once a week (HANDBOOK): learn a slope of its level on ln(km),
                                       # c3g residuals show a lasting step of ~0.14 ratio per ln km on one Tue-Thu morning (PRICE_EVENTS.md) (0 = off)
    learn_fastest: bool = False        # learn the competitor only from requests where we quoted the fastest option: with only a slower
                                       # option quoted the dealer often wants speed (win 0.31 vs 0.52 at the same ratio, 16,818 quotes), which drags mu down
    dealer_lr: float = 0.006           # per dealer: the competitor cuts where we win most
    min_ratio: float = 1.00            # never quote under list
    max_ratio: float = 1.80
    menu: bool = False                 # one price in fastest-option euros, slower options cheaper by the dealer's speed value, every option
                                       # at the same margin (dealer buys max(threshold - price); Halal: next = same - €14.5, 3 days = next - €6.1)
    speed_cents: tuple = (1450, 610)   # the dealer's euros for same->next day and next->within 3 days (Halal's medians)
    s_cap_cents: int = 0               # with same_day and next_day quoted, same_day at most next_day + this - €1: a dealer pays ~€9-15 more for
                                       # speed, so past that gap it takes next_day for less (our weeks: gap €15-20 -> takes same_day 38%) (0 = off)
    mu_w: tuple = ()                   # (day, dealer, lane) weights of mu's parts when pricing (learning unchanged): fitted on 34 c3g weeks,
                                       # 0.65/0.4/0.6, the full parts over-react (research/re/market/PRICING.md) (() = 1/1/1)
    short_fee: tuple = ()              # (hours, drive min, mult): an option whose estimated last pickup is < hours after respondBy and drive >= min quotes the fee x mult; such cars paid 1.26x the assumed fee vs 1.00-1.10 elsewhere (research/re/market/SHORT_NOTICE.md) (() = off)
    shadow_cents: int = 0              # opportunity cost of one car of driver capacity
    class_cost: tuple = ()             # (private pickup, private delivery) fee over the dealer-to-dealer fee in the quote: 1.072, 1.032 measured (() = off)
    min_ev_cents: int = 200            # expected margin below this is not worth a driver
    pl_cal: tuple = ()                 # ((drive minutes under, factor), ...): scale the quoted P(late) in the risk price by drive time.
                                       # 20,551 won orders of the c1/c3/c4/y4 runs: late/quoted = 0.55 (<1 h), 0.30-0.36 (1-4 h), 0.47 (4-6 h), 1.57 (>6 h)
    late_cost_frac: float = 2.0        # rc3: a late car costs refund + trust + gate risk; 2.0 with load 0.07 = y4, +24% over rc2 on 5 fresh weeks, 5/5 ranked
    drive_cost: bool = False           # expected fee by drive time (table in desk.py), not one average
    cost_prior: float = 1.15           # expected fee over typical fee with fee_plan (research: 0.9 books 64% in time)
    cost_prior_n: int = 30
    only_next_if_no_same: bool = False # quote next_day only when we do not quote same_day (next_day cars cost more)
    trust_loss_w: float = 0.0          # charge (1 - P(on time)) x the trust a late car would cost this dealer
    protect_trust_cents: int = 0       # a dealer's trust at stake above this: escalate as normal (x2: as rescue)
    trust_invest: bool = False         # big dealers under 25 trust: win their safe cars at P(win) ~ invest_pwin (Mon-Wed)
    invest_share: float = 0.08         # a dealer with at least this share of all requests
    invest_pwin: float = 0.8
    invest_p_ok: float = 0.93
    invest_min_margin_cents: int = 300
    trust_bonus: float = 0.0           # weight of dealer-trust value in the quote (1 = full expected value)
    gate_bonus_cents: int = 0          # value of one more safe on-time order when the projection is under target
    gate_target: float = 0.935
    gate_span: float = 0.02            # full bonus this far under target
    gate_safe_p: float = 0.95
    load_cap: float = 0.0              # no quote for an option whose deadline day already holds this share of the roster (0 = off):
                                       # late 4-6% under day load 0.12, 8% at 0.12-0.14, 12-13% above (research/re/lateload.py, tuning runs)
    gate_load_max: float = 0.0         # no gate bonus for a car whose deadline day is already this loaded (0 = off): late share climbs
                                       # from 0.046 at day load 0.08-0.10 to 0.084 at 0.12-0.14 and 0.122 above (research/re/lateload.py)
    steer: float = 0.0                 # with both quoted: same_day at least next_day / steer (dealers take next_day under ~0.85x)
    steer_down: bool = False           # instead lower next_day to steer x same_day
    # --- on-time selection
    ontime_fee_assumed: float = 1.6    # the fee the on-time model assumes (fee_plan reaches about this)
    ontime_shift: float = 0.0
    ontime_model: str = "policy"       # "policy": fit on weeks of this dispatch policy; "research": the first fit; "gbm": late_gbm.py trees
    gbm_site_lead: bool = False        # gbm lead_h from the site-hours last pickup (as trained), not deadline - drive: 4-5 h band P(late) 0.036 -> 0.079 vs 0.087 seen (research/re/market/SHORT_NOTICE.md)
    dilute: bool = True               # in rescue, the bar is the projection (+ margin), not a fixed 0.92
    dilute_margin: float = 0.01
    calibrate: bool = False            # scale P(on time) by this world's observed/predicted on-time ratio
    min_slack_h: float = 1.5
    theta: float = 0.80                # bar on P(on time) for a car in normal mode
    theta_tight: float = 0.88
    theta_rescue: float = 0.93
    gov_tight: float = 0.95            # projected on-time share under which the bar tightens (v1w: min on-time 0.932 vs 0.919)
    gov_rescue: float = 0.93 
    gov_stuck_p: float = 0.0           # projection: an order whose gig is posted but unbooked for gov_stuck_age minutes counts as this likely
    gov_stuck_left: int = 100000        # gov_stuck_p applies when the last pickup is this close; further out the cap is gov_stuck_far
    gov_stuck_far: float = 0.0         # (0 = gov_stuck_p for every stuck order, the first version)
    gov_stuck_steep: bool = True       # the escalation level also reads the stuck-adjusted projection (False: only the admission bar)
    gov_stuck_age: int = 60            # on time (0 = off). Such orders end late 40-55% of the time in every week (lab/build/openstate.py, 13 weeks)
    strict_warn: float = 0.0           # when this share of our orders has had a deadline warning, switch to the strict governor (0 = off):
    strict_after: int = 60             # (judged once we hold this many orders) dev-43: c1 had 20 warnings by Thursday (8%), normal weeks 2-5%
    strict_gov: tuple = (0.95, 0.93, 0.95, 0.80)  # strict (gov_tight, gov_rescue, gov_relaxed, theta) = y4's, the only config ranked on dev-43
    # --- congestion: open gigs near the pickup make the next car there dearer
    cong_frac: float = 0.0             # extra cost per open gig beyond cong_free, as a share of the typical fee
    cong_free: int = 3
    cong_radius: float = 80.0          # km: drivers come from about this far for a typical gig
    cong_horizon: int = 18 * 60        # only gigs whose last pickup is within this many minutes
    # --- load: our cars due per day over the world's drivers
    load_free: float = 0.07            # rc3: with late 2.0 the long and thin-town cars get dear, so the safe ones can take more load (y4)
    load_free_mon2: float = 0.0        # load_free for cars due on the last Monday (0 = load_free): Friday noev is 80-94% the load charge, Mon2 cars 2.4-3.2% late (research/re/market/WAR_FRIDAY.md)
    mon2_max_drive: int = 0            # load_free_mon2 only for drives under this (min): long Mon2 gigs wait ~77 h, 29-44% late (research/re/market/MON2_LATE.md) (0 = all)
    adaptive_load: bool = False        # scale load_free by how easily our first posts book this week
    cap_min: float = 0.7
    cap_max: float = 1.4
    load_flat_cents: int = 0           # load cost per car in cents (every car counts the same for the gate); 0 = one typical fee
    load_slope: float = 1.0            # extra cost, in typical fees, per 0.05 of load above load_free
    load_desert_n: int = 0             # cars delivering where <= this many drivers live within 60 road min keep the full load charge
                                       # (0 = off): the stacks' extra late cars on dev-46 are cars c3g also won, starved by extra long
                                       # drives into such towns (21% of won cars that week vs ~35 cars in a median week; drivers/DEV46.md)
    load_desert_slope: float = 1.0     # their load_slope (c3g's)
    # --- fees
    fee_mode: str = "relative"         # "span": fee_plan over the slack; "relative": fee_rel anchored to lastPickupAt
    fee_open: float = 1.05              # 12/12 ranked, min on-time 0.919 vs 11/12, 0.896 at 0.95 (v1v vs v1p, 12 seeds)
    hot_open: bool = False             # cars the expensive-car model flags open at fee_open_hot instead of fee_open
    hot_p: float = 0.4
    fee_open_hot: float = 1.3
    fee_open_dense: float = 0.0        # opening fee for a single whose pickup has >= dense_n drivers within 30 km (0 = fee_open):
    dense_n: int = 150                 # dense towns book in a median 2 min at 1.05 (13,297 singles of the c1/c3/c4/y4 runs)
    fee_open_rule: tuple = ()          # ((min hours to last pickup, min drivers living <= 30 road min from the delivery, opening), ...),
                                       # first match wins, else fee_open. 1.05 openings book in a median 1-5 min and are 63% of c3g's fees;
                                       # 0.95 openings pay 0.96-0.98 vs 1.05-1.06 with slack > 24 h (988k gigs, research/re/drivers/gigs.py)
    fee_open_day: tuple = ()           # ((first day 0=Mon, last day, min drivers <= 30 road min from delivery, min hours to last pickup, opening), ...) first match, before fee_open_rule
                                       # nd30 > 40 + 90-min relook kept warned 2.0/2.7% vs c3g 1.6/2.4%, waits to 1.25 0.7/1.2% vs 1.0/0.5%; nd30 <= 40 warned 3.0 -> 4.3% (SAFE_OPEN.md)
    stop_windows: bool = False         # pickup window ends at the car's last pickup, delivery window at deadline - stop_margin
    stop_margin: int = 60              # (Halal / jaffa: failed visits 10.6 -> 0, deliveries >24 h late fixed)
    fee_cut_guard: tuple = ()          # (min P(on time) at quote, min governor projection, max mean booked/first fee of the last 60 bookings):
                                       # fee_open_rule cuts only when all hold, else the opening is fee_open (() = off). Deep cuts failed H1 on one
                                       # scarce week each; board W3 had booked/opening 1.27 vs 1.05-1.07 (EXTERNAL.md)
    desert_n: int = 0                  # a delivery town with fewer drivers living <= 60 road min is a desert: no fee_open_rule cut and the own
                                       # alarm at desert_alarm (0 = off). dev-46: 21% of won cars, ~2x late in every policy (DEV46.md)
    desert_alarm: int = 720            # minutes before the last pickup: escalate a desert car this early (others: alarm_minutes)
    fee_hold: int = 45                 # minutes the opening fee shows before any raise
    fee_rel: tuple = ((8, 1.25), (5, 1.6))   # (hours before lastPickupAt, fee over typical fee)
    fee_plan: tuple = ((0.0, 0.95), (0.15, 1.15), (0.4, 1.45), (0.7, 1.85))  # (share of slack, fee over typical fee)
    steep_plan: tuple = (1.7, 2.0, 2.3, 2.6)  # after a deadline warning: generous, a late car costs more
    steep_step: int = 30
    gov_steep: bool = True             # choose the escalation by the projected on-time share
    gov_relaxed: float = 0.95          # above this projection, a car is not worth saving at any price
    steep_relaxed: tuple = (1.4, 1.6, 1.8)  # v1aa: p10 margin 6,773 vs 5,594, same mean
    steep_rescue: tuple = (2.0, 2.5, 3.0, 3.5, 4.0)
    late_plan: tuple = ((0, 1.2), (4, 1.5), (12, 2.0))  # (hours from now, fee): a car that is late anyway, no steep fees
    flu_drops: int = 0                 # this many of our gigs dropped 00:00-01:00 = a flu night (0 = off): on tuning weeks, nights with
                                       # >= 8 such drops (125 of 752) make that day's cars 8.9% late vs 4.7% (research/re/flu.py; Halal idea 14)
    flu_mult: float = 1.9              # P(late) multiplier for cars due on a flu day, at quote time and in the projection (8.9 / 4.7)
    repost_past_last: int = 0          # minutes after an open gig's last pickup to withdraw and post it again without the order's windows
                                       # (0 = off): till then no driver can book it (research/re/external/RIVAL_FEES.md #5)
    long_warn: tuple = ()              # (drive min, n, window min): decline cars with drive >= this while >= n of our long cars got a
                                       # deadline warning in the last window min (() = off). Both unranked fresh weeks: 2-3x the usual long
                                       # cars, 36-39% late, warned 5x as often, P(on time) at quote ~0.94 as usual (research/re/H2_AUTOPSY.md)
    crunch_drops: int = 0              # this many drops 05-13h = a crunch day (flu): escalate today's open gigs, tighten the bar
    view_raise_n: int = 0              # this many viewers and no booking: raise to view_raise_mult at once
    view_raise_after: int = 45
    view_raise_mult: float = 1.5
    own_alarm: bool = True             # escalate before the effective last pickup (note deadlines included)
    alarm_minutes: int = 360           # 6 h: earlier than the world's 3 h warning; ranked 6/6 vs 4/6 (v1i vs v1h)
    use_offers: bool = False           # offers to drivers near the pickup on a deadline warning
    viewer_offers: bool = False        # offers to drivers who viewed an unbooked gig
    offer_after: int = 20              # minutes a gig is open before its viewers get offers
    offer_home_n: int = 0              # direct offers per unbooked single to drivers living near its delivery, not notified (home > 30 km
                                       # from the pickup): they book 26% of the gigs they view but view 1% (0 = off; reach.py, 20 c3g weeks)
    offer_home_after: int = 20         # minutes after posting: most singles book in the first 1-5 min, offers are 3 per driver per day
    offer_home_slack: int = 6 * 60     # only while the last pickup is this far off: the driver must still get there
    offer_home_min: int = 30           # road minutes from the delivery to the driver's home
    offer_mult: float = 1.15           # offer fee over typical fee (or the app fee, if higher)
    offer_mult_urgent: float = 1.8
    offer_max_km: float = 120.0
    charge_km: float = 190.0           # rule: EV < 30% on a route over 200 km needs charging; margin for road km
    # --- bundles: two of our cars in one gig, the second picked up near where the first is delivered
    bundle: bool = True
    bundle_price: bool = False         # quote a car that chains with one of our open gigs at the bundle cost
    bundle_km: float = 25.0            # straight line from the first delivery to the second pickup
    bundle_lead: int = 60              # minutes before a driver can start, when checking a chain
    bundle_margin: int = 60            # minutes to spare before each deadline
    bundle_min_slack: int = 6 * 60     # a chain needs this long before its last start
    bundle_window: int = 120           # pair with gigs posted at most this many minutes ago
    bundle_mult: float = 0.8           # one driver, no trip home in between: the pair costs less than two gigs
    unbundle_minutes: int = 5 * 60     # unbooked this close to its last start: post the cars alone
    # --- chain planner (branch-v1-frank, preset chains): hold a won car a few hours, unposted, to find a chain partner
    bundle_max_drive: int = 12 * 60 - 30  # road minutes of a chain; k5: 74% booked under 4 h, 17% at 10-12 h
    bundle_min_lead: int = 0           # minutes from now to the chain's start; k5: 46% booked under 2 h, 70% at 18-30 h
    bundle_empty_end: tuple = ()       # (drive min, drivers): no chain over this drive whose end has fewer drivers living <= 30 road min (() = off);
                                       # pairs > 4 h ending at nd30 <= 10: 45% booked in 60 min, 18.5% warned vs singles 60% / 3.7% (research/re/drivers/PAIRS.md)
    bundle_open_dense: tuple = ()      # (min hours to the chain's last start, min drivers living <= 30 road min from its end, opening share of
                                       # the two typical fees); () = off. Pairs ending at nd30 >= 150 book 91% in 60 min at 0.84 vs 67% at <= 10 (PAIRS.md)
    long_split: tuple = ()             # (min chain drive, minutes): a pair with this much driving still unbooked this long after posting is split
                                       # into singles (() = off). Release pairs book within 3 h 82%; of those unbooked at 3 h only 32% ever book, and
                                       # long ones carry 4.4 of 20.5 warned singles/wk (k-safe, research/re/drivers/RESCUES.md)
    bundle_short: bool = False         # pick the partner that makes the shortest chain (short chains book more often), not the one with most slack
    bundle_keep_drop: bool = False     # a dropped bundle with time to spare stays in the app as a bundle (split later if still unbooked)
    bundle3: bool = False              # a held or new car may join an open two-car chain as its first or third car
    bundle3_mult: float = 0.75         # fee of a three-car chain, as a share of the three typical fees
    bundle_soon_lead: int = 0          # a chain starting sooner than this (minutes) is allowed, at bundle_soon_mult (0 = off)
    bundle_soon_mult: float = 1.0      # fee of such a chain over the two typical fees: still under two single gigs (~1.18x)
    bundle_soon_slack: int = 180       # such a chain needs this long before its last start, and splits this long before it
    load_bundle_w: float = 1.0         # a car in one of our live chains counts this much in the day's load (one driver moves two)
    bundle_rel: tuple = ()             # ((hours before the chain's last start, fee as a share of the two typical fees), ...); () = fee_rel on the bundle fee
    hold_minutes: int = 0              # hold a won car up to this long, unposted, to find a chain partner (0 = post at once)
    hold_lead: int = 12 * 60           # post a held car at the latest this long before its pickup window opens
    hold_slack: int = 8 * 60           # and this long before its last pickup
    # --- evening release: hold cars picked up on a later day, release them together and pair them first
    hold: bool = True                  # rc3: a car for a later day waits for its release (+14% on dev-19..30, 12/12 ranked)
    hold_hour: int = 16                # release at 16:00 the day before: 14-16 best; at 18-20 pairs stay unbooked into the night
    hold_min_left: int = 0             # post at once a car whose last pickup is less than this many minutes after its release (0 = off):
                                       # next-day cars with last pickup 12-14 h held to 16:00 are 25% late vs 11% posted at once (176 c3 weeks)
    hold_all: bool = False             # hold every car (default: only cars that could be paired, see simple())
    hold_open: bool = True             # at a release, also pair with our open unbooked single gigs
    hold_price: bool = False           # quote a car that pairs with a held car (same pickup day, near) at the bundle cost
    pairq_mult: float = 0.0            # quote cost multiplier for a car hold_price/bundle_price flag as pairable (0 = bundle_mult): 0.8 priced every such car as a pair, gave away EUR2-5/order
    bundle_keep: float = 0.0          # a dropped bundle with this many hours to spare stays a bundle, raised to this x its base (0 = split)
    hold_km: float = 0.0               # air km from A's delivery to B's pickup for a release pair (0 = bundle_km)
    hold_weekend: bool = False         # a held car whose last pickup is on the last Monday is released Sunday at hold_hour (not before Friday):
                                       # bookings made 2+ days ahead are a third dropped and a fifth late (RESEARCH_2 round 2), Mon2 drivers are idle
    drop_calm_hours: float = 0.0       # a single dropped with more than this many hours to its last pickup is posted again at the opening
                                       # fee instead of escalated (k-safe, 35 weeks: 25 of 35 drops/wk had > 16 h left, rebooked at
                                       # 1.24-1.31x typical, 2-4% late); 0 = off
    repair_pairs: bool = False         # a car won during the day may pair with any open unbooked single of ours, not only one posted in the last bundle_window
    repair_drive: int = 300            # such a pair drives at most this many minutes (k18: chains under 5 h book 85%)
    repair_lead: int = 360             # and starts at least this long from now (k18: pairs formed under 2 h ahead book 46%)
    repair_mult: float = 0.0           # fee of such a pair over the two typical fees (0 = bundle_mult). Halal: 0.85, a sitting car paired
                                       # finds a driver within 60 min 83-85% of the time vs 24% alone (research/TOP_TEAMS.md §2)
    repair_split: int = 0              # minutes: a pair built from a sitting single and still unbooked after this is split back into
                                       # singles (Halal: 60); 0 = only the usual unbundle_minutes before its last start
    # --- second look: one raise for a single that sits unbooked (Halal: +€1.9k with board pairs, 350 -> 438 orders)
    relook_minutes: int = 0            # an open single still unbooked this long after posting gets one raise now (Halal 360); 0 = off
    relook_mult: float = 1.2           # to this x typical fee (one step above fee_open 1.05); later fee_rel steps stay above it
    relook_min_left: int = 8 * 60      # only while its last pickup is further than this: closer, fee_rel's own raises take over
    # --- backhaul offers: one of our drivers finishing near an open car of ours gets a direct offer for it
    backhaul: bool = False             # the app does not notify a driver where our gigs took them; a second car costs them little
    backhaul_mult: float = 1.0         # offer fee over typical fee (never under the app fee unless backhaul_below)
    backhaul_below: bool = False       # offer at backhaul_mult even when the app shows more
    backhaul_road: int = 45            # road minutes from where the driver finishes to the next pickup
    backhaul_wait: int = 90            # minutes the driver may wait for the pickup window or the site to open
    backhaul_free_by: int = 17 * 60    # only drivers who finish by this minute of the day
    backhaul_home_by: int = 21 * 60    # the second car is delivered by this minute of the day
    # --- experiments (research runs only)
    experiment_quote: bool = False
    exp_quote_lo: float = 1.0
    exp_quote_hi: float = 1.8
    experiment_fee: bool = False
    exp_fee_ratios: tuple = (0.9, 1.1, 1.3, 1.5, 1.8, 2.2)

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)

    @staticmethod
    def parse(overrides: list[str]) -> "Config":
        cfg = Config()
        types = {f.name: f.type for f in fields(Config)}
        kw = {}
        for o in overrides:
            k, v = o.split("=", 1)
            cur = getattr(cfg, k)
            if isinstance(cur, bool):
                kw[k] = v.lower() in ("1", "true", "yes", "on")
            elif isinstance(cur, int):
                kw[k] = int(v)
            elif isinstance(cur, float):
                kw[k] = float(v)
            elif isinstance(cur, tuple):
                kw[k] = eval(v)  # research knob, typed by hand
            else:
                kw[k] = v
        return cfg.with_(**kw)
