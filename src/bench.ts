/** Batch runner. node src/bench.ts <command> [options]
 *   run         --cfg cfg/x.json --seeds a,b,c [--slots 4] [--policy stride|starter] [--tag t] [--level 8]
 *   determinism --cfg cfg/x.json --seed s [--policy stride]      (same config twice, same cents?)
 *   ab          --a cfg/a.json --b cfg/b.json --seeds a,b,c [--slots 4] [--tag t]   (paired table)
 *   gate        --cfg cfg/x.json [--slots 4] [--tag t]           (G seeds, PLAN §7 floor)
 *   table       --tags t1,t2 | --a <cfgHash|name> --b <...> [--seeds ...]   (paired table from runs/index.jsonl)
 *   worlds                                                        (the team's worlds; ours marked)
 *   cleanup     --mine                                            (delete our non-ended worlds)
 * Never creates ranking runs. Uses at most --slots worlds and leaves --reserve of the team's 8. */
import { appendFileSync, existsSync, readFileSync } from "node:fs"
import { parseArgs } from "node:util"
import { Client, World } from "./client/spread.ts"
import type { Cfg } from "./config.ts"
import { cfgHash, loadCfg } from "./config.ts"
import type { StepPolicy } from "./desk-api.ts"
import { STARTER_POLICY, STRIDE_POLICY } from "./desk-api.ts"
import type { RunSummary } from "./run-practice.ts"
import { RUNS_DIR, runPractice } from "./run-practice.ts"

try {
  process.loadEnvFile(new URL("../.env", import.meta.url))
} catch {}

export const GATE_SEEDS = ["spread-1", "v2-g1", "v2-g2", "v2-g3", "v2-g4"]
const REGISTRY = `${RUNS_DIR}/worlds.jsonl`
const MAX_TEAM = 8

const { positionals, values: args } = parseArgs({
  allowPositionals: true,
  options: {
    cfg: { type: "string" }, a: { type: "string" }, b: { type: "string" },
    seeds: { type: "string" }, seed: { type: "string" }, slots: { type: "string", default: "4" }, reserve: { type: "string", default: "2" },
    policy: { type: "string", default: "stride" }, tag: { type: "string" }, level: { type: "string", default: "8" },
    tags: { type: "string" }, mine: { type: "boolean" }, quiet: { type: "boolean" }, stride: { type: "string" },
  },
})

const client = new Client()
const level = Number(args.level)
const mine = new Set<string>()
const registered = (world: World) => {
  mine.add(world.id)
  appendFileSync(REGISTRY, JSON.stringify({ worldId: world.id, at: new Date().toISOString() }) + "\n")
}
const ours = (): Set<string> =>
  new Set(existsSync(REGISTRY) ? readFileSync(REGISTRY, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l).worldId as string) : [])

function policyOf(name: string): StepPolicy {
  const base = name === "starter" ? STARTER_POLICY : STRIDE_POLICY
  return args.stride ? { ...base, strideMin: Number(args.stride) } : base
}

async function freeSlots(): Promise<number> {
  const open = (await client.worlds()).filter((w) => !w.ended && w.kind === "practice").length
  return MAX_TEAM - open - Number(args.reserve)
}

/** Runs every (cfg, seed) job with at most `slots` worlds at once. A failed job is reported and skipped. */
async function runJobs(jobs: { cfg: Cfg; seed: string; tag: string }[], policy: StepPolicy): Promise<RunSummary[]> {
  let free = await freeSlots()
  for (let waited = 0; free <= 0; waited++) {
    if (waited % 10 === 0) console.log(`no free practice slot (team free after reserve: ${free}); waiting...`)
    await new Promise((done) => setTimeout(done, 30_000))
    free = await freeSlots()
  }
  const slots = Math.max(1, Math.min(Number(args.slots), free, jobs.length))
  console.log(`${jobs.length} jobs on ${slots} slots, policy ${policy.kind}/${policy.strideMin}`)
  const out: RunSummary[] = []
  let next = 0
  const worker = async () => {
    while (next < jobs.length) {
      const job = jobs[next++]!
      try {
        out.push(await runPractice(client, { ...job, level, policy, onWorld: registered, quiet: args.quiet }))
      } catch (error) {
        console.error(`[${job.seed}] FAILED: ${(error as Error).message}`)
      }
    }
  }
  await Promise.all(Array.from({ length: slots }, worker))
  return out
}

const seedsArg = (fallback?: string[]): string[] => (args.seeds ? args.seeds.split(",") : fallback ?? (args.seed ? [args.seed] : []))
const tagOf = (cfg: Cfg) => args.tag ?? cfg.name

