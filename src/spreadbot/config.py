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
    dealer_lr: float = 0.006           # per dealer: the competitor cuts where we win most
    min_ratio: float = 1.00            # never quote under list
    max_ratio: float = 1.80
    shadow_cents: int = 0              # opportunity cost of one car of driver capacity
    min_ev_cents: int = 200            # expected margin below this is not worth a driver
    late_cost_frac: float = 0.6        # a late car: refund 10-50%, trust halved, the gate at risk
    cost_prior: float = 1.15           # expected fee over typical fee with fee_plan (research: 0.9 books 64% in time)
    cost_prior_n: int = 30
    only_next_if_no_same: bool = False # quote next_day only when we do not quote same_day (next_day cars cost more)
    trust_bonus: float = 0.0           # weight of dealer-trust value in the quote (1 = full expected value)
    gate_bonus_cents: int = 0          # value of one more safe on-time order when the projection is under target
    gate_target: float = 0.935
    gate_span: float = 0.02            # full bonus this far under target
    gate_safe_p: float = 0.95
    # --- on-time selection
    ontime_fee_assumed: float = 1.6    # the fee the on-time model assumes (fee_plan reaches about this)
    ontime_shift: float = 0.0
    calibrate: bool = False            # scale P(on time) by this world's observed/predicted on-time ratio
    min_slack_h: float = 1.5
    theta: float = 0.70                # bar on P(on time) for a car in normal mode
    theta_tight: float = 0.82
    theta_rescue: float = 0.92
    gov_tight: float = 0.935           # projected on-time share under which the bar tightens
    gov_rescue: float = 0.915
    # --- congestion: open gigs near the pickup make the next car there dearer
    cong_frac: float = 0.0             # extra cost per open gig beyond cong_free, as a share of the typical fee
    cong_free: int = 3
    cong_radius: float = 80.0          # km: drivers come from about this far for a typical gig
    cong_horizon: int = 18 * 60        # only gigs whose last pickup is within this many minutes
    # --- fees
    fee_mode: str = "span"             # "span": fee_plan over the slack; "relative": fee_rel anchored to lastPickupAt
    fee_open: float = 0.95
    fee_hold: int = 45                 # minutes the opening fee shows before any raise
    fee_rel: tuple = ((8, 1.25), (5, 1.6))   # (hours before lastPickupAt, fee over typical fee)
    fee_plan: tuple = ((0.0, 0.95), (0.15, 1.15), (0.4, 1.45), (0.7, 1.85))  # (share of slack, fee over typical fee)
    steep_plan: tuple = (2.0, 2.4, 2.8, 3.3, 3.8)  # after a deadline warning: generous, a late car costs more
    steep_step: int = 30
    gov_steep: bool = False            # choose the escalation by the projected on-time share
    gov_relaxed: float = 0.955         # above this projection, a car is not worth saving at any price
    steep_relaxed: tuple = (1.6, 1.9, 2.2)
    steep_rescue: tuple = (2.0, 2.5, 3.0, 3.5, 4.0)
    late_plan: tuple = ()
    crunch_drops: int = 0              # this many drops 05-13h = a crunch day (flu): escalate today's open gigs, tighten the bar
    view_raise_n: int = 0              # this many viewers and no booking: raise to view_raise_mult at once
    view_raise_after: int = 45
    view_raise_mult: float = 1.5
    own_alarm: bool = False            # escalate 3 h before the effective last pickup (note deadlines included)
    alarm_minutes: int = 180              # e.g. ((0, 1.2), (4, 1.5), (12, 2.0)): fees for a car that is late anyway
    use_offers: bool = True            # offers to drivers near the pickup on a deadline warning
    viewer_offers: bool = False        # offers to drivers who viewed an unbooked gig
    offer_after: int = 20              # minutes a gig is open before its viewers get offers
    offer_mult: float = 1.15           # offer fee over typical fee (or the app fee, if higher)
    offer_mult_urgent: float = 1.8
    offer_max_km: float = 120.0
    charge_km: float = 190.0           # rule: EV < 30% on a route over 200 km needs charging; margin for road km
    # --- bundles: two of our cars in one gig, the second picked up near where the first is delivered
    bundle: bool = False
    bundle_km: float = 25.0            # straight line from the first delivery to the second pickup
    bundle_lead: int = 60              # minutes before a driver can start, when checking a chain
    bundle_margin: int = 60            # minutes to spare before each deadline
    bundle_min_slack: int = 6 * 60     # a chain needs this long before its last start
    bundle_window: int = 120           # pair with gigs posted at most this many minutes ago
    bundle_mult: float = 0.8           # one driver, no trip home in between: the pair costs less than two gigs
    unbundle_minutes: int = 5 * 60     # unbooked this close to its last start: post the cars alone
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
