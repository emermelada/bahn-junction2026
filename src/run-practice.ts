/** Practice runner: one world, one desk, one step policy. Writes the run artifacts of desk-api.ts.
 * `stride`: quotes in the very next advance (≤ strideMin minutes after arrival) and wakes on WAKE_ON; at night and on
 * weekends it also wakes on price_request and jumps to the next day start. `starter`: the kit's loop, for the regression. */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { execSync } from "node:child_process"
import type { Client, World } from "./client/spread.ts"
import type { Action, ActionResult, DeskEvent, DeskEventKind, DriverProfile, Score, WorldMap } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import { cfgHash } from "./config.ts"
import type { Desk, DeskContext, RunMeta, StepPolicy } from "./desk-api.ts"
import { DAY, WAKE_ON, WAKE_ON_STARTER, WEEKDAYS } from "./desk-api.ts"
import { createDesk } from "./desk.ts"

export type RunOptions = {
  cfg: Cfg
  seed: string
  level: number
  policy: StepPolicy
  tag: string
  quiet?: boolean
  /** Called with the world as soon as it exists (the bench registers it for cleanup). */
  onWorld?: (world: World) => void
}

export type RunSummary = RunMeta & {
  tag: string
  marginCents: number
  revenueCents: number
  wonOrders: number
  onTimeShare: number
  undeliveredShare: number
  ranked: boolean
  requests: number
  unquoted: number
  warnings: number
  refused: number
  ledger: Record<string, number>
}

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")
export const RUNS_DIR = `${ROOT}runs`
export const RESULTS_CSV = `${ROOT}data/results.csv`

let cachedMap: WorldMap | null = null
export async function loadMap(client: Client): Promise<WorldMap> {
  if (cachedMap) return cachedMap
  const path = `${ROOT}data/map.json`
  cachedMap = existsSync(path) ? (JSON.parse(readFileSync(path, "utf8")) as WorldMap) : await client.map()
  return cachedMap
}

export function gitSha(): string {
  try {
    return execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim()
  } catch {
    return "nogit"
  }
}

