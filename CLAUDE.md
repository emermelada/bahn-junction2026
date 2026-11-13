# Spread bot: working agreement

## Mission
Two of us are at Junction 2026 building a bot for the Bahn Express "Spread"
challenge. The bot runs a car transport company for one simulated week in
Finland. It quotes prices to car dealers and pays freelance drivers to move
the cars.

On Sunday at 08:00 Helsinki time the bot plays ONE secret level 8 week, live,
for about 34 minutes. The 10 ranked teams with the highest gross margin
present to a jury. The jury judges how elegant, clear, creative and robust
the system is. A team is ranked only if at least 90% of its won orders
arrive on time.

Priorities, in this order:
1. Always ranked. On-time share never under 90% on any week. Aim for 95%.
2. Never down. Survive a crash, a restart, a slow network, a server restart.
3. Positive margin on every week.
4. Higher margin.
5. A design small enough to explain in five slides.

Scores on practice seeds are not the goal. The final is a week nobody has
seen. A change that raises the average and makes the worst week worse is a
bad change.

The organisers' yardstick, on 20 level 8 weeks: their best system makes
12,551 euros a week and is ranked on all 20. An oracle that sees every
hidden price makes 16,578 and is ranked on only 7, because it wins more
cars than it can move. Driver capacity is the limit, not price knowledge.

## Read first, every session
- docs/vendor/HANDBOOK.md, RULES.md, API.md, openapi.json. Where they
  differ, RULES.md is right.
- docs/PLAN.md, the team plan.
- docs/log/, what we already measured and decided.
Check any belief about how dealers or drivers behave with an experiment
before building on it. If the docs and an experiment disagree, stop and tell
your human.

## Who you work for
Your human tells you at the start whether you work for Person A or Person B.
- Person A owns: src/spreadbot/runtime/, src/spreadbot/dealer/, harness/,
  Makefile, lab/a/, tests/a/.
- Person B owns: src/spreadbot/driver/, src/spreadbot/notes/,
  src/spreadbot/governor.py, lab/b/, tests/b/.
- Frozen for both after tag v0: src/spreadbot/core/ and CLAUDE.md.
Edit only the paths of the person you work for. If you need a change
anywhere else, write it as docs/requests/<a or b>-<short name>.md, tell your
human, and carry on with a workaround inside your own paths. This rule is
what keeps our merges free of conflicts, so hold to it even when a one line
fix elsewhere looks harmless.

## Rules of the code
- Nothing fitted to a seed. Whatever depends on the week (competitor price
  level, clearing fees, towns without drivers) is learned from that week's
  events. Every remaining constant gets a one line comment saying why it has
  that value.
- Deterministic. The same seed and the same code give the same score to the
  cent. Use core/rng.py for randomness. No wall clock time and no unordered
  iteration inside decisions.
- World time comes from events and snapshots, never from the local clock.
- State is built only by folding events (core/state.py). After a restart the
  bot rebuilds from world.snapshot() and world.events() and carries on. Drop
  repeated events by seq.
- Never leave a price request unanswered. To decline, quote far above list.
  If the quote code throws, send the decline quote.
- Fail safe everywhere. Wrap each handler so one bad order cannot stop the
  loop. No data yet means a cautious default, not a crash.
- Every decision writes one line to the decision log with a short reason
  code. We debug with it and we show it to the jury.
- Each idea sits behind a flag in dealer/flags.py or driver/flags.py, so it
  can be switched off for an ablation.
- Standard library plus the spread kit inside src/. Ask before adding a
  dependency. Scripts in harness/ and lab/ may use pandas and matplotlib.
- Small modules, plain functions, type hints. Fewer parts is a judged
  criterion.

## Rules of the server
- SPREAD_KEY lives in .env, which is gitignored. Never print it, log it or
  commit it.
- Only the human starts ranking runs (board=True or --board), test finals
  and the final (--final).
- Never delete a ranking run. It would play to its end without our bot and
  the score would still count.
- Both of us share one key: 8 unfinished practice worlds and one rate
  bucket. Use at most 3 worlds at a time. Record each world you create in
  data/worlds_<a or b>.jsonl, and delete or finish only those.
- Practice calls slow down when many teams play, and drop to 20 a second
  during a test final. Let the kit client wait for tokens. Do not write
  retry loops that hammer the server.

## How to judge a change
- make check: unit tests, determinism test, 3 seed level 8 smoke. Must pass
  before every merge.
- make sweep SET=dev: the 10 fixed DEV seeds. Use freely.
- make compare BASE=<run> NEW=<run>: paired table on the same seeds.
- make ablate FLAG=<name>: the same seeds with one flag on and off.
- make sweep SET=fresh N=20 TAG=<rc>: 20 new seeds. Needed before a release
  tag. Never reuse them.
Report results in this order: ranked rate, minimum on-time share, 10th
percentile margin, median margin, the three worst seeds. Accept a change
only if the ranked rate stays at 100% and the worst weeks do not get worse.
A gain smaller than the spread between seeds is not a gain. If a feature
shows no gain, say so and propose removing it.

## Log for the pitch
After each experiment or decision, add one file
docs/log/<a or b>-<yyyymmdd-hhmm>-<short name>.md with five short parts:
what we saw, the idea, the test (seeds and flags), the numbers with and
without, keep or kill. The jury asks for exactly this, including what did
not work.

## Working style
- Before a large change, write a five line plan and wait for a yes.
- Small commits on a branch named a/<topic> or b/<topic>. Rebase on main
  before merging.
- When you are unsure what a rule means, quote the sentence from docs/vendor
  and ask.
- Say plainly when something failed or when a result is within noise.