function readIndex(): RunSummary[] {
  const path = `${RUNS_DIR}/index.jsonl`
  return existsSync(path) ? readFileSync(path, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []
}

const eur = (c: number) => (c / 100).toFixed(0).padStart(8)
const pct = (s: number) => (100 * s).toFixed(1).padStart(5)

/** Paired table: per seed A vs B; sign count; mean delta; PLAN §7 adoption verdict. */
function pairedTable(A: RunSummary[], B: RunSummary[]): void {
  const bySeed = (rows: RunSummary[]) => new Map(rows.map((r) => [r.seed!, r]))
  const a = bySeed(A)
  const b = bySeed(B)
  const seeds = [...a.keys()].filter((s) => b.has(s))
  console.log(`seed        |   A margin  A on%  A won |   B margin  B on%  B won |    Δ margin  Δ on%`)
  let plus = 0
  let sum = 0
  let bRanked93 = true
  for (const s of seeds) {
    const x = a.get(s)!
    const y = b.get(s)!
    const d = y.marginCents - x.marginCents
    sum += d
    if (d > 0) plus++
    if (!(y.ranked && y.onTimeShare >= 0.93)) bRanked93 = false
    console.log(`${s.padEnd(11)} | ${eur(x.marginCents)} ${pct(x.onTimeShare)} ${String(x.wonOrders).padStart(5)}  | ${eur(y.marginCents)} ${pct(y.onTimeShare)} ${String(y.wonOrders).padStart(5)}  | ${eur(d).padStart(10)} ${pct(y.onTimeShare - x.onTimeShare)}`)
  }
  const n = seeds.length
  const mean = n ? sum / n : 0
  const adopt = n > 0 && bRanked93 && mean > 0 && plus >= n - 1
  console.log(`n=${n}  B better on ${plus}/${n}  mean Δ €${(mean / 100).toFixed(0)}  B all ranked ≥93%: ${bRanked93}  → ${adopt ? "ADOPT B" : "keep A"}`)
}

function gateVerdict(rows: RunSummary[]): void {
  console.log(`seed        |   margin  on%    won  unq  exc  undeliv`)
  let pass = true
  for (const r of rows) {
    const ok = r.ranked && r.onTimeShare >= 0.93 && r.unquoted === 0 && r.exceptions === 0
    if (!ok) pass = false
    console.log(`${r.seed!.padEnd(11)} | ${eur(r.marginCents)} ${pct(r.onTimeShare)} ${String(r.wonOrders).padStart(6)} ${String(r.unquoted).padStart(4)} ${String(r.exceptions).padStart(4)} ${pct(r.undeliveredShare)}  ${ok ? "ok" : "FAIL"}`)
  }
  const mean = rows.reduce((s, r) => s + r.marginCents, 0) / Math.max(1, rows.length)
  console.log(`mean €${(mean / 100).toFixed(0)}/week  gate ${pass && rows.length === GATE_SEEDS.length ? "PASS" : "FAIL"}`)
}

async function main(): Promise<void> {
  const cmd = positionals[0]
  if (cmd === "run") {
    const cfg = loadCfg(args.cfg)
    await runJobs(seedsArg().map((seed) => ({ cfg, seed, tag: tagOf(cfg) })), policyOf(args.policy!))
  } else if (cmd === "determinism") {
    const cfg = loadCfg(args.cfg)
    const seed = args.seed ?? "spread-1"
    const tag = tagOf(cfg)
    const rows = await runJobs([{ cfg, seed, tag: `${tag}-det1` }, { cfg, seed, tag: `${tag}-det2` }], policyOf(args.policy!))
    const [x, y] = rows
    if (!x || !y) throw new Error("a determinism run failed")
    const same = x.marginCents === y.marginCents && x.wonOrders === y.wonOrders && x.onTimeShare === y.onTimeShare
    console.log(`determinism ${same ? "OK" : "MISMATCH"}: ${x.marginCents} vs ${y.marginCents} cents, ${x.wonOrders} vs ${y.wonOrders} won, steps ${x.steps}/${y.steps}`)
  } else if (cmd === "ab") {
    const A = loadCfg(args.a)
    const B = loadCfg(args.b)
    const seeds = seedsArg()
    const tag = args.tag ?? `${A.name}-vs-${B.name}`
    const rows = await runJobs(seeds.flatMap((seed) => [{ cfg: A, seed, tag: `${tag}-A` }, { cfg: B, seed, tag: `${tag}-B` }]), policyOf(args.policy!))
    pairedTable(rows.filter((r) => r.tag === `${tag}-A`), rows.filter((r) => r.tag === `${tag}-B`))
  } else if (cmd === "gate") {
    const cfg = loadCfg(args.cfg)
    const rows = await runJobs(GATE_SEEDS.map((seed) => ({ cfg, seed, tag: `${tagOf(cfg)}-gate` })), policyOf(args.policy!))
    gateVerdict(rows)
  } else if (cmd === "table") {
    const index = readIndex()
    const seeds = args.seeds ? new Set(args.seeds.split(",")) : null
    const pick = (key: string) => {
      const rows = index.filter((r) => (r.tag === key || r.cfgHash.startsWith(key) || r.cfgName === key) && (!seeds || seeds.has(r.seed!)))
      return [...new Map(rows.map((r) => [r.seed, r])).values()] // latest per seed
    }
    if (args.tags) for (const t of args.tags.split(",")) (console.log(`== ${t}`), gateVerdict(pick(t)))
    else pairedTable(pick(args.a!), pick(args.b!))
  } else if (cmd === "worlds") {
    const known = ours()
    for (const w of await client.worlds()) console.log(`${w.worldId}  ${w.kind.padEnd(8)} L${w.level}  ${w.ended ? "ended " : "OPEN  "} ${w.boardRun ? `board#${w.boardRun}` : ""} ${known.has(w.worldId) ? "(ours)" : ""}`)
  } else if (cmd === "cleanup") {
    if (!args.mine) throw new Error("cleanup only with --mine (never touches worlds we did not create)")
    const known = ours()
    for (const w of await client.worlds()) {
      if (w.ended || !known.has(w.worldId) || w.boardRun) continue
      await client.world(w.worldId).delete()
      console.log(`deleted ${w.worldId}`)
    }
  } else {
    console.log(readFileSync(new URL(import.meta.url), "utf8").split("\n").slice(0, 10).join("\n"))
  }
}

// Ctrl-C: delete the worlds this process created and that have not ended.
process.once("SIGINT", async () => {
  console.error("SIGINT: deleting this process's open worlds")
  await Promise.all([...mine].map((id) => client.world(id).delete().catch(() => {})))
  process.exit(130)
})

await main()
