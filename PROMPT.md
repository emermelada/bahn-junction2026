# Prompt for the build session

Paste everything below the line into a new Claude Code session started in `C:\Users\franc\Desktop\studia\ElysasSecret\Junction\BahnSpread\v2`.

---

You are building our entry for Bahn's "Spread" challenge at Junction 2026 (a real-time car-dispatch agent: quote dealers against a hidden competitor, post gigs with fee schedules to freelance drivers). Workspace: `C:\Users\franc\Desktop\studia\ElysasSecret\Junction\BahnSpread\v2`, git branch `branch-v2-frank-plan` on `https://github.com/emermelada/bahn-junction2026.git`. Never read or use anything under the sibling folder `v1`.

Read in this order, then start coding: `HANDOFF.md` (what exists, decisions taken, numbers), `PLAN.md` §0, §6, §7, §8 (modules with formulas, validation, milestones), `src/desk-api.ts` and `src/config.ts` (the contract and every tunable), `src/desk.ts` (the starter-faithful desk you extend), `kit/typescript/starter.ts` (the official starter the regression test compares against), and `docs/RULES.md` when a rule matters (RULES beats HANDBOOK).

Working rules:
- Build directly. No strategy panels, no parallel agent fan-outs, no plan rewrites. One short status line per step. Spawn an agent only for a clearly separable long job (e.g. the note reader validated against `data/reveal-spread1-L8-starter/legs.csv` truth columns) and at most one at a time.
- Node 24, run TS directly (`node src/x.ts`): `import type`, `.ts` import extensions, no enums, no parameter properties, zero npm dependencies. `.env` at the repo root has `SPREAD_URL`/`SPREAD_KEY`; never print or commit the key.
- The team shares 8 practice-world slots and a slow sequential API (~350 ms/step from the laptop, ~11 min per level-8 week; a 14-minute stride loop should cut it to ~5 min). Use at most 4 slots, delete any world you create that did not end, never create ranking runs (`board: true`) until a config passes the gate, never delete worlds you did not create.
- Commit small and often on `branch-v2-frank-plan` as Franciszek Kossut; no Claude co-author lines. Push after each milestone.
- Every change is measured: same seeds, both arms, PLAN.md §7 adoption rule (all gate seeds ranked at ≥ 93% on time, mean Δ > 0, n−1 of n seeds positive). Append every run to `data/results.csv`.

Target: ranked (≥ 90% on time) on 100% of seeds, then margin. Franco's target is **€80k+ summed over a 5-week level-8 ranking round (€16k/week)**; the board leader averages €14k/week with a best week of €20.8k; House best €12k/week.

Milestones, in order, each with its pass metric (details in PLAN.md §8):

1. **M0 harness** — `src/run-practice.ts` (stride and starter loops per desk-api.ts; set the desk clock with `tick(now)` before handling a stop's events; actions travel with the next advance; `ctx.act` wired to `world.act`), `src/bench.ts` (`run --cfg --seeds --slots --policy --tag`, `determinism`, `worlds`, `cleanup --mine`, later `ab` and `gate`), run artifacts per `src/desk-api.ts`, `runs/index.jsonl`, `data/results.csv`. Pass: `cfg/starter.json` with the starter policy on seed `spread-1` level 8 reproduces **−€72,612.51 / 45.5% on time** to the cent; the stride policy is deterministic to the cent across two runs; steps per week ≤ 1,000.
2. **M1 gate + capacity + ladder + governor** — write `src/quote.ts` combining `feasibility.ts` → `capacity.ts` → `governor.ts` → price (list price for now; ladder multipliers from `cfg.pricing.optionMult` on the slowest option's ratio 1.0; tier C and non-admitted options at `decline.mult` × list), wire `Books.track(event)` and the modules into `desk.ts` behind `cfg.flags`. Pass: all of `spread-1, v2-g1..v2-g4` ranked at ≥ 93%, margin > 0 on each, zero unquoted requests.
3. **M2 fees + rescue + straggler** — `src/fees.ts` (flat-then-cliff, bands by reach30, night shifting, two-sided learner) and `src/dispatch.ts` (30-minute sweep: warm/hot/doomed stages with the caps in PLAN.md §6.4; never end the world with an undelivered car). Pass: driver fee / revenue ≤ 0.70, deadline warnings halved, undelivered = 0, on-time not worse.
4. **M3 pricing** — `src/pricing.ts` (per-bucket `[lo, hi]` ratio interval with free upper probes, Monday prior [1.15, 1.40], morning widening, trust multiplier, dealer-share penalty, war/outage guards). Pass: revenue per won order +15% at ≤ 20% fewer wins, on-time within 1 pt, mean ≥ €6k/week on the gate seeds. Play the Sat 09:00 ranking round with this.
5. **M4 final loop** — `src/run-final.ts` (rejoin from snapshot+events → stream → act at once; reconnect on Unreachable; supervisor-friendly exit codes) and `src/ticker.ts` for a kill-and-restart rehearsal on a practice world. Pass: rehearsal survives two `kill -9` restarts with no unquoted request and no duplicate gigs. Must be ready for the Sat 14:00 test final.
6. **M5 offers + notes** — `src/offers.ts` (relay / active / homebound candidates, fee from the position-cost ratio, 3 per driver per day with 1 reserved for after 12:00, none 22:50–07:00) and `src/notes.ts` (fi/sv/en facts validated against reveal truth; unparsed notes downgrade the tier). Pass: offer acceptance ≥ 25%, failed visits ≤ 5/week, margin up on ≥ 4 of 5 seeds.
7. **M6 bundles + guards + anchor dealers; M7 tuning sweeps; M8 freeze Sun 03:00, VM deploy, slides** — per PLAN.md §8.

Start now with M0. First command: inspect `src/desk.ts` and `kit/typescript/starter.ts` side by side, then write `src/run-practice.ts`.
