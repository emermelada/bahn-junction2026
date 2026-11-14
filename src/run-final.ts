/** The final loop: rejoin from snapshot + events -> stream -> act at once. Rebuilds from scratch on Unreachable.
 *   node src/run-final.ts --cfg cfg/x.json                 (waits for the team's final / test final)
 *   node src/run-final.ts --cfg cfg/x.json --world <id>    (rehearsal on a practice world that ticker.ts moves)
 * Exit codes: 0 the world ended; 1 fatal error (a supervisor restarts us); 130 Ctrl-C. One instance per key. */
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs"
import { parseArgs } from "node:util"
import { Client, SpreadError, Unreachable, World } from "./client/spread.ts"
import type { Action, ActionResult, DeskEvent } from "./client/types.ts"
import { loadCfg } from "./config.ts"
import type { Desk } from "./desk-api.ts"
import { DAY, WEEKDAYS } from "./desk-api.ts"
import { createDesk } from "./desk.ts"
import { RUNS_DIR, fmtScore, loadMap } from "./run-practice.ts"

try {
  process.loadEnvFile(new URL("../.env", import.meta.url))
} catch {}

const { values: args } = parseArgs({ options: { cfg: { type: "string" }, world: { type: "string" }, level: { type: "string", default: "8" } } })
const cfg = loadCfg(args.cfg)
const client = new Client()
const stamp = () => new Date().toISOString().slice(11, 19)
const say = (line: string) => console.log(`${stamp()} ${line}`)

async function nextFinal(): Promise<World> {
  for (let said = false; ; said = true) {
    const set = await client.final().catch((error: unknown) => {
      if (error instanceof SpreadError && error.status === 404) return null
      throw error
    })
    if (set) {
      const world = client.world(set.worldId)
      const snap = await world.snapshot()
      if (snap.now < snap.endsAt) return world
    }
    if (!said) say("No final is set (or the last one ended). Waiting...")
    await new Promise((done) => setTimeout(done, 10_000))
  }
}

/** One session: rebuild, then stream until the world ends. Throws Unreachable on a server restart. */
async function play(world: World, dir: string): Promise<void> {
  const history = await world.events()
  const snapshot = await world.snapshot()
  if (snapshot.now >= snapshot.endsAt) return
  const roster = await world.roster()
  const map = await loadMap(client)
  const write = (file: string, lines: unknown[]) => lines.length && appendFileSync(`${dir}/${file}`, lines.map((l) => JSON.stringify(l)).join("\n") + "\n")
  const decisions: unknown[] = []
  let desk: Desk
  const send = async (actions: Action[]): Promise<ActionResult[]> => {
    if (actions.length === 0) return []
    const results = await world.act(actions)
    write("actions.jsonl", actions.map((action, i) => ({ at: desk.now, action, result: results[i] ?? null })))
    const refused = results.filter((r) => !r.ok).length
    if (refused) say(`${refused} of ${actions.length} actions refused: ${(results.find((r) => !r.ok) as { reason: string }).reason}`)
    return results
  }
  desk = createDesk(cfg, { level: Number(args.level), map, roster, endsAt: snapshot.endsAt, act: send, log: (l) => decisions.push(l) })
  desk.setClock(snapshot.now)
  const t0 = Date.now()
  await desk.rejoin(snapshot, history)
  await desk.tick(snapshot.now)
  const first = desk.drain()
  desk.onResults(first, await send(first))
  write("decisions.jsonl", decisions.splice(0))
  say(`rejoined at ${clock(snapshot.now)} with ${history.length} events, ${snapshot.orders.length} orders, ${first.length} actions (${Date.now() - t0} ms)`)

  let lastSeq = history.at(-1)?.seq ?? -1
  let day = Math.floor(snapshot.now / DAY)
  let lastClockRead = 0
  for await (const event of world.stream({ after: lastSeq, idleMs: 1000 })) {
    let now = desk.now
    if (event === null) {
      // Read the clock at most once a second so time-based work (sweeps) runs between events.
      if (Date.now() - lastClockRead < 1000) continue
      lastClockRead = Date.now()
      now = args.world ? (await world.snapshot()).now : (await client.final()).now
    } else {
      if (event.seq <= lastSeq) continue // repeats after a reconnect
      lastSeq = event.seq
      now = Math.max(now, event.at)
      write("events.jsonl", [event])
    }
    desk.setClock(now)
    const t = Date.now()
    try {
      if (event) await desk.handle(event as DeskEvent)
      await desk.tick(now)
    } catch (error) {
      if (error instanceof Unreachable) throw error
      decisions.push({ at: now, kind: "exception", event: event?.kind ?? "tick", error: String((error as Error)?.stack ?? error) })
      say(`exception on ${event?.kind ?? "tick"}: ${(error as Error).message}`)
    }
    const actions = desk.drain()
    if (actions.length) desk.onResults(actions, await send(actions))
    const ms = Date.now() - t
    if (ms > 1500) say(`slow handle: ${event?.kind ?? "tick"} took ${ms} ms`)
    write("decisions.jsonl", decisions.splice(0))
    if (Math.floor(now / DAY) > day) {
      say(`${WEEKDAYS[day % 7]!.padEnd(9)} ${fmtScore(await world.score())}`)
      day = Math.floor(now / DAY)
    }
    if (now >= snapshot.endsAt) return
  }
}

const clock = (t: number) => `${WEEKDAYS[Math.floor(t / DAY) % 7]!.slice(0, 3)} ${String(Math.floor((t % DAY) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`

async function main(): Promise<number> {
  const world = args.world ? client.world(args.world) : await nextFinal()
  const dir = `${RUNS_DIR}/final-${world.id}`
  mkdirSync(dir, { recursive: true })
  writeFileSync(`${dir}/config.json`, JSON.stringify(cfg, null, 1))
  say(`world ${world.id}, cfg ${cfg.name}; artifacts in ${dir}`)
  process.once("SIGINT", () => {
    say("Stopped. The world keeps running without the desk; start again to rejoin.")
    process.exit(130)
  })
  for (let restarts = 0; ; restarts++) {
    try {
      await play(world, dir)
      const score = await world.score()
      say(`END ${fmtScore(score)} ${score.ranked ? "RANKED" : "not ranked"}`)
      writeFileSync(`${dir}/score.json`, JSON.stringify(score, null, 1))
      return 0
    } catch (error) {
      if (!(error instanceof Unreachable)) throw error
      say(`${error.message}. Rebuilding in 3 s (restart ${restarts + 1}).`)
      await new Promise((done) => setTimeout(done, 3000))
    }
  }
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error)
    process.exit(1)
  },
)