const euros = (cents: number) => (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const fmtScore = (s: Score) =>
  `margin €${euros(s.marginCents).padStart(11)}  revenue €${euros(s.revenueCents).padStart(10)}  ${String(s.wonOrders).padStart(4)} won  ${(100 * s.onTimeShare).toFixed(1).padStart(5)}% on time  ${(100 * s.undeliveredShare).toFixed(1)}% undelivered`

/** Plays one practice world to its end. The world is deleted if anything throws before the end. */
export async function runPractice(client: Client, opts: RunOptions): Promise<RunSummary> {
  const { cfg, seed, level, policy, tag } = opts
  const hash = cfgHash(cfg)
  const world = await client.create(level as 8, { seed })
  opts.onWorld?.(world)
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)
  const runId = `${tag}-${seed}-${hash.slice(0, 6)}-${stamp}`
  const dir = `${RUNS_DIR}/${runId}`
  mkdirSync(dir, { recursive: true })
  const say = (line: string) => opts.quiet || console.log(`[${seed}] ${line}`)
  say(`world ${world.id} run ${runId}`)

  const startedAt = new Date().toISOString()
  const t0 = Date.now()
  let steps = 0
  let exceptions = 0
  const counts: Record<string, number> = {}
  const ledger: Record<string, number> = {}
  const requested = new Set<string>()
  const quotedOk = new Set<string>()
  let refused = 0

  const write = (file: string, lines: unknown[]) => {
    if (lines.length) appendFileSync(`${dir}/${file}`, lines.map((l) => JSON.stringify(l)).join("\n") + "\n")
  }
  const decisions: unknown[] = []
  const flushDecisions = () => write("decisions.jsonl", decisions.splice(0))

  const record = (at: number, actions: Action[], results: ActionResult[]) => {
    write("actions.jsonl", actions.map((action, i) => ({ at, action, result: results[i] ?? null })))
    actions.forEach((a, i) => {
      const r = results[i] as { ok: boolean } | undefined
      if (!r?.ok) refused++
      if (a.type === "quote" && r?.ok) quotedOk.add(a.requestId)
    })
  }

  let desk: Desk | null = null
  try {
    const snapshot = await world.snapshot()
    const roster: DriverProfile[] = await world.roster()
    writeFileSync(`${dir}/roster.json`, JSON.stringify(roster))
    writeFileSync(`${dir}/config.json`, JSON.stringify(cfg, null, 1))
    const map = await loadMap(client)
    const endsAt = snapshot.endsAt
    const ctx: DeskContext = {
      level,
      map,
      roster,
      endsAt,
      act: async (actions) => {
        const results = await world.act(actions)
        record(desk?.now ?? snapshot.now, actions, results)
        return results
      },
      log: (line) => decisions.push(line),
    }
    desk = createDesk(cfg, ctx)
    desk.setClock(snapshot.now)

    const ingest = async (events: DeskEvent[]) => {
      write("events.jsonl", events)
      for (const event of events) {
        counts[event.kind] = (counts[event.kind] ?? 0) + 1
        if (event.kind === "price_request") requested.add(event.request.id)
        if (event.kind === "ledger") ledger[event.line.kind] = (ledger[event.line.kind] ?? 0) + event.line.cents
        try {
          await desk!.handle(event)
        } catch (error) {
          exceptions++
          decisions.push({ at: event.at, kind: "exception", event: event.kind, error: String((error as Error)?.stack ?? error) })
          if (exceptions <= 3) console.error(`[${seed}] exception on ${event.kind}:`, error)
        }
      }
    }

    let now = snapshot.now
    while (now < endsAt) {
      const day = Math.floor(now / DAY)
      const midnight = (day + 1) * DAY
      let untilEvent: DeskEventKind[]
      let max: number
      if (policy.kind === "starter") {
        untilEvent = WAKE_ON_STARTER
        max = Math.min(endsAt, midnight)
      } else {
        const mod = now - day * DAY
        const weekday = day % 7 < 5 && day < 7
        const busy = weekday && mod >= policy.dayFrom && mod < policy.dayTo
        if (busy) {
          untilEvent = WAKE_ON
          max = Math.min(now + policy.strideMin, day * DAY + policy.dayTo)
        } else {
          untilEvent = [...WAKE_ON, "price_request"]
          const nextDayStart = mod < policy.dayFrom ? day * DAY + policy.dayFrom : midnight
          max = policy.nightSkip ? nextDayStart : Math.min(now + policy.strideMin, nextDayStart)
        }
        const wake = desk.nextWake()
        if (wake !== null && wake > now) max = Math.min(max, wake)
        max = Math.max(now + 1, Math.min(max, endsAt, midnight))
      }
      const actions = desk.drain()
      const step = await world.advance({ untilEvent, max, actions })
      steps++
      record(now, actions, step.results)
      desk.onResults(actions, step.results)
      now = step.now
      desk.setClock(now)
      await ingest(step.events)
      try {
        await desk.tick(now)
      } catch (error) {
        exceptions++
        decisions.push({ at: now, kind: "exception", event: "tick", error: String((error as Error)?.stack ?? error) })
        if (exceptions <= 3) console.error(`[${seed}] exception in tick:`, error)
      }
      flushDecisions()
      if (Math.floor(now / DAY) > day && !opts.quiet) {
        const s = await world.score()
        say(`${WEEKDAYS[day % 7]!.padEnd(9)} ${fmtScore(s)}  steps ${steps}  ${((Date.now() - t0) / 60000).toFixed(1)} min`)
      }
    }
    // Anything still in the outbox at the very end is moot, but send it so the action log is complete.
    const tail = desk.drain()
    if (tail.length) record(now, tail, await world.act(tail).catch(() => []))
    flushDecisions()

    const score = await world.score()
    const endSnap = await world.snapshot()
    writeFileSync(`${dir}/score.json`, JSON.stringify(score, null, 1))
    writeFileSync(`${dir}/snapshot.json`, JSON.stringify(endSnap))
    try {
      writeFileSync(`${dir}/reveal.json`, JSON.stringify(await world.reveal()))
    } catch (error) {
      say(`no reveal: ${(error as Error).message}`)
    }
    const wallMs = Date.now() - t0
    const summary: RunSummary = {
      runId,
      worldId: world.id,
      seed,
      level,
      cfgName: cfg.name,
      cfgHash: hash,
      policy,
      gitSha: gitSha(),
      startedAt,
      endedAt: new Date().toISOString(),
      steps,
      wallMs,
      msPerStep: Math.round(wallMs / Math.max(1, steps)),
      exceptions,
      tag,
      ...score,
      requests: requested.size,
      unquoted: [...requested].filter((id) => !quotedOk.has(id)).length,
      warnings: counts["deadline_close"] ?? 0,
      refused,
      ledger,
    }
    writeFileSync(`${dir}/meta.json`, JSON.stringify(summary, null, 1))
    appendFileSync(`${RUNS_DIR}/index.jsonl`, JSON.stringify(summary) + "\n")
    appendResult(summary)
    console.log(`[${seed}] END ${fmtScore(score)}  ${score.ranked ? "RANKED" : "unranked"}  steps ${steps} (${summary.msPerStep} ms/step, ${(wallMs / 60000).toFixed(1)} min)  unquoted ${summary.unquoted}  refused ${refused}  exc ${exceptions}`)
    return summary
  } catch (error) {
    flushDecisions()
    await world.delete().catch(() => {})
    say(`stopped by an error; world ${world.id} deleted`)
    throw error
  }
}

const CSV_HEAD = "runId,tag,seed,level,cfgName,cfgHash,policy,gitSha,startedAt,steps,wallMin,marginEur,revenueEur,wonOrders,onTimePct,undeliveredPct,ranked,requests,unquoted,warnings,refused,exceptions,driverFeeEur,lateRefundEur,undeliveredEur,failedVisitEur,fineEur\n"

function appendResult(s: RunSummary): void {
  if (!existsSync(RESULTS_CSV)) writeFileSync(RESULTS_CSV, CSV_HEAD)
  const e = (c: number | undefined) => ((c ?? 0) / 100).toFixed(2)
  const row = [
    s.runId, s.tag, s.seed, s.level, s.cfgName, s.cfgHash, s.policy.kind, s.gitSha, s.startedAt, s.steps, (s.wallMs / 60000).toFixed(1),
    e(s.marginCents), e(s.revenueCents), s.wonOrders, (100 * s.onTimeShare).toFixed(2), (100 * s.undeliveredShare).toFixed(2), s.ranked,
    s.requests, s.unquoted, s.warnings, s.refused, s.exceptions,
    e(s.ledger.driver_fee), e(s.ledger.late_refund), e(s.ledger.undelivered_penalty), e(s.ledger.failed_visit), e(s.ledger.fine),
  ]
  appendFileSync(RESULTS_CSV, row.join(",") + "\n")
}
