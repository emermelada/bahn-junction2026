"""Driver-side switches. Each idea sits behind one, so harness/sweep.py --flag driver.<name>=<value> can ablate it."""
FLAGS = {
    "fee_open": 1.4,  # opening fee as a multiple of the typical fee; 1.2 booked fewer in time (b5), 1.6 cost more (b3)
    "fee_open_long": 1.0,  # flat fee for a gig posted a day or more before its last pickup; 0 uses fee_open (b15 1.2x, b18 1.0x: median €3.9k -> €6.8k -> €10.5k on rc1)
    "fee_open_mid": 0.0,  # flat fee for a gig posted 8-24 hours before its last pickup; 0 uses fee_open
    "fee_top": 1.4,  # the schedule rises to this multiple; <= fee_open means one flat fee, which teaches no waiting
    "raise_lead": 360,  # minutes before lastPickupAt at which a still-open gig gets one raise to fee_raise; 0 is off (b7)
    "fee_raise": 1.8,  # that one raise, as a multiple of the typical fee
    "min_drivers_near": 0,  # decline pickups with fewer drivers living within 30 km; 0 is off
    "max_backlog": 15,  # decline new requests while this many won orders due within a day wait for a driver; 0 is off
    "min_slack": 240,  # decline an option whose latest pickup is under this many minutes after we win it; 0 is off (b6: on-time 88->92%)
    "read_notes": True,  # set plates, manual licence and stop windows from the note (b12 vs rc1: 9/9 ranked, +€1.4k over 9 weeks)
    "skip_trade_in": True,  # decline two-car trade-ins: 32% late on rc1 (18 of 54) against 2-7% dealer to dealer
    "skip_private": True,  # decline private pickups and deliveries: 20-23% late for next_day (b11: rc1 8/9 -> 9/9 ranked)
    "governor": True,  # risk_mode from the projected late share; tight and rescue make serviceability stricter (b7: 3/3 ranked)
    "cars_per_driver_day": 0.0,  # cap on cars won per pickup town and ready day, per nearby driver; 0 is off
    "fee_ladder": 0.0,  # lab only: >0 posts every gig at one flat fee, a random multiple of the typical fee in [0.8, 0.8 + fee_ladder]
}
