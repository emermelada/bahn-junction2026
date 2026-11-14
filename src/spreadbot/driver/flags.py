"""Driver-side switches. Each idea sits behind one, so harness/sweep.py --flag driver.<name>=<value> can ablate it."""
FLAGS = {
    "fee_open": 1.4,  # opening fee as a multiple of the typical fee; 1.2 booked fewer in time (b5), 1.6 cost more (b3)
    "fee_open_long": 1.0,  # flat fee for a gig posted a day or more before its last pickup; 0 uses fee_open (b15 1.2x, b18 1.0x: median €3.9k -> €6.8k -> €10.5k on rc1)
    "long_fee_over_weekend": False,  # True lets a gig due after the weekend open at fee_open_long (rc2: 8/12 ranked; False: 12/12)
    "fee_open_weekend": 0.0,  # flat fee for a gig whose last pickup is after the weekend; 0 uses fee_open
    "fee_open_mid": 0.0,  # flat fee for a gig posted 8-24 hours before its last pickup; 0 uses fee_open
    "fee_top": 1.4,  # the schedule rises to this multiple; <= fee_open means one flat fee, which teaches no waiting
    "raise_lead": 360,  # minutes before lastPickupAt at which a still-open gig gets one raise to fee_raise; 0 is off (b7)
    "fee_raise": 1.8,  # that one raise, as a multiple of the typical fee
    "raise_mid_lead": 0,  # minutes before lastPickupAt for an earlier, smaller raise to fee_raise_mid; 0 is off
    "fee_raise_mid": 1.1,  # the earlier raise, for gigs opened low (fee_open_long below 1)
    "bundle": False,  # post two single cars as one chain when car A delivers near car B's pickup
    "bundle_factor": 0.8,  # the chain's fee as a share of the two single fees
    "bundle_hold": 120,  # minutes a new car waits for a partner before it is posted alone
    "bundle_slack": 480,  # only cars with at least this many minutes to their last pickup wait for a partner
    "bundle_gap": 45,  # road minutes at most from car A's delivery to car B's pickup
    "min_drivers_near": 0,  # decline pickups with fewer drivers living within 30 km; 0 is off
    "max_backlog": 15,  # decline new requests while this many won orders due within a day wait for a driver; 0 is off
    "min_slack": 240,  # decline an option whose latest pickup is under this many minutes after we win it; 0 is off (b6: on-time 88->92%)
    "read_notes": True,  # set plates, manual licence and stop windows from the note (b12 vs rc1: 9/9 ranked, +€1.4k over 9 weeks)
    "skip_trade_in": True,  # decline two-car trade-ins: 32% late on rc1 (18 of 54) against 2-7% dealer to dealer
    "skip_private": True,  # decline private pickups and deliveries: 20-23% late for next_day (b11: rc1 8/9 -> 9/9 ranked)
    "gov_tight": 0.05,  # projected late share above which the governor goes tight (plan: budget 5%)
    "gov_rescue": 0.08,  # and above which it goes to rescue (never spend 10%)
    "governor": True,  # risk_mode from the projected late share; tight and rescue make serviceability stricter (b7: 3/3 ranked)
    "max_per_batch": 0,  # decline once we hold this many orders from one batchId (a yard sending many cars); 0 is off
    "orders_per_driver_day": 0.0,  # cap on won orders per last-pickup day, per driver in the world; 0 is off
    "cars_per_driver_day": 0.0,  # cap on cars won per pickup town and ready day, per nearby driver; 0 is off
    "fee_ladder": 0.0,  # lab only: >0 posts every gig at one flat fee, a random multiple of the typical fee in [0.8, 0.8 + fee_ladder]
}
