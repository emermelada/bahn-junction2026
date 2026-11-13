# Flat fee and a backlog cap bring on-time share to 88-90%

**What we saw.** With rising fees and no cap (b1), 58-70% of orders were on time. Most late orders had no driver before `lastPickupAt`, and drivers waited for the top of the fee ladder.

**The idea.** Three changes at once, to get near the gate fast: quote 1.4x list (same_day 1.6x, so dealers that accept next_day pick it); post every gig at one flat fee (no raises to wait for); decline new requests while 15 won orders due within a day still have no driver.

**The test.** dev-01..03, level 8.

| Tag | Settings | dev-01 | dev-02 | dev-03 | On time |
|---|---|---|---|---|---|
| b2 | ratio 1.4, flat fee 1.4x, backlog 15 | -€900 (242 orders) | -€5,001 (322) | -€1,518 (408) | 87.6-89.7% |
| b3 | ratio 1.4, flat fee 1.6x, backlog 25 | -€4,839 | -€12,472 (382) | -€10,746 (433) | 82.7-86.4% |

Money on b2 dev-02: revenue €40,154, driver fees €41,741, late refunds €2,586, failed visits €787. Revenue per order about €108-125, driver fee per order about €106-130: the fee eats the price.

**Keep or kill.** Keep the flat fee and the backlog cap (b2). The higher fee and looser cap (b3) lose on both money and on-time share. Next: a margin floor, a cheaper fee, dealer trust and the governor.
