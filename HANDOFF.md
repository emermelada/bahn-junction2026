# Handoff — BahnSpread v2 (branch `branch-v2-frank-plan`)

Written Sat 14 Nov 2026 ~00:30 Helsinki. Final Sun 08:00 (set 07:30). Test finals Sat 14:00 and 20:00. Rounds Sat 09/12/15/18/21, Sun 00/03/06.

## What exists (all committed and pushed)

| Path | State |
|---|---|
| `PLAN.md` | The blueprint: economics, 8 modules with formulas and config constants, validation, roadmap, risks, human action items. Read §0, §6, §7, §8. |
| `docs/` | RULES.md, HANDBOOK.md, API.md, openapi.json copied from the kit (RULES wins on conflicts). |
| `kit/typescript/` | The official starter, untouched (reference for the to-the-cent regression). |
| `data/map.json` | The public map (30 places, 900 roads). |
| `data/reveal-spread1-L8-starter/` | Reveal + roster + gigs of the kit starter's level-8 week on seed `spread-1` (world `w6ee5cfaf99b1467fae68`, ended, free to read again). `events.csv` and `views.csv` are gitignored (large) but on disk. |
| `src/client/` | `spread.ts`, `types.ts` = the kit client, unchanged. |
| `src/desk-api.ts` | The contract: `Desk` (async `rejoin/handle/tick`, `drain/onResults/nextWake`), `DeskContext` (map, roster, endsAt, **`act`** callback, log sink), `WAKE_ON` lists, `StepPolicy`, run artifact formats. |
| `src/config.ts` | `Cfg` with every tunable and a flag per module; `DEFAULT_CFG` = all flags off = kit starter; `loadCfg(path)` deep-merges a JSON; `cfgHash`. `cfg/starter.json`, `cfg/base.json` (all flags on). |
| `src/geo.ts` | `Geo`: road minutes/km, haversine km, `reach30/reach80` (all / experienced / manual) per place, 30 km pools (`poolId`). Verified: Hyvinkää reach30 = 2, reach80 = 480; Helsinki pool = espoo+helsinki+vantaa = 418. |
| `src/desk.ts` | `createDesk(cfg, ctx)` → `V2Desk`: a faithful port of the kit starter (quotes first option at list, rising/steep schedules, retry/repost/raise, rejoin). **Modules are not wired in yet**; `quoted` set added so rejoin never quotes twice. Loads and runs. |
| `src/books.ts` | `Books`: v2 bookkeeping from events (orders with sticky lateness, gigs, drivers' positions / views / offers / drops, dealer-day counts, pool-day seen drivers, trust from ledger, forecasts). Not yet called from `desk.ts`. |
| `src/feasibility.ts` | 6.1: `assess(request, option, now, geo, cfg, noteFacts, snowy)` → tier A/B/C, drive, latestArrival (site closing on the deadline day), lastPickup, slackHours (07–21 Mon–Fri, Sat 09–14). Opening-hours `weekdays` are 0 = Monday (checked in data). |
| `src/capacity.ts` | 6.2: pool-day ledger with quote-time reservations (`reserve/commit/release/free`), `cap()` with the online per-pool availability floor, `planDay()`, dealer-share penalty. |
| `src/governor.ts` | 6.6: marginal admission test, GREEN/AMBER/RED with hysteresis, calendar guard. |
| `src/tools/csv.ts`, `src/tools/import-world.ts` | Left by the analytics agent before it died; untested. |
| `.env` | Local copy of the team key (gitignored). Never commit. |

Not written: `notes.ts` (6.8), `pricing.ts` (6.5), `quote.ts` (the integration), `fees.ts` (6.4), `dispatch.ts` (triage/straggler), `offers.ts` (6.7), `bundles.ts`, `run-practice.ts`, `run-final.ts`, `bench.ts`, `analyze.ts`, `ticker.ts`. The exact specs for each are in PLAN.md §6–§7 and in `PROMPT.md`.

## Decisions already taken (do not re-litigate)

1. Decline = quote `decline.mult` × list on every offered option; never leave a request unquoted.
2. Capacity is reserved at quote time (pending, weight 0.9), committed on `order_won`, released on `order_lost`; batches decided in one pass. Counting only on `order_won` is blind to the 15-minute lag and to batches — the single most repeated finding of the review.
3. The governor is a marginal ratio test with a floored denominator (30), never a stock test (a stock test deadlocks at zero wins).
4. Fees are flat-then-cliff; raises before the pickup, never after; the fee learner is two-sided (share booked at step 1 vs share reaching the cliff), never an EWMA of our own booked/typical ratio (that cannot learn).
5. The price-war guard freezes learning and tightens the gate; it never lowers prices. The outage guard only raises prices.
6. Offers are the fix for towns with no drivers inside 30 km but hundreds within 80 km (Hyvinkää, Porvoo, Hämeenlinna). 21% of the starter's bookings were already natural relays.
7. Practice loop uses a 14-minute stride; every unanswered request is quoted in the very next advance (actions apply at the current minute before the clock moves), so a quote is always inside the 15-minute window.
8. The desk calls `ctx.act` only where the kit's starter calls its own `send()` (trade-in fallback, withdraw); the runner must set the desk clock (`tick(now)`) before handling a stop's events, as the kit does, or the regression will not match to the cent.
9. Gate seeds `spread-1, v2-g1..v2-g4` are never revealed or tuned on; the adoption rule is in PLAN.md §7.

## Numbers to remember

- spread-1 L8, kit starter: −€72,612.51, 45.5% on time, 949 orders (regression target, to the cent).
- 1,037 requests/week; list price wins 92% at level 8; typical fee ≈ €16 + €0.39/road-minute; starter paid 1.5× typical median; bookings peak 18–20h and 06–08h; same_day forced on 681 orders → 359 late.
- Board (Fri 20:01): Juhus €69,954 / 97.5%, House best €60,449 / 94.2%, #2 €40,273. Target set by Franco: **€80k+** per 5-week round = €16k/week.

## Human action items (open)

- Slot budget with teammates (8 shared; an open level-1 world `w4f0ae1f294a7463b8285` holds one).
- VM near Stockholm for sweeps and the final (laptop sees ~350 ms per step).
- Booth questions: does an accepted direct offer teach viewers the booked/first-viewed ratio; does `lastPickupAt` reflect a note's tighter deadline; is `batchId` the bulk-order marker.
- Slides owner; numbers come from `data/results.csv` once the bench exists.

## Loose ends

- The five-lens review workflow's completeness critic never finished (rate limit); its drafts and 100 skeptic verdicts are in the session's workflow journal, already folded into PLAN.md §6.
- `src/tools/*` from the dead analytics agent is untested.
