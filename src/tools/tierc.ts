/** Why tier C: replays the M6 gate decisions of a run with flags (needs decisions with flags). Uses replay of request events. */
import { readFileSync } from "node:fs"
import type { PriceRequest } from "../client/types.ts"
import { loadCfg } from "../config.ts"
import { Geo } from "../geo.ts"
import { assess } from "../feasibility.ts"
const dir = process.argv[2]!
const cfg = loadCfg(process.argv[3])
const map = JSON.parse(readFileSync(new URL("../../data/map.json", import.meta.url), "utf8"))
const geo = new Geo(map, JSON.parse(readFileSync(`${dir}/roster.json`, "utf8")))
const reqs: PriceRequest[] = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((e) => e.kind === "price_request").map((e) => e.request)
const h: Record<string, number> = {}
for (const r of reqs) for (const o of r.options) {
  const f = assess(r, o, r.arrivedAt + 5, geo, cfg, null, () => false)
  if (f.tier !== "C") continue
  const k = `${o.kind} ${f.slackHours < 3 ? "slack<3" : f.slackHours < 8 ? "slack3-8" : "slack8+"} r30p=${f.reachPickup < 3 ? "<3" : f.reachPickup < 10 ? "3-9" : "10+"} ${f.flags.filter((x) => x !== "private_delivery").join("+") || "-"}`
  h[k] = (h[k] ?? 0) + 1
}
for (const [k, v] of Object.entries(h).sort((a, b) => b[1] - a[1]).slice(0, 25)) console.log(String(v).padStart(4), k)
