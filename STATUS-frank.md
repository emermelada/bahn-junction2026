# v1 (branch-v1-frank) — status and commands

## Where it stands (Fri 13 Nov, 23:59 Helsinki)
- **Preset `money`** (`--preset money`): on 12 fresh seeds €12.1k/week mean and median (+29% vs rc2), but only 9/12 weeks reach 90% on time.
- **Tag `rc2`** (load_free 0.05) on 12 fresh level 8 seeds (dev-19..30): ranked 12/12, worst on-time 0.935, median €8.9k, mean €9.4k, worst week €5.4k. rc1: 12/12, mean €9.2k.
- Top of the Friday 20:01 board: Juhus ~€14.0k/week, House best ~€12.1k/week (5 runs each).
- Biggest measured gains so far: per-day load pricing (+€1.6k/week, ranked 9→11 of 12), fees anchored to the last pickup time + cheap plan for already-late cars, bundling two chained cars in one gig (+€1.1k/week), the refit on-time model.
- Experiment logs: `docs/log/frank-*.md`. Analysis scripts: `lab/frank/`.

## Commands (from this folder, Git Bash)
```bash
./run_final.sh                                   # test final / final: waits for it, restarts the bot if it exits
```
```bash
PYTHONPATH=src ./.venv/Scripts/python -m spreadbot.run practice --board --level 8 --tag board   # one ranking run (humans only)
```
```bash
./.venv/Scripts/python harness/sweep.py --tag mytest --seeds dev-07..dev-18 --set load_free=0.07   # A/B on 12 seeds
```
```bash
./.venv/Scripts/python harness/sweep.py --report v1p-load mytest                                   # paired table
```
`.env` must hold SPREAD_URL and SPREAD_KEY (it is gitignored; copied from `../kit/typescript/.env`).

## Human to-dos
- Ranking rounds (Sat 09:00, 12:00, 15:00...): play 5 board runs with the command above, one at a time (each ~2–5 min).
- Test final Sat 14:00: start `./run_final.sh` around 13:50 on the machine that will run the final. Watch `data/final-console.log`.
- Only one bot per world. Keep Javier's and my practice sweeps off during test finals (limit drops to 20/s).
