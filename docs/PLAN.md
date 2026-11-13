# Spread (Bahn Express) game plan: Junction 2026

Nov 13, 2026 · @emer

## Read this first

The goal is a top 10 place on one secret level 8 week, then winning the pitch. Once you are in the top 10, margin stops counting and the jury decides.

- **The gate is on-time delivery.** A team with under 90% of won orders on time is not ranked at all. The kit starter is unranked at level 8 and loses €72,612.51 on seed `spread-1`.
- **Priorities, in order:** always ranked, never crash, positive margin every week, then more margin.
- **Your real bar is on the board.** After each round, look at level 8: how many teams are ranked, and the margin of 10th place.
- **The system in one line:** learn what dealers accept and what drivers accept during the week, with one estimator, and only win cars whose spread is positive and safe to deliver.
- **Nothing is tuned to practice seeds.** Every number that depends on the week is learned live from that week's events.
- **Two people:** A owns the dealer side, the runtime and the test harness. B owns the driver side, the notes reader and the on-time governor. Four functions cross the line.

**What good looks like.** The organisers played three systems on the same 20 weeks at level 8.

| System | Margin a week | Weeks ranked |
| --- | --- | --- |
| House starter, the kit starter unchanged | −€67,177 | 0 of 20 |
| House best, the organisers' best system | €12,551 | 20 of 20 |
| The oracle, which reads every driver's cost and the competitor's prices | €16,578 | 7 of 20 |

