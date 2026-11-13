"""Dealer-side switches. Each idea sits behind one, so harness/sweep.py --flag dealer.<name>=<value> can ablate it."""
FLAGS = {
    "quote_ratio": 1.0,  # price = ratio x list on serviceable requests; 1.0 is the kit starter
    "min_margin_cents": None,  # decline an option whose price minus the cost oracle's fee is below this; None is off
    "trust": False,  # scale prices by the dealer's trust factor (level 8), so wins stay as likely and pay more
    "same_day_extra": 0.0,  # added to the ratio for same_day, so dealers that also accept next_day pick it
    "ladder": 0.0,  # lab only: >0 quotes one random option at a random ratio in [1.0, 1.0 + ladder], to map wins vs price
}
