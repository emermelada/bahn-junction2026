# Bahn Spread — v2 master plan (branch `branch-v2-frank-plan`)

Written Fri 13 Nov 2026 23:20 Helsinki. Final: Sun 15 Nov 08:00 (set 07:30), ~34 real minutes, level 8.
Sources of truth: `docs/RULES.md` > `docs/HANDBOOK.md` > `docs/API.md`. Everything in v2 is isolated from v1.

## 0. TL;DR (read this if nothing else)

- **This is not a prediction task.** It is a real-time dispatch agent: quote dealers against a hidden competitor, then pay freelance drivers to move the cars. Score = gross margin; **under 90% on time = unranked = zero**. Top 10 by margin present; the jury then scores *elegant / clear / creative / robust* with same-seed A/B evidence per idea.
- **Where the money is (from the spread-1 level-8 reveal, 1,037 requests, 832 drivers):** list price wins 92% of requests (competitor is 26–54% above list), so revenue comes from pricing *above* list; cost comes from drivers who are scarce and *unevenly* placed (Helsinki 295 drivers, Hyvinkää 2 drivers but 167 pickups). The starter loses €72k because it wins everything and pays 1.5–2.5× the typical fee for cars nobody nearby can move.
- **The system = 8 small modules, one idea each**, in build order:
  1. **Driver-reach map** (roster + map → drivers within 30/80 km of every place) — the hidden shortage made visible.
  2. **Feasibility gate + pool-day capacity ledger with quote-time reservations** — win only what the drivers near the pickup can move; decline by quoting 3× list.
  3. **Option ladder** — price `within_3_days` ≤ `next_day` < `same_day` so dealers self-select into the option that gives drivers time.
  4. **Flat-then-cliff fees + rescue ladder** — open near the clearing fee, raise early and rarely, never teach drivers to wait; bounded rescue when the warning comes.
  5. **Online competitor interval** — per-lane `[highest won, lowest lost]` price ratio, bisected with free upper probes; guards for the price-war day and the outage region; dealer-trust multiplier.
  6. **On-time governor** — a marginal admission test against a 7% late budget, sticky lateness, GREEN/AMBER/RED.
  7. **Direct offers to drivers only we can see** — our drivers finishing nearby, today's active viewers, homebound drivers; the fix for Hyvinkää-type towns outside every notification radius.
  8. **Bundling + notes** — trade-ins, out-and-back and same-yard pairs under the 12-hour rule; a note reader validated against reveal truth.
- **Validation = same-seed paired A/B on a fixed level-8 seed set**, every module behind a flag, adopt only if all seeds ranked at ≥ 93% on time and n−1 of n seeds improve. Ranking rounds are the held-out test set; the two Saturday test finals are the dress rehearsals.
- **Targets:** ranked on 100% of seeds by Sat 03:00; ≥ €8k/week by the Sat 09:00 round; ≥ €12k/week (House best) by the Sat 21:00 round; final: top 10 at ≥ 95% on time.
- **Blockers for Franco right now:** preliminary submission due **Fri 23:59**; the GitHub repo is not reachable from this account (see §10).

## 1. The game and what the judges reward

| Judging fact (source) | Design consequence |
|---|---|
| Score = sum of the account; < 90% on time → unranked; no wins → unranked (RULES, Score) | On-time is a hard constraint, margin is the objective. Err tight: 90% is binary, margin is linear. |
| Final = one secret level-8 week, own copy per team, clock runs itself (18 s per weekday hour → 4.5 real s per quote) | Quote path must be synchronous and sub-100 ms; state rebuildable from `snapshot` + `events`; one process per key; survive server restarts (502/503/504). |
| Top 10 by margin present; jury: elegant, clear, creative, robust; "measure the effect of each idea on the same weeks" (judging page) | One module per idea, one formula per module, every constant in one config table with its reason, every decision logged with its inputs, every module behind a flag for the ablation table. |
| Level 8: 26–40% of drivers, uneven per town; competitor 26–54% above list; one price-war day (−20%, 08–18); outage day (one region, backup +30%); flu day (30% of drivers home); bulk order (30–40 cars, one yard); dealer trust +1%/on-time order (cap 25), halved by a late order | Capacity, not price, is the binding constraint; the roster is the map of capacity; unannounced days need detectors that can only make us safer, never looser. |
| A quote that loses costs nothing; a request not quoted costs goodwill | Never skip a request. Decline = quote 3× list on every offered option. |
| Drivers learn how far our fees rise and how long gigs stay open (HANDBOOK, Drivers learn your fees) | Fees must be flat-ish and early. Raises are rare and come before the pickup, not after the warning. |
| Direct offers save most on gigs whose fee drivers expect to rise; a driver finishing our gig far from home is reachable only by offer (HANDBOOK, Direct offers) | Offers are the precision tool for towns with no drivers inside the 30 km notification radius. |

