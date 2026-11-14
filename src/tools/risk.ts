/** On-time by (option, drive band, reach30 band, won-day) across runs. node src/tools/risk.ts runs/a ... */
import { existsSync, readFileSync } from "node:fs"
import { Geo } from "../geo.ts"
const map = JSON.parse(readFileSync(new URL("../../data/map.json", import.meta.url), "utf8"))
const agg: Record<string, { n: number; late: number }> = {}
const add = (k: string, late: boolean) => ((agg[k] ??= { n: 0, late: 0 }), agg[k].n++, late && agg[k].late++)
for (const dir of process.argv.slice(2)) {
  if (!existsSync(`${dir}/roster.json`) || !existsSync(`${dir}/score.json`)) continue
  const geo = new Geo(map, JSON.parse(readFileSync(`${dir}/roster.json`, "utf8")))
  const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
  const late = new Set<string>()
  for (const e of ev) if (e.kind === "ledger" && e.line.orderId && /late_refund|undelivered/.test(e.line.kind)) late.add(e.line.orderId)
  for (const e of ev) {
    if (e.kind !== "order_won") continue
    const o = e.order, P = o.legs[0].pickup.placeId, D = o.legs[0].delivery.placeId
    const drive = geo.road(P, D), r = geo.reach30(P).all
    const db = drive < 120 ? "d<2h" : drive < 240 ? "d2-4h" : "d4h+"
    const rb = r < 10 ? "r<10" : r < 40 ? "r10-39" : "r40+"
    const L = late.has(o.id)
    add(`${o.option} ${db} ${rb}`, L)
    add(`day${Math.floor(e.at / 1440)} ${o.option}`, L)
  }
}
for (const [k, v] of Object.entries(agg).sort()) console.log(k.padEnd(32), `n=${String(v.n).padStart(4)} on-time ${(100 * (1 - v.late / v.n)).toFixed(1)}%`)
