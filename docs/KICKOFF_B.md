You work for Person B. Read CLAUDE.md, docs/PLAN.md and everything in
docs/vendor/ before you answer. Then tell me in ten lines how you understand
the game and the plan, and list anything in the docs that contradicts the
plan.

Your area is the road: getting every won car delivered on time at the lowest
fee. Work through these steps in order. After each step show me the numbers
and wait for my go.

B0. World lab. Target: 90 minutes, while Person A builds the skeleton. Work
in lab/b/ with the kit and its starter. No dependency on our own code.
- Money map, driver map and starter autopsy, as described in docs/PLAN.md.
- A notes corpus: every note with its language and the truth fields of its
  car from the reveal, from finished weeks at levels 5 to 8. Save it as
  data/notes_corpus.jsonl.
- Scripts for the price ladder and the fee ladder that can run unattended
  overnight.
- One file in docs/log/ per finding.

B1. Cost oracle. Do this first once v0 is tagged, because the quote policy
needs it.
- driver/cost.py implements estimate_cost. Serviceable or not, from the
  drivers within 30 km of the first pickup, the slack before the deadline,
  the drive time from the map, and what the car needs (experienced driver,
  manual licence, charging, plates).
- Expected fee from a driver acceptance curve (core/curve.py) on fee divided
  by typical fee, by town and lead time. Start from a cautious prior and
  update it from our own bookings and views during the week.
- p_on_time from slack and local driver supply. Keep it simple and monotone.
- A capacity ledger: cars already won per pickup town and day, against the
  drivers who can serve that town. When a town and day are full,
  serviceable is false. This cap matters more than a precise fee estimate:
  the organisers' oracle knows every price and is still unranked on 13 of
  20 weeks, because it wins more cars than it can move.
- Done when: the cars it declines are the ones that were late or unbooked in
  the baseline runs.

B2. Dispatch.
- driver/dispatch.py builds one gig per order with correct stop windows:
  inside the order window, inside opening hours, inside a private slot,
  after any ready time. A trade-in is one gig with the old car picked up
  right after the new car is delivered, up to 12 hours of driving.
- driver/handling.py sets withPlates, withCharging, the experienced audience
  and the manual licence from the request, the car and the note.
- driver/schedule.py sets the fee schedule: open at the fee the curve says
  will book in time, one early raise if the gig is still open after a set
  share of the slack, nothing that looks like a steady ladder. Check with a
  fork whether rising schedules make drivers wait.
- driver/exceptions.py handles gig_dropped, no_show, driver_late,
  gig_expired, visit_failed, order_changed, order_cancelled and
  deadline_close. Each handler acts in the same step and logs a reason code.
  Our own alarm for an unbooked car must fire long before deadline_close.
- Mind the name clash: the release event says a car can now be collected.
  The release action lets a booked driver go.
- Done when: on the 10 DEV seeds no car is undelivered, and failed visits
  are rare and explained.

B3. Notes reader.
- notes/reader.py turns a note into a small structure: ready time, pickup
  hours, delivery hours, tighter deadline, plates, manual gearbox, summer
  tyres, wait for release. Finnish, Swedish and English. Days are relative
  to the arrival day of the request. A statement that the note corrects or
  denies does not count.
- Rules and patterns only, no network calls at run time. Use your own
  reading of the corpus to write the patterns.
- A scorer that compares the reader with the truth fields in the corpus and
  prints accuracy per field and per language, plus the notes it got wrong.
- When the reader is not sure, it returns the cautious reading: later
  pickup, earlier deadline, stricter driver.
- Done when: the scorer runs on the whole corpus and every miss is either
  fixed or listed.

B4. Governor.
- governor.py implements risk_mode from the projected on-time share: late
  orders so far plus open orders weighted by their risk, over won orders.
- normal, tight and rescue, with thresholds that carry a written reason. In
  rescue, saving a car may cost up to its full price in fees, and only easy
  cars are won.
- A manual switch: a file named RESCUE in the run folder forces rescue mode.
- Done when: on weeks where the baseline drops under 90%, the governor keeps
  the week ranked.

B5. Sharpen. One flag each, each with an ablation file in docs/log/.
- Bundles: two cars in one gig when the second pickup is near the first
  delivery.
- Direct offers: to a driver about to finish one of our gigs near the next
  pickup, and as a rescue to drivers who live near the delivery. Respect 3
  offers per driver per day, 3 open per gig, and no offers from 23:00 to
  07:00.
- Snow: use forecast events to move pickups of summer tyre cars out of the
  snow window and to add slack on affected lanes.
- Bulk batches: use batchId to spot a yard that sends many cars at once, and
  cap how many we take.
