"""Driver-side switches. Each idea sits behind one, so harness/sweep.py --flag driver.<name>=<value> can ablate it."""
FLAGS = {
    "fee_open": 1.0,  # opening fee as a multiple of the typical fee; 1.0 is the kit starter
    "fee_top": 1.5,  # the schedule rises to this multiple; <= fee_open means one flat fee, which teaches no waiting
    "min_drivers_near": 0,  # decline pickups with fewer drivers living within 30 km; 0 is off
    "max_backlog": 0,  # decline new requests while this many won orders still wait for a driver; 0 is off
    "min_slack": 0,  # decline an option whose latest pickup is less than this many minutes after we would win it; 0 is off
    "governor": False,  # risk_mode from the projected late share; tight and rescue make serviceability stricter
    "cars_per_driver_day": 0.0,  # cap on cars won per pickup town and ready day, per nearby driver; 0 is off
    "fee_ladder": 0.0,  # lab only: >0 posts every gig at one flat fee, a random multiple of the typical fee in [0.8, 0.8 + fee_ladder]
}
