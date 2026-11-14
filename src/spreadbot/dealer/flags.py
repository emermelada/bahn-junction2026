"""Dealer-side switches. Each idea sits behind one, so harness/sweep.py --flag dealer.<name>=<value> can ablate it."""
FLAGS = {
    "quote_ratio": 1.4,  # price = ratio x list; the ladder wins ~40% at 1.4 (docs/log a-...-price-ladder); 1.0 is the kit starter
    "min_margin_cents": 1500,  # decline an option whose price minus the planned fee is below this; None is off (b4 vs b2: +€4-8k)
    "trust_invest": 0.0,  # quote this much lower to big dealers until their trust count is full (25); 0 is off
    "dealer_level": 0.0,  # move the ratio by this share of the dealer's level relative to this week's average; 0 is off
    "week_level": 0.0,  # move the ratio by this share of this week's learned competitor level (week_level.py); 0 is off
    "lane_weight": 0.0,  # add this share of the lane table's shift (dealer/lanes.json) to the ratio; 0 is off
    "max_ratio": 0.0,  # >0: an option under the floor is priced at fee + floor, up to this ratio of list; 0 declines it
    "learn_price": False,  # pick the ratio from the live win model instead of quote_ratio
    "trust": True,  # scale prices by the dealer's trust factor (level 8), so wins stay as likely and pay more (b6)
    "same_day_extra": 0.2,  # added to the ratio for same_day, so dealers that also accept next_day pick it; same_day ran 60% late
    "ladder": 0.0,  # lab only: >0 quotes one random option at a random ratio in [1.0, 1.0 + ladder], to map wins vs price
}
