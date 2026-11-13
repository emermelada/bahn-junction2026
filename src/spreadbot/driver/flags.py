"""Driver-side switches. Each idea sits behind one, so harness/sweep.py --flag driver.<name>=<value> can ablate it."""
FLAGS = {
    "fee_open": 1.4,  # opening fee as a multiple of the typical fee; 1.2 booked fewer in time (b5), 1.6 cost more (b3)
    "fee_top": 1.4,  # the schedule rises to this multiple; <= fee_open means one flat fee, which teaches no waiting
    "raise_lead": 0,  # minutes before lastPickupAt at which a still-open gig gets one raise to fee_raise; 0 is off
    "fee_raise": 1.8,  # that one raise, as a multiple of the typical fee
    "min_drivers_near": 0,  # decline pickups with fewer drivers living within 30 km; 0 is off
    "max_backlog": 15,  # decline new requests while this many won orders due within a day wait for a driver; 0 is off
    "min_slack": 240,  # decline an option whose latest pickup is under this many minutes after we win it; 0 is off (b6: on-time 88->92%)
    "governor": False,  # risk_mode from the projected late share; tight and rescue make serviceability stricter
    "cars_per_driver_day": 0.0,  # cap on cars won per pickup town and ready day, per nearby driver; 0 is off
    "fee_ladder": 0.0,  # lab only: >0 posts every gig at one flat fee, a random multiple of the typical fee in [0.8, 0.8 + fee_ladder]
}
