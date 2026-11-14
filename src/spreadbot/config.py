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
    war_guard: bool = False            # freeze world and dealer learning on a day whose shift is below -war_shift
    war_shift: float = 0.12
    lane_w: float = 0.0                # weight of the cross-world lane table (Javier's lanes.json) in the competitor level
    max_per_batch: int = 0             # decline once we hold this many orders from one batch (a yard sending many cars)
    place_lr: float = 0.0              # per (pickup place, day) shift, spread over 80 km: the outage (0 = off)
    dealer_lr: float = 0.006           # per dealer: the competitor cuts where we win most
    min_ratio: float = 1.00            # never quote under list
    max_ratio: float = 1.80
    shadow_cents: int = 0              # opportunity cost of one car of driver capacity
    min_ev_cents: int = 200            # expected margin below this is not worth a driver
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
    steer: float = 0.0                 # with both quoted: same_day at least next_day / steer (dealers take next_day under ~0.85x)
    steer_down: bool = False           # instead lower next_day to steer x same_day
    # --- on-time selection
    ontime_fee_assumed: float = 1.6    # the fee the on-time model assumes (fee_plan reaches about this)
    ontime_shift: float = 0.0
    ontime_model: str = "policy"       # "policy": fit on weeks of this dispatch policy; "research": the first fit
    dilute: bool = True               # in rescue, the bar is the projection (+ margin), not a fixed 0.92
    dilute_margin: float = 0.01
    calibrate: bool = False            # scale P(on time) by this world's observed/predicted on-time ratio
    min_slack_h: float = 1.5
    theta: float = 0.80                # bar on P(on time) for a car in normal mode
    theta_tight: float = 0.88
    theta_rescue: float = 0.93
    gov_tight: float = 0.95            # projected on-time share under which the bar tightens (v1w: min on-time 0.932 vs 0.919)
    gov_rescue: float = 0.93 
    # --- congestion: open gigs near the pickup make the next car there dearer
    cong_frac: float = 0.0             # extra cost per open gig beyond cong_free, as a share of the typical fee
    cong_free: int = 3
    cong_radius: float = 80.0          # km: drivers come from about this far for a typical gig
    cong_horizon: int = 18 * 60        # only gigs whose last pickup is within this many minutes
    # --- load: our cars due per day over the world's drivers
    load_free: float = 0.07            # rc3: with late 2.0 the long and thin-town cars get dear, so the safe ones can take more load (y4)
    adaptive_load: bool = False        # scale load_free by how easily our first posts book this week
    cap_min: float = 0.7
    cap_max: float = 1.4
    load_flat_cents: int = 0           # load cost per car in cents (every car counts the same for the gate); 0 = one typical fee
    load_slope: float = 1.0            # extra cost, in typical fees, per 0.05 of load above load_free
    # --- fees
    fee_mode: str = "relative"         # "span": fee_plan over the slack; "relative": fee_rel anchored to lastPickupAt
    fee_open: float = 1.05              # 12/12 ranked, min on-time 0.919 vs 11/12, 0.896 at 0.95 (v1v vs v1p, 12 seeds)
    hot_open: bool = False             # cars the expensive-car model flags open at fee_open_hot instead of fee_open
    hot_p: float = 0.4
    fee_open_hot: float = 1.3
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
    crunch_drops: int = 0              # this many drops 05-13h = a crunch day (flu): escalate today's open gigs, tighten the bar
    view_raise_n: int = 0              # this many viewers and no booking: raise to view_raise_mult at once
    view_raise_after: int = 45
    view_raise_mult: float = 1.5
    own_alarm: bool = True             # escalate before the effective last pickup (note deadlines included)
    alarm_minutes: int = 360           # 6 h: earlier than the world's 3 h warning; ranked 6/6 vs 4/6 (v1i vs v1h)
    use_offers: bool = False           # offers to drivers near the pickup on a deadline warning
    viewer_offers: bool = False        # offers to drivers who viewed an unbooked gig
    offer_after: int = 20              # minutes a gig is open before its viewers get offers
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
    hold_all: bool = False             # hold every car (default: only cars that could be paired, see simple())
    hold_open: bool = True             # at a release, also pair with our open unbooked single gigs
    hold_price: bool = False           # quote a car that pairs with a held car (same pickup day, near) at the bundle cost
    bundle_keep: float = 0.0          # a dropped bundle with this many hours to spare stays a bundle, raised to this x its base (0 = split)
    hold_km: float = 0.0               # air km from A's delivery to B's pickup for a release pair (0 = bundle_km)
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
