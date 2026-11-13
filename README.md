# Bahn Spread v2

Read `PLAN.md` first. TypeScript on Node 24, no dependencies. Put `SPREAD_URL` and `SPREAD_KEY` in `.env` at the repo root (never commit it); every script loads it.

- `node src/bench.ts run --cfg cfg/base.json --seeds v2-g1,v2-g2 --slots 4` plays seeds in parallel and writes `runs/<id>/` plus `runs/index.jsonl`
- `node src/bench.ts ab --a cfg/base.json --b cfg/x.json --seeds ...` prints the paired same-seed table
- `node src/bench.ts gate --cfg cfg/base.json` runs the gate seed set and passes or fails
- `node src/analyze.ts runs/<id>` writes CSV tables and a per-order P&L reconciled to the score
- `node src/run-final.ts --cfg cfg/final.json` is the live loop for the test finals and the final

Layout: `src/desk-api.ts` (the contract), `src/config.ts` (every tunable with its reason), one module per idea (see PLAN.md §3).
