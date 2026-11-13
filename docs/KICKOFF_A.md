You work for Person A. Read CLAUDE.md, docs/PLAN.md and everything in
docs/vendor/ before you answer. Then tell me in ten lines how you understand
the game and the plan, and list anything in the docs that contradicts the
plan.

Your area is the desk: the runtime, the dealer side and the test harness.
Work through these steps in order. After each step run make check, show me
the numbers and wait for my go.

A0. Skeleton. Target: 90 minutes, then tag v0.
- Repo layout from docs/PLAN.md. Makefile, .env.example, .gitignore, one
  formatter config.
- core/state.py: one State object built by folding events. Use the kit's
  types where they exist.
- core/interfaces.py exactly as in docs/PLAN.md, plus simple stubs for all
  four functions.
- core/curve.py: the acceptance curve. It takes observations (ratio, yes or
  no, world minute), keeps a monotone estimate of the chance of a yes at any
  ratio, lets old observations fade, and starts from a prior given by the
  caller. Under 150 lines, with unit tests.
- core/rng.py and core/declog.py.
- runtime/practice_runner.py: plays one full week with advance, calls quote
  and dispatch, and writes data/runs/<run id>/ with score, events and
  decision log.
- Done when: one command plays a full level 8 week with the stubs, a replay
  of the saved events rebuilds the same state, and the same seed twice gives
  the same score.

A1. Harness.
- make sweep, compare and ablate as described in CLAUDE.md. A world registry
  in data/worlds_a.jsonl. One JSON result file per run.
- A summary table: ranked rate, minimum on-time share, 10th percentile and
  median margin, the worst three seeds.
- Done when: the 10 DEV seeds run with one command and the table prints.

A2. Baseline quote, then the real one.
- Baseline: one ratio above list for serviceable requests, decline the rest.
  It may use a fixed number. It exists only to get ranked.
- Real policy: a trust count per dealer from our own deliveries, as RULES.md
  describes it. A dealer acceptance curve on price divided by list price and
  by the trust factor, with its prior taken from the level 8 range in
  RULES.md. For each option choose the price that maximises the chance of
  winning times (price minus CostEstimate.fee_cents minus a risk charge from
  p_on_time). Decline when no price is positive, when serviceable is false,
  or when risk_mode says so.
- When the curve is unsure, lean to the higher price, because a lost quote
  costs nothing.
- Check with the price ladder experiment that the curve recovers the win
  rate it was fed.
- Done when: it beats the baseline on DEV and on 20 fresh seeds, with a
  ranked rate of 100%.

A3. Live runner. Must be ready before Saturday 14:00 Helsinki time.
- runtime/live_runner.py: joins with client.final(), follows world.stream(),
  reconnects from the last seq, and reads world.snapshot() about once a
  second as a heartbeat and as the source of world time.
- Our own token bucket for the final limits (20 actions a second with a
  burst of 50, 50 reads a second). Quotes go first, then rescues, then
  posts, then reprices.
- Recovery: on start, and after any 502, 503, 504 or timeout, rebuild from
  snapshot and events before acting again. Never resend an action without
  reading the world first.
- A supervisor script that restarts the bot when it exits.
- harness/emulate.py: a practice week advanced one world minute every 0.3
  seconds by a ticker, while the bot runs in live mode. First check that a
  practice stream delivers events while another call advances the world,
  and tell me if it does not.
- harness/chaos.py: kill and restart, 30 second freeze, dropped stream,
  added latency, injected 429 and 502.
- Done when: an emulated week ends ranked after a kill and restart, with no
  gig posted twice.

A4. Sharpen. One flag each, each with an ablation file in docs/log/.
- Reaction delay: results with actions delayed by 3 and by 10 world minutes.
- Price war and outage: notice a sudden shift in wins and losses, adapt,
  and recover when it ends.
- Spread wins across dealers, if the data shows the competitor undercutting
  us where we win most.
- Option steering: price the slow options to win when the fast one is risky.

A5. Numbers for the pitch.
- The ablation table: each idea on and off on the same 20 fresh weeks, with
  margin and on-time share.
- A chart of margin per seed for the final tag, and a list of what would
  break the system.