House best is the line to beat, and it plays every ranking round. The oracle earns the most and still fails the gate on 13 weeks, because it wins more cars than it can move. The limit is driver capacity, not price knowledge. Source: [challenge page](https://spread.bahnexpress.com/).

Margins per car are thin. At level 6 House best makes €8,404 a week, and the page shows one such week with 524 cars delivered: roughly €16 a car. One undelivered car costs twice its price, so it erases many good ones.

All times are Helsinki time, one hour ahead of Spain and Denmark.

| When | What |
| --- | --- |
| Fri 23:59 | Preliminary submission due on the Junction platform |
| Fri 19:30, then Sat 00:00, 09:00, 12:00, 15:00, 18:00, 21:00 | Ranking rounds open. Practice only, they do not count for the final |
| Sat 14:00 and 20:00 | Test finals with the live clock, about 19 minutes each |
| Sun 00:00, 03:00, 06:00 | Last three ranking rounds |
| Sun 07:30 | Registration closes and the final is set |
| Sun 08:00 | Final starts and runs by itself for about 34 minutes |
| Sun 10:00 | Final submission closes: submission hash, code link, 5 to 10 slides or a short video |
| Sun 10:30 to 14:00 | Jury meets the top 10 |

Source for the schedule: [judging page](https://spread.bahnexpress.com/judging). Junction's own schedule wins if the times differ.

## The game in one page

At level 8 the scarce thing is drivers, not orders: there are more cars than drivers can move, so the job is choosing which cars to win. These are the rules that drive every decision.

| Topic | Rule | What we do with it |
| --- | --- | --- |
| Score | Gross margin: dealer payments minus driver pay, refunds, fines and other costs | Optimise the spread per car, not the number of cars |
| Ranking gate | At least 90% of won orders on time. An order is on time when every car arrives by its deadline. Cancelled orders are not counted | Treat lateness as a budget. Plan for 5%, never spend 10% |
| Requests | About 1,000 a week, Monday 08:00 to Friday 18:00. Answer within 15 world minutes, which is 4.5 real seconds in the final | Always answer, and answer fast |
| Options | Up to three per request: `same_day`, `next_day`, `within_3_days`, each with a deadline and a list price. You quote one price per option | Price the slow options to win and the risky ones high |
| Declining | A quote far above list is free. Sending no quote costs dealer goodwill | Decline by quoting high. Never leave a request unanswered |
| Competitor | At level 8 it sits 26% to 54% above list. Prices vary by lane and day. It cuts prices for a dealer when you win most of that dealer's orders | You never see its prices. Learn them from wins and losses during the week |
| Price war | On one unannounced working day the competitor quotes 20% lower, 08:00 to 18:00 | Detect the sudden run of losses. Do not chase below cost |
| Outage | On one working day the competitor is down in one region. Dealers there use a backup about 30% dearer | Probe upward. Wins at high prices reveal the outage |
| Dealer trust | Each on-time order raises the price that dealer accepts by 1%, up to 25 orders. One late order halves the count | Reliability is revenue. Track the count per dealer exactly |
| Drivers | A fraction of the normal supply, and some towns lose nearly all of them. A driver is notified when the first pickup is within 30 km of home | Build a map of where drivers are. Decline cars from empty towns |
| Driver cost | Road time, the trip to the pickup, the trip home by public transport. Evenings, weekends, private addresses and nights away cost more | A car ending near a driver's home is cheap. Estimate cost per lane |
| Fee schedule | 1 to 48 steps, never decreasing. Drivers learn your raise pattern and wait. Most views come in the first minutes. A high fee just before pickup finds nobody | Open near the clearing fee. Raise early and rarely |
| Extra tools | Multi-car gigs up to 12 hours of driving. Direct offers: one driver, 10 minutes, 3 per driver per day, 3 open per gig, unread from 23:00 to 07:00 | Chain cars for a driver already nearby. Keep offers for rescues |
| Late costs | Refund of 10% up to 2 hours late, 25% up to 24 hours, 50% up to two business days, 100% after that. Undelivered at the end: no price plus a penalty of twice the price | Never abandon a car. Paying a high fee beats a penalty |
| Car rules | Premium needs an experienced driver or a €150 fine. An electric car under 30% charge on a route over 200 km needs `withCharging` or it is 90 minutes late plus €100. Plates need `withPlates`. A manual car needs a manual licence | Set these flags from the request and the note, every time |
| Notes | Finnish, Swedish or English, with typos and corrections. They change ready times, opening hours, deadlines, plates, gearbox, tyres. The world applies them whether you read them or not | A wrong read is a failed visit, a fee of at least €25, and often a late car |
| Surprises | Dealers move or cancel won cars. Snow slows drives and blocks summer-tyre cars. Flu keeps 30% of working drivers home for a day. A dealer group can send 30 to 40 cars from one yard | Keep slack. React to every warning event at once |

Sources: [rules](https://spread.bahnexpress.com/kit/RULES.md), [handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md), [how the world works](https://spread.bahnexpress.com/how). Where they differ, the rules are right.

## Reliability first: built for weeks we have not seen

The final is one week nobody has seen, so every change is judged by its worst weeks on fresh seeds, never by its best score on familiar ones. One week is noisy and the 90% gate is a cliff: one bad run of late cars and the team is unranked, whatever the margin.

1. **No number is fitted to a seed.** The competitor's price level, the clearing fees and the empty towns change every week. The bot learns them from that week's events. Starting guesses come from the published rules, such as the 26% to 54% range.
2. **Every constant has a written reason.** If you cannot say why a number is what it is, it becomes a learned value or it goes.
3. **Two seed sets and one outside exam.** See the table below. Seeds are free text, so a new seed is an unseen week on demand.
4. **Report the bad end.** Metrics in this order: ranked rate, minimum on-time share, 10th percentile margin, median margin. A change that lifts the median and hurts the worst weeks is rejected.
5. **Compare on the same weeks.** Practice worlds are deterministic: same seed, level and actions give the same score. Old and new code on one seed differ only by the change.
6. **Robustness is part of done.** Every release candidate survives a kill and restart mid-week, a reaction delay of 3 and of 10 world minutes, and a burst of 429 answers.
7. **Every part fails safe.** Quote path throws: send the decline quote. Fee model has no data: use a generous default. Note cannot be parsed: take the cautious reading.
8. **Cut what does not pay.** A feature with no measured gain on fresh seeds is removed. Fewer parts is safer, and the jury scores it.

| Set | Seeds | Used for | Rule |
| --- | --- | --- | --- |
| DEV | 10 fixed, `dev-01` to `dev-10`, level 8 | Daily work and debugging | Look at anything. Expect to overfit these a little |
| FRESH | 20 new per release candidate, `rc3-01` to `rc3-20` | Deciding whether a candidate is better than the last tag | Run old tag and new candidate on the same 20. Never reuse them |
| Ranking round | 5 secret weeks per level, set by the organisers | The outside exam, and the comparison with the house best system | Play from a tagged commit at milestones. No reveal, so nothing to tune on |

**Targets for the final tag:** ranked on 20 of 20 fresh weeks, minimum on-time share of 93% or more, positive margin on every week, and a median margin within reach of House best's €12,551.

A level 8 week is about 1,900 requests. That takes about 2 seconds on a quiet server, 11 seconds with 60 teams practising and 38 seconds with 200, so 20 seeds twice is a few minutes. Source: [API reference](https://spread.bahnexpress.com/kit/API.md).

## The system: one loop, two markets, one estimator

The bot is one loop: events come in, the state updates, two policies decide, actions go out. The same code plays practice weeks and the live final.

**The core idea.** Spread is two markets with hidden reservation prices. A dealer says yes when your price is under what it would pay elsewhere. A driver says yes when your fee is over what the trip costs them. You only ever see yes or no, so one small estimator learns both curves during the week. The bot takes a car only when the gap between the two is positive after risk.

```text
Spread server (practice: we call advance; final: live stream, 4.5 s per request)
   | events                                               ^ actions
   v                                                      |
Dealer side (A)        Shared core (frozen)        Driver side (B)
 Quote policy    <---   State (event fold)   --->   Cost oracle
 Runners/harness        Acceptance curve            Dispatch and notes
                                                    On-time governor
   | quotes      <-- cost, capacity, risk mode --       | gigs, fees, offers
   v                                                    v
          Action queue: rate limited, quotes first
```

Events fold into one state. Both sides read it and share one acceptance curve. The driver side tells the dealer side what a car costs, how risky it is and whether there is capacity left.

| Part | What it does | Why it exists | Owner |
| --- | --- | --- | --- |
| Event log and state | Folds every event into one state object. A restart replays the log | Restart safe. The same state code runs in practice, replay and live | A |
| Acceptance curve | Learns the chance of a yes as a function of a price ratio, from yes or no outcomes, with old data fading | Used twice: dealers on price over list, drivers on fee over typical fee | A builds, both use |
| Quote policy | Per option, picks the price with the best expected margin: chance of winning times price minus cost minus risk. Declines when nothing is positive | Turns the two curves into a price | A |
| Cost oracle | For a request: expected driver cost, chance of on-time delivery, and whether it is serviceable at all, given the cars already won in that town and day | The one link between the two sides | B |
| Dispatch policy | Builds gigs with the right windows, flags and audience. Sets the fee schedule. Bundles cars, sends direct offers, handles drops, no-shows, late drivers and changes | Gets won cars delivered on time at the lowest fee | B |
| Notes reader | Turns a note into structured constraints. Scored against the truth in the reveal. Unknown text gets the cautious reading | A misread note is a failed visit | B |
| On-time governor | Tracks the projected on-time share and sets a mode: normal, tight or rescue | The 90% gate is a cliff, so it gets its own guard | B |
| Runners | Practice runner on `advance`. Live runner on the stream, with a snapshot heartbeat, a rate limiter and recovery | Same decisions, two clocks | A |
| Harness | Seed sweeps, paired comparison, ablation by flag, live-clock emulator, chaos tests | Proof for you and numbers for the pitch | A |

**How the four decisions work.** Each one is a hypothesis until its ablation shows a gain on fresh seeds.

- **Quote.** The curve works on price divided by list price and by the dealer's trust factor. Trust is 1% per on-time order for that dealer, as the rules state, so the curve only has to learn the competitor. When unsure, price high: a lost quote costs nothing and drivers are the scarce resource.
- **Fee.** Open at the fee the driver curve says will book in time for that town and lead time. One early raise if it is still open after a set share of the slack. Direct offers as the last step. No steady ladder of small raises, because drivers learn to wait for them.
- **Serviceability.** Count drivers whose home is within 30 km of the pickup, from the roster and the map. Correct it with the views seen this week. No drivers nearby and little slack: decline. Also count the cars already won per town and day, and stop winning there once the local drivers are fully used.
- **Governor.** Normal: act on expected margin. Tight: decline risky cars and open fees higher. Rescue: pay whatever a late car needs, and win only easy cars so on-time orders dilute the late ones.

**Repo layout.** Ownership follows folders, which is what keeps merges clean.

```text
spread-bot/
  CLAUDE.md               shared agent rules (frozen)
  Makefile                check, sweep, compare, ablate, emulate, docs
  .env.example            SPREAD_URL, SPREAD_KEY (the real .env is gitignored)
  docs/
    PLAN.md               this plan, exported
    vendor/               HANDBOOK.md, RULES.md, API.md, openapi.json
    log/                  one file per experiment, prefixed a- or b-
    requests/             change requests across the ownership line
    pitch/                slides, figures, numbers
  src/spreadbot/
    core/                 FROZEN after tag v0
      state.py            event fold
      interfaces.py       the four functions that cross the line
      curve.py            acceptance curve
      rng.py, declog.py   seeded randomness, decision log
    runtime/              A: practice_runner, live_runner, ratelimit, recovery
    dealer/               A: quote, win_model, trust, flags
    driver/               B: cost, dispatch, schedule, bundles, offers,
                             exceptions, handling, flags
    notes/                B: reader, corpus tests
    governor.py           B
  harness/                A: sweep, compare, ablate, emulate, chaos
  lab/a/  lab/b/          throwaway analysis, one folder each
  tests/a/  tests/b/      one folder each
  data/                   gitignored: runs, reveals, world registry
```

## Split in two: who owns what

A owns the dealer side plus the runtime and harness. B owns the driver side, the notes reader and the governor. Only four functions cross the line, and they are frozen after the first two hours.

|  | Person A: the desk | Person B: the road |
| --- | --- | --- |
| Mission | Win the right cars at the right price, and keep the bot running | Deliver every won car on time at the lowest fee |
| Folders | `runtime/`, `dealer/`, `harness/`, `lab/a/`, `tests/a/` | `driver/`, `notes/`, `governor.py`, `lab/b/`, `tests/b/` |
| First two hours | Skeleton: repo, state fold, practice runner, stubs, `make check`, tag `v0` | World lab with the kit starter: reveals to CSV, driver map, notes corpus, fee and booking data |
| Then, in order | Sweep and compare harness. Win model and quote policy. Live runner, emulator and chaos tests before Saturday 14:00 | Cost oracle first, because A's quoting needs it. Dispatch and exceptions. Notes reader. Governor. Bundles and offers |
| Pitch | Owns the numbers: ablation table, robustness charts | Owns the story: slides, script, what did not work |

Whoever is more comfortable with git and plumbing should take A.

**The contract.** This file is the whole interface between you.

```python
# src/spreadbot/core/interfaces.py   (frozen after tag v0)

@dataclass(frozen=True)
class CostEstimate:
    fee_cents: int       # expected total driver cost for this option
    p_on_time: float     # chance that every car arrives by its deadline
    serviceable: bool    # False means decline at any price

# B implements, A calls
def estimate_cost(request, option, state) -> CostEstimate: ...
def risk_mode(state, now) -> str: ...            # "normal" | "tight" | "rescue"
def dispatch(state, now) -> list[Action]: ...    # post, reprice, offer, withdraw, release

# A implements, the runner calls
def quote(request, state) -> dict[str, int]: ...  # option kind -> price in cents
```

Both sides ship a simple stub at `v0`, so nobody waits for the other. Each side also keeps its own trackers, fed by the same events, so neither needs to edit `core/state.py`.

**Merge rules.**

1. `main` always plays a full week. Work on short branches named `a/...` and `b/...`. Rebase and merge every hour or two.
2. Edit only your own folders. Need a change on the other side? Write it in `docs/requests/` and say it out loud. The owner makes the change.
3. `core/` and `CLAUDE.md` change only when both agree, in one tiny commit that both pull at once.
4. No shared files that grow. Logs, results and experiments are one new file each, prefixed `a-` or `b-`.
5. Flags live in `dealer/flags.py` and `driver/flags.py`. There is no shared config file to fight over.
6. One formatter, set up in the skeleton. Never reformat a file you do not own.
7. Standard library only in `src/`. A new dependency needs both of you to agree.
8. The merge gate is `make check`: unit tests, the determinism test, and a 3 seed level 8 smoke that must stay ranked.
9. Only tagged commits play ranking rounds, test finals and the final.

**Sharing one team key.**

- The key allows 8 unfinished practice worlds and one rate bucket for both of you. Take 3 slots each and keep 2 for ranking runs.
- Record every world you create in `data/worlds_a.jsonl` or `data/worlds_b.jsonl`. Delete only your own.
- Never delete a ranking run. It then plays to its end without your bot, and that score counts.
- One person plays each ranking round, from a tag. Take turns.
- During a test final the practice limit drops to 20 requests a second. Plan big sweeps away from Saturday 14:00 and 20:00.

## Setup and configuration

Use the Python kit, one shared team key in a gitignored `.env`, and local copies of the organisers' documents for the agent to read. The Python kit needs no other packages and makes the reveal analysis easy. Take the TypeScript kit only if you both prefer it, and do not mix the two.

1. **Team and key.** Create the team at [spread.bahnexpress.com/join](https://spread.bahnexpress.com/join) with event code `spread-kmu9z6`. You both use the same key. The team page shows your submission hash.
2. **Repo.** One private Git repo with both of you as collaborators. The code link goes to the jury, so the key must never be committed.
3. **Environment.** Keep the key in `.env` and commit only `.env.example`.

```sh
# .env  (gitignored)
export SPREAD_URL=https://spread.bahnexpress.com
export SPREAD_KEY=<your team key>
```

4. **Kit.** Python 3.9 or later.

```sh
python3 -m venv .venv
. .venv/bin/activate
. ./.env
pip install $SPREAD_URL/kit/spread-0.1.0-py3-none-any.whl
spread-starter                          # plays one level 8 practice week
spread-starter --level 3 --seed dev-01  # same seed, same world
```

5. **Local docs for the agent.** These are served without a key. Refresh them on Saturday morning in case they changed.

```sh
mkdir -p docs/vendor
for f in HANDBOOK.md RULES.md API.md; do
  curl -fsS -o docs/vendor/$f $SPREAD_URL/kit/$f
done
curl -fsS -o docs/vendor/openapi.json $SPREAD_URL/openapi.json
curl -fsS -o docs/vendor/llms.txt $SPREAD_URL/llms.txt
```

6. **Starter as reference.** Copy the kit starter and read it. It already rebuilds its state after a restart and joins the final with `--final`.

```sh
mkdir -p lab
cp "$(python -c 'import spread.starter as s; print(s.__file__)')" lab/starter_reference.py
```

7. **Opus 5.5.** Put the shared brief from this plan in `CLAUDE.md` at the repo root, and export this plan as Markdown to `docs/PLAN.md`. Claude Code reads `CLAUDE.md` by itself. In any other tool, paste it as the first message.
8. **One session each.** Each of you runs your own Opus 5.5 session, in your own clone, on your own branch, started with your kickoff prompt. When a session gets long, start a fresh one: the brief, the plan and `docs/log/` carry the context.
9. **Humans keep three commands.** Only you start ranking runs (`--board`), test finals and the final (`--final`). The agent runs everything else.
10. **Where the final runs.** Decide by Saturday 20:00 and rehearse it in the second test final. A small cloud server with a laptop on standby beats venue wifi. A restart is safe, because the bot rejoins the same week. Two bots on the same week are not safe, because both would post gigs.

Source for the commands: [handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md).

## Testing with their API and data

Practice weeks are deterministic and free, so the loop is: play many seeds, read the reveal, compare on the same weeks, then confirm on fresh seeds and a ranking round.

| Tool | Kit call | Use it for | Limits |
| --- | --- | --- | --- |
| Practice week | `client.create(level=8, seed="dev-01")`, then `world.advance(until=[...], max=..., actions=[...])` | Everything. The clock moves only when you call `advance` | 8 unfinished worlds per team |
| Snapshot and events | `world.snapshot()`, `world.events(after=seq)` | Rebuilding state after a restart | Events can repeat after a server restart. Drop repeats by `seq` |
| Roster and map | `world.roster()`, `client.map()` | Driver home towns, rating, licence, past drops. 30 towns with road km and minutes | The roster can be 5 seconds stale. The map costs nothing |
| Reveal | `world.reveal()` or `spread-reveal-csv <world id>` | Your quotes and outcomes, the truth of each won car, every view of your gigs with the fee the driver saw | Only after the week ends. Never competitor prices or driver costs |
| Requests only | `spread-reveal-csv --seed study-1` | A week's requests with no actions taken | Uses a new world |
| Fork | `world.fork()` | Trying two decisions on the same future | Takes a slot. Refused on ranking runs and in the final |
| Ranking run | `client.create(level=8, board=True)` or the starter's `--board` | Five secret weeks per level per round, the same for every team | Each week is played once, in order. No fork and no reveal |
| Board | `client.board(8)` | Your place against the house best system, and how many teams are ranked | Margin and rank appear after your fifth run |
| Run viewer | [spread.bahnexpress.com/viewer](https://spread.bahnexpress.com/viewer/) | Each order's money and story, worst margin first, with a map replay | Uses the key you gave the site on the team page |
| Test final | `client.final()`, then `world.stream()`, or the starter's `--final` | The live clock | Saturday 14:00 and 20:00, about 19 minutes each |

**The six actions:** `quote`, `post`, `offer`, `reprice`, `withdraw`, `release`.

**The twenty event kinds:** `price_request`, `order_won`, `order_lost`, `order_changed`, `order_cancelled`, `release`, `gig_viewed`, `gig_booked`, `gig_dropped`, `gig_started`, `driver_late`, `no_show`, `gig_expired`, `offer_answered`, `picked_up`, `visit_failed`, `delivered`, `deadline_close`, `forecast`, `ledger`.

**World lab: measure before you build.** Each experiment ends as one file in `docs/log/`. These files are also the "why" of the pitch.

1. **Money map.** Export a week of requests with no actions. Compare list price with typical fee by lane and option. Count requests by town, hour and day, and the share with notes.
2. **Driver map.** Roster plus map: drivers within 30 km of each town, on several level 8 seeds. Which towns go empty, and does it change per seed?
3. **Starter autopsy.** Open one starter week in the viewer. Split its loss into fees, refunds and penalties.
4. **Price ladder.** Quote a random ratio between 1.0 and 1.7 times list on every request. Plot win rate against ratio, per seed. Use Monday and Tuesday only, before trust and competitor reactions blur it.
5. **Fee ladder.** Post each won car at a flat fee, at a random ratio of the typical fee. Plot time to booking against ratio, town and lead time. Level 3 gives clean driver data, because every quote wins there. Level 8 gives the real levels.
6. **Mechanism checks with fork.** One world, two branches: flat schedule against rising schedule, withdraw and repost against waiting, a direct offer to a driver near the delivery against an open post.
7. **Notes corpus.** Every note with its truth fields, from 30 or more finished weeks at levels 5 to 8.

**The loop for every change.** A builds these targets in the harness.

```sh
make check                          # tests, determinism, 3 seed smoke
make sweep SET=dev                  # 10 fixed seeds, level 8
make compare BASE=main NEW=HEAD     # paired table on the same seeds
make ablate FLAG=dealer.trust       # one flag on and off, same seeds
make sweep SET=fresh N=20 TAG=rc3   # 20 new seeds before tagging
make emulate SEED=dev-01            # live clock rehearsal
```

Each run writes `data/runs/<run id>/` with the score, the events, the decision log and the reveal.

**Rehearse the live final any time.** The final gives 4.5 real seconds per request and has no `advance`. The emulator plays a practice week while a ticker advances one world minute every 0.3 seconds, and the bot runs in live mode on the stream. Check early that a practice stream delivers events while another call advances the world. If it does not, the two test finals are your only live rehearsals.

**Chaos tests on the emulator.** Kill the bot mid-Wednesday and restart it. Freeze it for 30 seconds. Drop the stream. Add 500 ms of latency. Feed it 429 and 502 answers. A pass means the week is still ranked and no gig was posted twice.

**Limits to design for in the final.** 20 actions a second with a burst of 50, 50 reads a second, 50 actions per batch, 16 open streams. Over the limit the final answers 429 at once, so the bot needs its own queue with quotes first. A 502, 503 or 504 means the server is restarting: wait, read the world again, then act.

Sources: [API reference](https://spread.bahnexpress.com/kit/API.md), [OpenAPI contract](https://spread.bahnexpress.com/openapi.json), [handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md).

## Timeline to Sunday 08:00

Feature freeze is Saturday 20:30 and code freeze is Sunday 00:45, so the last night goes to validation, the pitch and sleep. Times are Helsinki time. Ranking rounds are practice, so play them at milestones only.

| When | Person A | Person B | Gate before moving on |
| --- | --- | --- | --- |
| Fri 22:00 to 24:00 | Team, key, repo, skeleton, stubs, tag `v0` | World lab experiments 1 to 3 with the kit starter | Preliminary submission sent by 23:59. `v0` plays a full level 8 week |
| Fri 24:00 to 01:30 | Sweep and compare harness. Baseline quote: one fixed ratio above list, decline empty towns | Cost oracle from the driver map. Start the price ladder and fee ladder so they run overnight | Baseline is ranked on all 10 DEV seeds, at any margin |
| Fri night | Sleep | Sleep |  |
| Sat 08:00 to 09:00 | Read the overnight data together. Play the 09:00 round with the baseline | Same | First outside number. Count the ranked teams at level 8 |
| Sat 09:00 to 13:30 | Win model and quote policy on the acceptance curve. Then the live runner | Fee model, dispatch with all car rules, exception handlers, first notes reader | `rc1` is ranked on 20 fresh seeds with positive margin on each. Play the 12:00 round |
| Sat 13:45 to 14:30 | Test final 1 on the machine that will run the final. Kill and restart the bot once on purpose | Watch the log for 429s, lag and failed visits | The bot keeps up with the clock and survives the restart |
| Sat 14:30 to 19:30 | Trust pricing. Price war and outage handling. Emulator and chaos tests | Governor. Bundles and direct offers. Snow and summer tyres. Notes reader scored on the corpus | Every idea has an ablation file. `rc2` beats `rc1` on fresh seeds. Play the 15:00 or 18:00 round |
| Sat 19:45 to 20:30 | Test final 2 as a full dress rehearsal: final machine, supervisor, standby laptop | Same | No manual fix was needed during the run |
| Sat 20:30 to 24:00 | Feature freeze. Fresh seed validation, ablation table, robustness charts | Feature freeze. Slides, script, what did not work, what would break it | `rc3` plays the 21:00 round. Deck is complete except the final numbers |
| Sun 00:00 to 00:45 | Play the 00:00 round from `rc3`. Tag `final`. Code freeze | Pull `final` on the standby laptop and smoke test it | Tag `final` exists on every machine |
| Sun night | Sleep, alarm at 06:15 | Sleep, alarm at 06:15 |  |
| Sun 06:30 to 07:45 | Runbook below | Runbook below | Bot started and waiting before 07:45 |
| Sun 08:00 to 08:35 | Final. Watch, do not touch | Same |  |
| Sun 08:35 to 10:00 | Save reveal and score. Fill in the final numbers | Finish slides. Submit hash, code link and presentation | Submitted by 10:00 |

If you fall behind, cut scope in this order: bundles and offers, price war handling, snow handling. Never cut the governor, the restart recovery or the dress rehearsal.

## Final-run runbook

On Sunday the bot runs untouched from a frozen tag. Your only jobs are to start it once, watch it, and restart it if it dies.

**Saturday night, before sleeping**

- [ ] Tag `final` is pushed, and every machine has it checked out with a clean install.
- [ ] `make check` passes on the machine that runs the final.
- [ ] Test final 2 was played with this exact setup.
- [ ] A supervisor restarts the bot when it exits. On start the bot rebuilds from `world.snapshot()` and `world.events()`.
- [ ] The deck has every slide except the final numbers.

**Sunday 06:30 to 07:45**

- [ ] The key works: `client.worlds()` answers. Registration closes at 07:30.
- [ ] No practice sweep and no second bot is running anywhere.
- [ ] From 07:30, `client.final()` returns a world that has not ended. Before that it answers 404 or returns the last test final.
- [ ] Start the bot in final mode under the supervisor by 07:45. It waits for 08:00.
- [ ] Open the live leaderboard and the bot log side by side.

**Sunday 08:00 to about 08:35**

- [ ] One of you watches the bot: event lag, 429 count, orders at risk, on-time share.
- [ ] The other watches the leaderboard and keeps the standby laptop ready.
- [ ] If the bot dies, the supervisor restarts it. If the machine or the network dies, make sure it is stopped, then start the standby.
- [ ] No code changes. The only manual lever is the rescue switch, used if on-time share falls toward 90% and the governor has not reacted.

**After the final**

- [ ] Save `world.reveal()`, the events and the score. Screenshot the leaderboard.
- [ ] Put the final margin and on-time share into the slides.
- [ ] Submit on the Junction platform by 10:00: submission hash from the team page, code link, presentation.
- [ ] If you are in the top 10, the jury meets teams between 10:30 and 14:00.

While your bot is down, requests go to the competitor and the week keeps running, so a fast restart costs little. Source: [judging page](https://spread.bahnexpress.com/judging).

## Briefs for Opus 5.5

There are three texts to copy: one shared `CLAUDE.md` for the repo, and one kickoff prompt for each of you. The shared file holds the rules that never change. The kickoff prompts hold the ordered work, each step with a test for done.

**Shared brief: save as `CLAUDE.md` in the repo root.**

```text
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
```

**Kickoff prompt for Person A.**

```text
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
```

**Kickoff prompt for Person B.**

```text
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
```

## Pitch notes

The jury scores four words: elegant, clear, creative, robust. Build the deck around one idea, and prove each claim with the same-week numbers the judging page asks for.

**The one sentence.** Spread is two auctions with hidden prices. We learn both during the week with one estimator, and we only take a car when the spread is positive and a driver is really there.

**Why it should beat other approaches.** Each line is a claim your numbers must back before it goes on a slide.

- **It learns the week instead of remembering practice.** Competitor prices sit anywhere from 26% to 54% above list, and driver supply changes by town. A bot with tuned constants is right for some weeks. Yours carries no number that belongs to one week.
- **It treats on-time delivery as a budget.** The organisers' oracle sees every hidden price and is still ranked on only 7 of 20 weeks, because it wins more cars than it can move. Information is not the bottleneck. Restraint is.
- **One mechanism, used twice.** Dealers and drivers are the same problem from two sides. That is "few parts, each with a reason".
- **Every claim is measured on the same weeks.** Worlds are deterministic, so each idea has an on number and an off number.
- **It survives.** Kill it mid-week and it rebuilds itself from the event log.

**Slides.** The judging page asks, for each big idea: the idea, why you had it, and its effect with and without on the same weeks.

| # | Slide | What goes on it | Scores on |
| --- | --- | --- | --- |
| 1 | Result | Final margin and on-time share. The one sentence | Clear |
| 2 | What we saw | The starter wins everything and delivers half. The oracle knows everything and is ranked 7 of 20. The problem is choosing cars, not knowing prices | Creative |
| 3 | Idea 1: two markets, one estimator | Both curves as learned live on one week. Why: you only ever see yes or no. Effect with and without | Elegant |
| 4 | Idea 2: win only what you can move | Map of Finland with driver supply per town and the cars declined. Effect with and without | Creative |
| 5 | Idea 3: on-time as a budget | On-time share through one week, governor on and off. Effect with and without | Robust |
| 6 | Idea 4: the best of the rest | The notes reader scored on truth, or the fee schedule that does not teach waiting. Pick the one with the larger measured effect | Clear |
| 7 | Unseen weeks | Margin per week on 20 fresh seeds and weeks ranked of 20. Best ranking round. Kill and restart test | Robust |
| 8 | What did not work, what would break it | A short, specific list | Clear |

**Report in the organisers' format.** Give "margin a week" and "weeks ranked of 20" on 20 fresh level 8 weeks, next to their table: House starter at −€67,177 and 0 of 20, House best at €12,551 and 20 of 20, the oracle at €16,578 and 7 of 20. Say that your 20 weeks are not their 20 weeks.

**Collect as you go.**

- [ ] One log file per experiment, with the numbers on and off.
- [ ] The board saved after every round you play. The best round goes in the deck.
- [ ] Viewer screenshots: the map replay of a good week, and the worst order of a bad one.
- [ ] A chart of the two learned curves from one week.
- [ ] The ablation table on 20 fresh weeks.
- [ ] A list of dead ideas, one line each on why.
- [ ] A short screen capture of the kill and restart test.

**Speech skeleton, about two minutes.**

1. Every car is two yes or no questions. Will the dealer take our price? Will a driver take our fee?
2. We never see either threshold. One small estimator learns both curves, live, from yes and no.
3. Knowing prices is not enough. The organisers' oracle knows everything and is ranked on 7 weeks of 20. It wins more cars than it can move.
4. So before we price a car we ask whether a driver is really there. And we keep a budget of late cars that we refuse to overspend.
5. Nothing in the code knows a practice week. On 20 unseen weeks we were ranked on \[N\] of 20, at \[X\] euros a week.
6. Each idea on and off, same weeks: \[table\].
7. It rebuilds itself from the event log. We killed it mid-week \[N\] times.
8. What did not work: \[list\]. What would break it: \[list\].

**Questions to rehearse.**

- What happens in the first hours, before the bot has data?
- What if the competitor's prices move mid-week?
- Why no language model for the notes at run time?
- Which part would you remove first, and what would it cost?
- What kind of week breaks it?

Sources: [judging page](https://spread.bahnexpress.com/judging), [challenge page](https://spread.bahnexpress.com/).

## Open questions for the Bahn booth

These answers would change the design, so ask early. The booth also gives hints.

- [ ] Is trust counted per dealer? Does one late car of a trade-in halve it?
- [ ] Does withdrawing and reposting a gig notify nearby drivers again?
- [ ] At level 8, does the roster list only the drivers that exist this week, so empty towns are visible on Monday morning?
- [ ] How does a dealer weigh the three delivery options against each other?
- [ ] Does a practice world's stream deliver events while `advance` is called from another connection?
- [ ] May the bot run on a cloud server during the final? Where is the game server hosted?
- [ ] What does "registration closes at 07:30" require beyond an existing team?
- [ ] Is a call to an outside model allowed at run time? The plan does not need one.
- [ ] How many teams were ranked at level 8 in the last round?
- [ ] One hint on House best: what kind of car does it decline?