## 2. Ground truth from data (spread-1, level 8, starter run; `data/reveal-spread1-L8-starter/`)

Requests and prices:
- 1,037 requests; 219/204/191/244/179 per weekday; 41% carry a note (fi 281, en 124, sv 19). 440 requests sit in 119 batches (max 37 = the bulk order).
- Options offered: 1 option 333 (private delivery / trade-in), 2 options 608, 3 options 96. List price median €64 (p10 €30, p90 €142). `same_day` list = 1.08 × `next_day`; `within_3_days` = 0.93 × `next_day`.
- Typical fee ≈ **€16 + €0.39 per road minute** (residual p10/p90 ±€12). Typical fee / list ≈ 0.88 (same_day), 0.96 (next_day), 1.00 (within_3_days): at list price the margin is ~zero before the shortage; the margin is in pricing above list.
- Starter quoted list on the first option: **won 959 / lost 78** (92.5%). The dealer then took `same_day` 681 times and `next_day` 278 — the starter forced the hardest option on itself.
- Dealers: 40; D01 251 requests, D02–D04 ~120 each → 60% of volume in four dealers (trust and the competitor's per-dealer reaction both concentrate there).

Drivers and geography:
- 832 drivers: Helsinki 295, Tampere 109, Espoo 76, Vantaa 47, Oulu 39, Lahti 34 … Hyvinkää 2, Lempäälä 2, Pori 1, Rauma 0, Kemi 0. Experienced (≥ 4.8 and ≥ 50 gigs): 61 (7%); manual licence 83%.
- Reach inside the 30 km notification radius (straight line): Helsinki/Espoo/Vantaa cluster 418; Tampere+Lempäälä 111; Turku+Raisio 29; every other town is alone. **Hyvinkää: 2 within 30 km, 480 within 80 km** (45 road minutes from Helsinki). Same shape for Porvoo (14 / 475), Hämeenlinna (12 / 159), Lahti (34 / 63).
- Demand vs supply (pickups/deliveries/drivers): Vantaa 188/97/47, Hyvinkää 167/122/2, Helsinki 104/85/295, Lahti 72/54/34, Oulu 69/53/39, Raisio 50/44/5, Lempäälä 41/65/2, Jyväskylä 30/57/11, Kokkola 13/42/21, Kuopio 10/39/23.

Driver behaviour under the starter:
- 1,312 bookings for 959 orders (reposts), booked fee / typical fee p50 **1.50**, p90 2.50; Raisio and Kokkola 2.5, Oulu 2.0, Kuopio 1.1. Minutes from post to booking p50 95, mean 904. Bookings peak 18–20h (168+93+87) and 06–08h: drivers with day jobs plan the next day in the evening.
- 343 drops (p50 660 min after booking), 587 expired gigs, 1,249 deadline warnings, 26 failed visits (11 no plates, 7 not ready, 7 closed, 1 licence), 24 cars never picked up.
- Lateness: same_day 308 on time / 359 late; next_day 129 / 141; late by p50 2,272 min. Ledger: revenue €71,332; driver fees −€118,593; late refunds −€20,301; undelivered −€3,506; failed visits −€1,252.
- Note truth over 971 won legs: needs plates 10, manual 4, summer tyres 7, note deadline 22, released after payment 4, ready later than stated 26. Rare, but each miss is a failed visit plus a likely late order.

Leaderboard (Fri 20:01 round, 5 weeks summed, level 8): Juhus €69,954 / 97.5% (294–433 orders a week); House best €60,449 / 94.2% (198–465); Bob the builders €40,273; Upsala €31,695 but unranked by one week at 87%. So the bar is ~€12–14k per week at 95%+ with 300–400 orders, i.e. ~€35–40 margin per order; and one bad week kills a round.

## 3. Architecture

TypeScript on Node 24, zero dependencies, the kit client (`spread.ts`, `types.ts`) reused unchanged. One file per idea so the jury can follow one formula per module and we can flag each off for the ablation.

```
v2/
  PLAN.md  README.md  docs/  data/            (map.json, reveal CSVs, results.csv for slides)
  cfg/            one JSON per experiment arm; every constant with a one-line reason
  src/
    client/       spread.ts, types.ts (from the kit)
    geo.ts        map, haversine, reach30/reach80 per place, pools (30 km clusters), road minutes
    notes.ts      fi/sv/en note reader → facts {readyFrom, afterPayment, pickupHours, deliveryHours, deadline, plates, manual, summerTyres, unparsed}
    books.ts      Desk state as a pure reducer over DeskEvents (dedupe by seq), rebuild from snapshot+events
    feasibility.ts per request/option: drive, latestArrival, lastPickup, slack hours, tier A/B/C
    capacity.ts   pool-day load ledger with quote-time reservations, bulk-batch single-pass decision, dealer daily share
    governor.ts   late budget, sticky lateness, GREEN/AMBER/RED, calendar guard
    pricing.ts    per-bucket [lo,hi] interval learner, probes, option ladder, trust multiplier, war/outage guards
    quote.ts      the one function: request → QuoteAction (gate → capacity → governor → price)
    fees.ts       flat-then-cliff schedule, rescue ladder, caps from the refund table, night shifting
    offers.ts     direct-offer engine: relay / active viewers / homebound; per-driver quota; driver ledger
    bundles.ts    pairing under the 12-hour rule; trade-in order; fallback to singles
    dispatch.ts   post/repost/retry/withdraw/release; at-risk sweep; triage; straggler policy
    desk.ts       handle(event) and tick(now) → outbox; decision log (JSON lines)
    run-practice.ts  stride loop (quote in the very next advance; max stride 14 min; night skip)
    run-final.ts     stream loop: rejoin → stream → act; watchdog; reconnect; supervisor-friendly exit codes
    bench.ts      batch runner: seeds × config, slot broker, registry, paired A/B table, gate, fork lab, board watch
    analyze.ts    events + reveal → quotes.csv, gigs.csv, orders.csv (per-order P&L reconciled to the score), towns.csv
  runs/           per-run raw events/actions/reveal (gitignored)
```

Decision flow per event (all pure functions over `books` + `cfg`, producing actions into an outbox that is flushed with the next advance in practice and at once in the final):

- `price_request` → `quote.ts`: notes → feasibility per option → capacity reservation → governor admission → price per option (or 3× list). Always one quote per request, sent in the very next advance / act.
- `order_won` → move reservation to committed; `bundles.ts` tries a pair; `fees.ts` schedule; `dispatch.ts` posts; `offers.ts` fires immediately if the pickup pool is thin.
- `order_lost` → release reservation; `pricing.ts` lowers `hi` for that bucket.
- `gig_booked` / `gig_started` / `picked_up` / `delivered` → books; `offers.ts` updates the driver's position and expected end; `governor.ts` on-time counters.
- `gig_dropped` / `no_show` / `gig_expired` / `visit_failed` / `driver_late` / `order_changed` / `order_cancelled` → `dispatch.ts` repost/retry/release rules; `offers.ts` rescue round.
- `deadline_close` and the 30-minute `tick(now)` sweep → `dispatch.ts` triage stages (warm / hot / doomed) with capped fees.
- `ledger` → trust counters, sticky lateness, P&L.
- `forecast` → snow factor on road minutes for those places/hours; summer-tyre cars rescheduled.

## 4. Data pipeline

Sources (all free of hidden information; nothing in the world is "test data" we could leak from):
1. `GET /v1/map` (no key): 30 places with lat/lon, 900 road pairs with km and minutes. Cached in `data/map.json`.
2. `GET /drivers` once per world at start (and on rejoin): home town, rating, licence, completed gigs, drops. This is the only view of the world's capacity draw; everything per-town is normalised by it so a new world needs no retuning.
3. Events (`advance` answers in practice, the stream in the final): every quote outcome, view, booking, drop, delivery and ledger line. Written raw to `runs/<id>/events.jsonl` with the actions and their results.
4. Reveal after a practice world ends: our quotes vs outcome, the truth of each won car (ready time, real hours, note deadline, plates, gearbox, tyres), every view with the fee seen. Exported by `analyze.ts` (extends the kit's `reveal-csv.ts`).
5. Public practice board (`/v1/leaderboards/practice?level=8`): per-run margin, on-time and won orders for every team and House best, on the same five worlds we play.

Preprocessing and standardisation:
- Times are whole minutes from Monday 00:00; money whole cents; the client refuses fractions, so every computed fee/price is `Math.round`ed to whole euros × 100 before it enters an action.
- Per-world normalisation: fees are reasoned as ratios to `referenceFeeCents` (the handbook says it is a typical pickup-town driver's cost times one world-wide factor), prices as ratios to the option's own `listPriceCents`, capacity as cars per roster driver per day. Nothing is an absolute euro constant.
- Missing values: `chargePercent` null → no charging stop; `hours` null → private address → the window is the slot; `note` null → no facts; `batchId` null → not a batch.
- Outliers: a request whose road minutes exceed 600 or whose options are all before `now` is declined; a fee below €1 or above `cfg.maxFeeOverPrice × price` is clamped and logged.
- Event repeats after a server restart are dropped by `seq` (API: "an answer can repeat events"); the reducer is idempotent on seq.
- Leakage prevention (for validation, §7): gate seeds are never revealed or tuned on; exploration seeds are read freely; constants are learned from exploration reveals and from *within-week* events only.
- Decision log: one JSON line per quote and per fee decision with its inputs (tier, loads, lo/hi, trust, fee bucket) so every A/B difference can be traced and the slides can show "how it decides".

## 5. Features (what each decision sees, and why)

Per place (from roster + map, computed once per world):
- `reach30(p)`, `reach80(p)`: roster drivers with home within 30 / 80 km straight line. 30 km is the notification radius (RULES, Drivers); 80 km is the outage-region radius and a practical "can be bought with a fee" radius. `reachExp`, `reachManual` subsets for premium and manual cars.
- `pool(p)`: the set of places within 30 km (Helsinki/Espoo/Vantaa; Tampere/Lempäälä; Turku/Raisio; singletons elsewhere). Capacity is charged per pool, not per place, so a Vantaa car and a Helsinki car compete for the same drivers.

Per request / option:
- `drive` = road minutes pickup→delivery (+40 charging if electric < 30% and > 200 km, +30 plates from the note) × snow factor 1.3 when a forecast covers either end in the window.
- `latestArrival` = min(option deadline, delivery site's closing on the deadline day; private: slot end + 30). `lastPickup` = `latestArrival − drive`, clipped to pickup hours. `slackHours` = driver-visible hours (07–21 Mon–Fri plus stated Saturday hours) between `max(now, readyFrom)` and `lastPickup − 90 min`.
- Flags: private pickup / delivery, trade-in, premium, manual (note), plates (note), summer tyres (note), Friday→Monday crossing, arrival after 15:00, `same_day` only.
- `homebound` = `reach30(delivery) ≥ 40`: a driver can live at the delivery end and needs no expensive trip home (HANDBOOK: the trip home is bought on the day and costs more).
- `batchId` size so far, dealer daily request/win counts, pool-day loads.

Per gig / driver (online):
- Driver ledger: home, rating, drops, licence, offers sent today, fees accepted from us, current position and expected end (sum of road minutes from the last event), viewed-today flag.
- Per fee bucket (by `reach30(pickup)` band × homebound): share of gigs booked at step 1 within 60 min, share reaching the cliff, drops per booking.
- Per price bucket (option kind × pickup pool × delivery pool, with fallbacks): today's `[lo, hi]` ratio interval, counts of wins and losses.

Why these and not more: every feature above is either in the rules verbatim or measured in §2; none needs hidden information; each maps to one sentence a jury can check.

## 6. Decision models (one per module)

Rules and online learners, not offline ML: the world's values are hidden and drawn fresh per world, we have ~30 hours and ~40 weeks of play, and the jury scores clarity. Where something must be learned it is learned *inside the week* from our own wins, losses and bookings, which is exactly what the handbook says a dispatcher does.

### 6.1 Feasibility gate (feasibility.ts)
Tier per option: **A** if `slackHours ≥ 24` and (`reach30(pickup) ≥ 3` or `reach30(delivery) ≥ 10`); **B** if `slackHours ≥ 8` and (`reach30(pickup) ≥ 1` or `reach80(pickup) ≥ 20` or `reach30(delivery) ≥ 3`); else **C**. Downgrade one tier for each of: private pickup slot, trade-in, unparsed note containing digits or a weekday word, Friday ready with Monday deadline. Premium uses `reachExp`; manual uses `reachManual`. `same_day` is A only if `drive ≤ 180`, `slackHours ≥ 4` and `reach30(pickup) ≥ 5`, else C. C is quoted at 3× list. Reason: drivers book only when they can reach every stop in its window (RULES, Gigs); a car far from any driver needs a fee that pays the whole trip (RULES, Drivers).

### 6.2 Capacity ledger with quote-time reservations (capacity.ts)
`load[pool][day]` = Σ pending reservations (weight `pWin` = 0.9 at our prices) + won legs without a booked driver whose planned pickup day is `day`. `cap[pool][day]` = `SAFETY × (ACTIVE × reach30 + ACTIVE80 × (reach80 − reach30))` with priors SAFETY 0.8, ACTIVE 0.5, ACTIVE80 0.1 (Helsinki pool ≈ 170 cars/day, Hyvinkää ≈ 39, Rauma ≈ 0.5). A request is admitted on an option only if `load < cap` on that option's planned day; the reservation is taken when the quote is sent, moved to committed on `order_won`, released on `order_lost` / cancel. All requests in one advance step, and all requests sharing a `batchId`, are decided in one pass sorted by tier and drive minutes (the skeptic panel's consensus fix: capacity counted only on `order_won` is blind to the 15-minute decision lag and to batches). Dealer share: once a dealer's wins today exceed 60% of its requests (≥ 5), quote it +0.08 higher (the competitor cuts prices for dealers where we won most; HANDBOOK, Dealers compare prices). Global cap per day = 0.8 × Σ pools. The planned day for `within_3_days` is the allowed business day with the most free capacity, never Sunday, Saturday only if both sites have Saturday hours.

### 6.3 Option ladder (pricing.ts)
Base ratio `r` from §6.5 for the slowest offered option. Faster options: `next_day` at `r × 1.05`, `same_day` at `r × 1.15` and only if tier A for that option; otherwise that option alone is quoted at 3× list. Reason: the dealer compares each option's price with the value of its speed (HANDBOOK), so a dear fast option and a fair slow option steer it to the slow one, which gives drivers a day or two to plan (bookings peak the evening before). Ablation: ladder off = quote only the first option.

### 6.4 Fees: flat-then-cliff with a bounded rescue (fees.ts)
`F_open = referenceFee × k[band] × extras`, bands by `reach30(pickup)`: 0–2 → 1.35, 3–9 → 1.15, 10–39 → 1.00, 40+ → 0.90; extras ×1.15 evening/Saturday, ×1.15 private stop, ×1.10 per extra leg, ×1.10 premium; ×0.90 if homebound. Schedule: `{now, F_open}`, `{now+60, 1.15 F_open}`, `{lastPickup−300, 1.4 F_open}`, `{lastPickup−180, 1.7 F_open}`; any step inside 23:00–07:00 moves to 07:00; never more steps later. Reposts open at the same fee (a higher repost counts as a raise and the order keeps its age); after a drop +15% once (the dropper only returns for more). Learning, two-sided per band: if ≥ 70% of a band's gigs book at step 1 within 60 min, `k −= 0.05` (floor 0.8); if ≥ 30% reach the cliff or drops per booking > 0.25, `k += 0.05` (cap 1.8). Rescue (dispatch.ts triage): at `lastPickup − 240` offers round; at the warning reprice to `capOnTime = min(0.9 × price, max(1.7 F_open, 1.5 × referenceFee + 0.25 × price))` (+0.25 × price in AMBER/RED or for anchor dealers); once `lastPickup` has passed the car is *doomed*: repost without windows at a calm schedule capped at 1.0 × price, rising to at most 2 × price − €1 only in the last Monday–Wednesday stretch (an undelivered car costs twice the price). Reason: drivers learn booked-fee / first-viewed-fee and wait when fees always rise (HANDBOOK, Drivers learn your fees); after the warning only a higher fee or an offer finds a driver (RULES).

### 6.5 Online competitor interval + guards + trust (pricing.ts)
Bucket = (option kind, pickup pool, delivery pool) → fallback (option kind, pickup pool) → (option kind); use the finest with ≥ 3 decided quotes today. Per bucket per day `lo` = highest ratio (quote / option list) that won, `hi` = lowest that lost. Monday prior `[1.15, 1.40]` (level-8 competitor is 1.26–1.54× list); each morning `lo −= 0.05, hi += 0.05`; if `hi ≤ lo` widen both by 0.03. Quote `r = lo + 0.5 (hi − lo)`, clamped to `[1.05, 1.60]`; every 10th admitted quote in a bucket probes at `r × 1.10` (a lost probe is free). Trust: `r × (1 + 0.01 × trust[dealer])` where trust counts revenue lines without a late refund (cap 25) and halves on a late refund; anchor dealers (top 5 by requests whose pickups sit in pools with `reach30 ≥ 10`) get tier thresholds 0.3 easier and the higher rescue cap. **Price-war guard**: if since 08:00, over ≥ 12 decided quotes across ≥ 4 dealers and ≥ 2 pools, the win rate is < 0.45 × yesterday's for two consecutive 60-minute windows → WAR until 18:00: freeze `lo/hi` updates and move the governor to AMBER; prices are *not* lowered (a chased war day fills the week with thin orders). **Outage guard**: a pool whose win rate exceeds base + 0.30 over ≥ 5 decided quotes while the map-wide rate is normal gets `r += 0.20` (cap 1.60) until 18:00; it only raises prices, so it is on-time safe. A war day and an outage day never coincide (RULES).

### 6.6 On-time governor (governor.ts)
Sticky `late(order)` set once by any of: late refund or undelivered line; `lastPickupAt` passed with no leg picked up; `driver_late.pickupAt + drive > latestArrival` and the driver kept; snow or change moving the plan past the deadline. `atRisk` = unbooked orders with `lastPickup − now < 240`. Admission test for a candidate with on-time probability `p` (by tier: A 0.97, B 0.92, C 0.80): admit iff `(late + 0.5 × atRisk + (1 − p)) / max(won + 1, 30) ≤ 0.07`. Modes with hysteresis: GREEN (headroom > 0.03): tiers A and B; AMBER (0–0.03): tier A only, rescue caps +0.25 × price; RED (≤ 0): only tier A with `slackHours ≥ 48` and `reach30(pickup) ≥ 5`, every unbooked car escalated at once. Calendar guard: from Friday 12:00 tier A only; no `same_day` after 14:00 for pools with `reach30 < 10`. Reason: one late order needs nine on-time ones to keep 90%; the final cannot be replayed.

### 6.7 Direct offers (offers.ts)
Triggers: at post when `reach30(pickup) < 3`; gig open 150 min; `lastPickup − 240`; drop / no-show / expired offer. Candidates ranked by estimated cost from their position: (a) **relay** — our drivers whose current gig ends within 90 road minutes of the pickup before the pickup window ends on the same day; (b) **active** — drivers who viewed one of our gigs today with home within 80 km of the pickup; (c) **homebound** — roster drivers with home within 30 km of the delivery and within 80 km of the pickup. Fee = `min(1.05 × feeEstimate, capOnTime)` with `feeEstimate = referenceFee × cost(position) / cost(pickup-town driver)`, `cost = drive + 0.3 × (road to pickup + road home) + ticket terms` (constants in cfg, fitted from exploration reveals). Quota: ≤ 3 per driver per day, keep 1 per driver for after 12:00; ≤ 3 open per gig; none 22:50–07:00; never to a driver who dropped us today; licence/experience must match. The gig stays in the app meanwhile. Reason: an offer reaches a driver a notification does not, and saves most on gigs drivers expect to rise (HANDBOOK, Direct offers); Hyvinkää, Porvoo, Hämeenlinna have hundreds of drivers 35–60 minutes away and almost none inside 30 km.

### 6.8 Bundles and notes (bundles.ts, notes.ts)
Bundles: pair a newly won leg with one pooled unbooked leg when the whole gig plans ≤ 8 h of driving (12 h is the rule's limit; shorter draws more takers) and every stop is reachable in its window: patterns in order out-and-back (A→B, B'→A with B' within 30 road minutes of B), chain (A→B, B'→C with C a supplied pool), same-yard (P→D1, P→D2 for the bulk order). Trade-in: new car's delivery then old car's pickup, as the rules mandate; split into two gigs if over 12 h. Never bundle a private pickup. Expected saving ≥ 15% of the pair's fees, else post singles. One bundle charges the capacity ledger once.
Notes: regex rule set for fi/sv/en: ready time and day ("klo 11.30 alkaen", "huomenna", weekday names 2–6 days ahead, "half three" = 14:30), after payment ("maksun jälkeen"), pickup/delivery hours ranges, tighter deadline ("perillä … mennessä", "by", "senast"), plates ("ei kilpiä", "no plates", "utan skyltar"), manual ("manuaali", "manuell", "manual"), summer tyres on the car (not "in the trunk"). Output feeds windows, `withPlates`, `audience`, `latestArrival` and the tier downgrade for unparsed notes. Validated against `LegTruth` in exploration reveals (971 won legs already in `data/`).

### 6.9 Robustness (books.ts, run-final.ts)
Pure reducer keyed by `seq`; on start and after every `Unreachable`: `snapshot` + `events(-1)` → rebuild → reconcile (an undelivered leg with no live gig → post; two open gigs for the same leg → withdraw the newer; a pending post the snapshot already shows → drop). Outbox priority: quotes by `respondBy`, releases, reprices/offers for at-risk gigs, posts, rest; flush at once after each event in the final, batches of ≤ 50, under the 20 actions/s bucket. Fallback: if the quote path throws, send 3× list before `respondBy`. Watchdog: stream `idleMs` 1000 → read the clock and run the 30-minute sweep. Exit codes for a supervisor loop; one instance per key; a read-only recorder on the laptop while the desk runs on a VM.

## 7. Validation framework (mirrors the final)

- **Level 8 only** for every scored run. Lower levels only to debug a mechanic in isolation.
- **Seeds**: gate set G = {spread-1, v2-g1, v2-g2, v2-g3, v2-g4} fixed for the weekend, never revealed, never tuned on directly; exploration set E = fresh seeds per idea (v2-e-<idea>-<n>), reveals read freely. The final is one unseen draw, so the floor on G is **93% on every seed**.
- **Step diet**: practice loop advances `untilEvent` = [order_won, order_lost, order_changed, order_cancelled, visit_failed, gig_expired, deadline_close, gig_dropped, no_show, offer_answered, driver_late, release] with `max = min(now + 14, next 07:00 if night/Sunday, next midnight, next sweep tick)`. Every unanswered request is quoted in the very next advance, which applies actions at the current minute, so a quote is always ≤ 14 minutes after arrival (< the 15-minute deadline). Expected ~700–900 steps per week instead of 1,891 (≈ 4–5 min from the laptop; a Stockholm VM should halve that).
- **Runner** (`bench.ts`): `run` (seeds × config, `--slots` parallel on one client, slot broker that leaves `--reserve 2` of the 8 team slots, registry `runs/index.jsonl` keyed by config hash + seed), `determinism` (same config twice = same cents), `ab` (paired table: per-seed Δ margin, Δ on-time, Δ won; sign count; bootstrap 90% CI), `gate` (G: all ranked ≥ 93%, margin ≥ best − 5%, zero exceptions, zero predictable refused actions, ms/step budget), `fork` (short-horizon single-decision tests: 2–3 forks at a minute, same desk, read the whole-world margin delta at the horizon), `board --watch` (ranking board snapshots; per-world comparison with House best and the top 3), `cleanup --mine`.
- **Adoption rule** (written in README and on a slide): adopt arm B over A only if every G seed of B is ranked at ≥ 93%, mean Δ > 0 with ≥ n−1 of n seeds positive, and undelivered share not worse. Ambiguous sign → one more wave of 5 exploration seeds before rejecting.
- **Analytics** (`analyze.ts`): per run `quotes.csv`, `gigs.csv`, `orders.csv` (per-order P&L that must reconcile to `score.marginCents` to the cent or the script fails), `towns.csv`, `steps.csv`; `--all` prints the standard summary (on-time, margin per order, win rate by ratio bucket, booked fee / typical by reach band, minutes to book, late causes). `data/results.csv` accumulates one row per run for the slides.
- **Rehearsal**: a ticker process advances a practice world at the final's pace while the desk runs `run-final.ts` against it over the stream; kill −9 twice and restart; pass = ranked, zero unquoted requests, no duplicate gigs, margin within 5% of the stride run on the same seed (which also measures the practice/final reaction-lag mismatch). Then the Saturday 14:00 and 20:00 test finals with the current best config (the second from the VM under a supervisor). Do not run batches during the test finals (practice limit drops to 20/s).
- **Ranking rounds** are the held-out test set: one gated config per round, five runs in sequence (~5–10 min each), never deleted, compared per world against House best (`wonOrders` tells whether the gap is selection or cost per order).
- **Slot budget** (to agree with teammates): bench 4, forks 1, ranking run 1, teammates 2. Clean up before every batch.

## 8. Roadmap (Helsinki time; ordered; each milestone has a pass metric)

| When | Milestone | Pass metric |
|---|---|---|
| Fri 23:30 – Sat 01:00 | **M0 Harness**: module skeleton, config table, reducer + rejoin, decision log, `bench run/determinism`, `analyze.ts` with P&L reconciliation, `towns.csv` for 3 seeds | starter policy under the new loop reproduces −€72,612.51 / 45.5% on spread-1 (with the kit's step policy) and is deterministic to the cent under the stride policy; steps/week ≤ 1,000; P&L reconciles on 3 runs |
| Sat 01:00 – 03:00 | **M1 Gate + capacity + ladder + governor** (6.1, 6.2, 6.3, 6.6) with starter fees | all 5 G seeds ranked at ≥ 93%; margin > 0 on every seed; unquoted = 0; bulk-batch late share < 10% |
| Sat 03:00 – 05:30 | **M2 Fees + rescue + straggler** (6.4, dispatch triage) | driver fee / revenue ≤ 0.70; deadline warnings halved; undelivered = 0; on-time not worse |
| Sat 05:30 – 08:00 | **M3 Competitor interval + trust** (6.5) | revenue per won order +15% vs M2 at ≤ 20% fewer wins; on-time within 1 pt; mean ≥ €6k/week on G |
| Sat 08:00 – 09:30 | **M4 Robust final loop + rehearsal** (6.9) | kill/restart rehearsal passes; `run-final.ts` ready for 14:00; **09:00 ranking round played with the gated config** (target ≥ €6k/week avg, all 5 ranked) |
| Sat 09:30 – 13:30 | **M5 Offers + notes** (6.7, 6.8 notes) | offer acceptance ≥ 25% for relay/active; bookings in reach-band 0–2 pools up; failed visits ≤ 5/week; margin up on ≥ 4 of 5 seeds |
| Sat 13:30 – 14:30 | **Test final #1** (live clock) | ranked; p95 handle < 300 ms; zero late quotes; no 429 storms |
| Sat 14:30 – 19:30 | **M6 Bundles + war/outage guards + anchor dealers** (6.8 bundles, 6.5 guards); 15:00 and 18:00 rounds | war day flagged within 90 world minutes on each seed with no false positives; bundle fee per car < single; mean ≥ €10k/week on G |
| Sat 19:30 – 20:30 | **Test final #2** on the VM with a deliberate restart | ranked; restart invisible in the log |
| Sat 20:30 – Sun 03:00 | **M7 Tuning sweeps** on E then G: SAFETY, k bands, interval priors, option multipliers; 21:00 and 00:00 rounds | mean ≥ €12k/week on G with min on-time ≥ 93%; freeze at 03:00 |
| Sun 03:00 – 07:35 | **M8 Freeze, gate, deploy, slides**: gate green on G; VM `whoami` shows the final; recorder on laptop; ablation table per idea from `data/results.csv` | desk streaming before 08:00; slides with one idea per slide and same-seed numbers; submission by 10:00 |

Rules for the loop (Phase 2): one component at a time; after every milestone run the G gate and read `analyze --all`; if a milestone fails its metric, fix or flag it off before moving on; update this file when a measurement changes the architecture (keep a dated changelog at the bottom). Up to 3 subagents in parallel for: feature A/Bs on E seeds, note-reader validation against truth, and error analysis of late orders.

## 9. Risks and kill-switches

- **Unranked week** (the only fatal risk): governor RED + calendar guard + the 93% gate floor. Kill-switch: `cfg.tierMax = "A"` turns the desk into "only easy cars".
- **Gate too tight → tiny margin**: visible as won orders < 150 on G; loosen SAFETY/ACTIVE by sweep, never by hand on the final morning.
- **Fee priors wrong**: two-sided learner moves `k` within the day; the rescue ladder bounds the damage; the fork lab settles the shape on 6 orders before Saturday noon.
- **Reaction-lag mismatch practice vs final**: measured by the rehearsal on the same seed; if > 5% margin, shorten the stride to 5 minutes for G runs.
- **Rate limits / server restarts in the final**: the kit client already waits on `RateLimit` headers; the desk rebuilds on `Unreachable`; the supervisor restarts the process; one instance per key.
- **Slot starvation / teammates' worlds**: slot broker reserve; `cleanup --mine` never touches worlds not in our registry.
- **Overfitting G**: G never revealed; E rotates; ranking rounds are the test set.

## 10. Human-in-the-loop action items (Franco)

1. **Now, before Fri 23:59**: preliminary submission on the Junction platform (submission hash from `/team`, link to the repo).
2. **GitHub access**: `https://github.com/emermelada/bahn-junction2026.git` returns "repository not found" for the `FearedLynx` account (`gh auth status` is logged in). Either get added as a collaborator or confirm the URL/visibility. Until then all work is committed locally on `branch-v2-frank-plan` and pushed the moment access works.
3. **Slot budget**: agree with Javier and the other two how many of the 8 practice slots v2 may hold (plan assumes 4 for bench + 1 fork + 1 ranking run). An open level-1 world `w4f0ae1f294a7463b8285` is holding a slot now — whose is it, can it be deleted?
4. **VM near Stockholm** (Hetzner Helsinki or AWS eu-north-1, Node 24, our repo, `.env`): needed for sweeps (the laptop sees ~350 ms per step) and for the final under a supervisor. Alternatively a second laptop on wired internet.
5. **Ask the Bahn booth**: (a) does an accepted direct offer teach viewing drivers the same booked-fee / first-viewed ratio as an app booking? (b) does `lastPickupAt` / `deadline_close` account for a note's tighter deadline or real hours, or only stated hours? (c) is `batchId` the bulk-order marker? (d) is a decline at 3× list in any way different from a lost quote for dealer satisfaction?
6. **Slides owner** (Javier?): 5–10 slides, one idea per slide; the numbers come from `data/results.csv` and the per-idea paired tables the bench prints.
7. **Calendar**: test finals Sat 14:00 and 20:00 (registration pauses 13:45 and 19:45); ranking rounds Sat 00/09/12/15/18/21, Sun 00/03/06; final set Sun 07:30, start 08:00, submissions close 10:00.

## 11. Open questions the first runs must answer

- Booking probability by (slack band, reach band, option) at level 8 — sets the tier thresholds and `p` in the governor. First product of M1's analytics.
- Realistic booked fee / typical fee in reach-band 0–2 towns under flat fees — if it is 1.8–2.5×, far more requests are net negative at 1.25× list and the gate must price them out rather than admit them.
- Steepness of dealer acceptance above the competitor — decides whether the interval is sharp (probes informative) or soft (need win-rate estimates).
- Size of the competitor's per-dealer morning step versus the +1%/order trust gain — decides how hard the dealer-share throttle should bite.
- Whether posting `within_3_days` cars two days early beats the evening before (drivers who "know their week" vs "most only the next day") — one fork test.
- Offer acceptance rates for relay / active / homebound candidates — decides how much capacity the ledger may credit to offers (`ACTIVE80`).
- Does the server parallelise one team's worlds? (ms/step for 1 vs 4 concurrent runs) — decides whether parallel seeds or the step diet is the throughput lever.

## Changelog

- 2026-11-13 23:20 — v1 of this plan from the rules, handbook, API, kit, the spread-1 level-8 reveal and a five-lens strategy panel with adversarial review (panel consensus folded in: quote-time capacity reservations, marginal governor test, two-sided fee learning, war guard that never lowers prices, pool-keyed capacity, offers as the Hyvinkää fix).
