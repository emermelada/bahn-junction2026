/** Margin per won order by option x drive band over runs (late share too). */
import { existsSync, readFileSync } from "node:fs"
import { Geo } from "../geo.ts"
const map = JSON.parse(readFileSync(new URL("../../data/map.json", import.meta.url), "utf8"))
const agg: Record<string, { n: number; m: number; late: number; rev: number }> = {}
for (const dir of process.argv.slice(2)) {
  if (!existsSync(`${dir}/score.json`)) continue
  const geo = new Geo(map, JSON.parse(readFileSync(`${dir}/roster.json`, "utf8")))
  const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
  const gigOrder = new Map<string, string>()
  for (const l of readFileSync(`${dir}/actions.jsonl`, "utf8").trim().split("\n")) { const a = JSON.parse(l); if (a.action.type === "post" && a.result?.ok) gigOrder.set(a.result.id, a.action.stops[0].orderId) }
  const pnl = new Map<string, number>(), rev = new Map<string, number>(), late = new Set<string>(), won = new Map<string, any>()
  for (const e of ev) {
    if (e.kind === "order_won") won.set(e.order.id, e.order)
    if (e.kind !== "ledger") continue
    const o = e.line.orderId ?? (e.line.gigId ? gigOrder.get(e.line.gigId) : undefined)
    if (!o) continue
    pnl.set(o, (pnl.get(o) ?? 0) + e.line.cents)
    if (e.line.kind === "revenue") rev.set(o, (rev.get(o) ?? 0) + e.line.cents)
    if (/late_refund|undelivered/.test(e.line.kind)) late.add(o)
  }
  for (const [id, o] of won) {
    const d = geo.road(o.legs[0].pickup.placeId, o.legs[0].delivery.placeId)
    const k = `${o.option.padEnd(13)} ${d < 60 ? "d<1h" : d < 120 ? "d1-2h" : d < 240 ? "d2-4h" : "d4h+"}`
    agg[k] ??= { n: 0, m: 0, late: 0, rev: 0 }
    agg[k].n++; agg[k].m += pnl.get(id) ?? 0; agg[k].rev += rev.get(id) ?? 0; if (late.has(id)) agg[k].late++
  }
}
for (const [k, v] of Object.entries(agg).sort()) console.log(k, `n=${String(v.n).padStart(4)} rev/order €${(v.rev / 100 / v.n).toFixed(0).padStart(4)} margin/order €${(v.m / 100 / v.n).toFixed(1).padStart(6)}  late ${(100 * v.late / v.n).toFixed(1)}%`)
