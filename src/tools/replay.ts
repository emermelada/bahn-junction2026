/** Offline smoke test: feeds a stored run's events through a desk (fake act) to catch exceptions and print quote stats.
 * node src/tools/replay.ts runs/<run> [cfg.json] */
import { readFileSync } from "node:fs"
import type { DeskEvent } from "../client/types.ts"
import { loadCfg } from "../config.ts"
import { createDesk } from "../desk.ts"

const dir = process.argv[2]!
const cfg = loadCfg(process.argv[3])
const events: DeskEvent[] = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
const roster = JSON.parse(readFileSync(`${dir}/roster.json`, "utf8"))
const map = JSON.parse(readFileSync(new URL("../../data/map.json", import.meta.url), "utf8"))
let id = 0
const decisions: any[] = []
const desk = createDesk(cfg, { level: 8, map, roster, endsAt: 1e9, act: async (a) => a.map(() => ({ ok: true as const, id: `g${id++}` })), log: (l) => decisions.push(l) })
let actions = 0
const kinds: Record<string, number> = {}
for (const e of events) {
  desk.setClock(e.at)
  await desk.handle(e)
  await desk.tick(e.at)
  const out = desk.drain()
  desk.onResults(out, out.map(() => ({ ok: true as const, id: `g${id++}` })))
  for (const a of out) kinds[a.type] = (kinds[a.type] ?? 0) + 1
  actions += out.length
}
const quotes = decisions.filter((d) => d.kind === "quote")
const why: Record<string, number> = {}
const tiers: Record<string, number> = {}
for (const q of quotes) for (const o of q.opts) { why[o.why || "admitted"] = (why[o.why || "admitted"] ?? 0) + 1; tiers[`${o.kind}:${o.tier}`] = (tiers[`${o.kind}:${o.tier}`] ?? 0) + 1 }
const anyAdmitted = quotes.filter((q) => q.opts.some((o: any) => o.admitted)).length
console.log({ events: events.length, actions, kinds, quotes: quotes.length, anyAdmitted, why, tiers })
