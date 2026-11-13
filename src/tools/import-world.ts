/** Pulls an ENDED world into a run directory in the format of desk-api.ts, so analyze.ts can read a world that
 * another system played (the kit's starter, a teammate's run) exactly like one of our own runs.
 *
 *   node src/tools/import-world.ts <worldId> [--out runs/<dir>]      default: runs/imported-<worldId>
 *
 * Writes events.jsonl (world.events(-1), seq order, no repeats), snapshot.json, score.json, roster.json,
 * reveal.json (skipped with a note on 403/409: ranking run, or not ended), meta.json (what is known: worldId and
 * level from client.worlds(), seed null, cfgName "imported", the rest null/0), config.json ({ name: "imported" }),
 * and empty actions.jsonl and decisions.jsonl. It never creates a world and never writes runs/index.jsonl. */
import { existsSync, mkdirSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { parseArgs } from "node:util"
import { Client, SpreadError } from "../client/spread.ts"
import type { DeskEvent, Reveal, WorldSummary } from "../client/types.ts"

const ROOT = fileURLToPath(new URL("../../", import.meta.url))
const PAGE = 20_000 // events per request; the server may answer fewer or all

export function loadEnv(): void {
  try {
    process.loadEnvFile(`${ROOT}.env`)
  } catch {
    // no .env: SPREAD_URL and SPREAD_KEY may be in the environment already
  }
}

/** Every event of the world, oldest first, without repeats. */
async function allEvents(client: Client, worldId: string): Promise<DeskEvent[]> {
  const world = client.world(worldId)
  const bySeq = new Map<number, DeskEvent>()
  let after = -1
  while (true) {
    const batch = await world.events(after, PAGE)
    if (batch.length === 0) break
    for (const event of batch) if (!bySeq.has(event.seq)) bySeq.set(event.seq, event)
    const last = batch.at(-1)!.seq
    if (last <= after) break
    after = last
    if (batch.length < PAGE) break
  }
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

async function main(): Promise<void> {
  const { values: args, positionals } = parseArgs({ allowPositionals: true, options: { out: { type: "string" } } })
  const worldId = positionals[0]
  if (!worldId) {
    console.error("usage: node src/tools/import-world.ts <worldId> [--out runs/<dir>]")
    process.exit(2)
  }
  loadEnv()
  const client = new Client()
  const worlds = await client.worlds()
  const summary: WorldSummary | undefined = worlds.find((w) => w.worldId === worldId)
  if (!summary) {
    console.error(`import: world ${worldId} is not in this team's list (client.worlds()); nothing written`)
    process.exit(1)
  }
  if (!summary.ended) {
    console.error(`import: world ${worldId} has not ended (level ${summary.level}, ${summary.kind}); import only ended worlds`)
    process.exit(1)
  }
  const outDir = (args.out ?? `runs/imported-${worldId}`).replace(/[\\/]+$/, "")
  const dir = outDir.match(/^([a-zA-Z]:)?[\\/]/) ? outDir : `${ROOT}${outDir}`
  const runId = dir.split(/[\\/]/).filter(Boolean).at(-1)!
  mkdirSync(dir, { recursive: true })

  const world = client.world(worldId)
  const startedAt = new Date().toISOString()
  const events = await allEvents(client, worldId)
  const [snapshot, score, roster] = await Promise.all([world.snapshot(), world.score(), world.roster()])
  let reveal: Reveal | null = null
  let revealNote = ""
  try {
    reveal = await world.reveal()
  } catch (error) {
    if (!(error instanceof SpreadError) || (error.status !== 403 && error.status !== 409)) throw error
    revealNote = `reveal skipped: ${error.message}`
  }

  writeFileSync(`${dir}/events.jsonl`, events.map((e) => JSON.stringify(e)).join("\n") + (events.length ? "\n" : ""))
  writeFileSync(`${dir}/snapshot.json`, JSON.stringify(snapshot))
  writeFileSync(`${dir}/score.json`, JSON.stringify(score, null, 2))
  writeFileSync(`${dir}/roster.json`, JSON.stringify(roster))
  if (reveal) writeFileSync(`${dir}/reveal.json`, JSON.stringify(reveal))
  if (!existsSync(`${dir}/actions.jsonl`)) writeFileSync(`${dir}/actions.jsonl`, "")
  if (!existsSync(`${dir}/decisions.jsonl`)) writeFileSync(`${dir}/decisions.jsonl`, "")
  writeFileSync(`${dir}/config.json`, JSON.stringify({ name: "imported" }, null, 2))
  const meta = {
    runId,
    worldId,
    seed: null,
    level: summary.level,
    cfgName: "imported",
    cfgHash: null,
    policy: null,
    gitSha: null,
    startedAt,
    endedAt: new Date().toISOString(),
    steps: 0,
    wallMs: 0,
    msPerStep: 0,
    exceptions: 0,
    imported: { kind: summary.kind, parent: summary.parent, season: summary.season, boardRun: summary.boardRun, ended: summary.ended, reveal: reveal !== null },
  }
  writeFileSync(`${dir}/meta.json`, JSON.stringify(meta, null, 2))

  const kinds = new Map<string, number>()
  for (const e of events) kinds.set(e.kind, (kinds.get(e.kind) ?? 0) + 1)
  console.log(`${dir}: world ${worldId} (level ${summary.level}, ${summary.kind}, ended)`)
  console.log(`  events.jsonl ${events.length} events, seq ${events[0]?.seq ?? "-"}..${events.at(-1)?.seq ?? "-"}`)
  console.log(`  ${[...kinds].map(([k, n]) => `${k} ${n}`).join(", ")}`)
  console.log(`  snapshot: ${snapshot.orders.length} orders, ${snapshot.gigs.length} gigs, now ${snapshot.now}/${snapshot.endsAt}; roster ${roster.length} drivers`)
  console.log(`  score: margin ${score.marginCents} cents, on time ${(score.onTimeShare * 100).toFixed(1)}%, won ${score.wonOrders}, undelivered ${(score.undeliveredShare * 100).toFixed(1)}%, ranked ${score.ranked}`)
  console.log(reveal ? `  reveal.json: ${reveal.requests.length} requests, ${reveal.orders.length} orders, ${reveal.views.length} views` : `  ${revealNote}`)
}

main().catch((error) => {
  if (error instanceof SpreadError) {
    console.error(`spread: ${error.message}`)
    process.exit(1)
  }
  throw error
})
