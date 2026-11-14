/** Per won order margin by quoted ratio (slowest admitted option) over runs. */
import { existsSync, readFileSync } from "node:fs"
const agg: Record<string, { n: number; m: number; q: number }> = {}
for (const dir of process.argv.slice(2)) {
  if (!existsSync(`${dir}/score.json`)) continue
  const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
  const pnl = new Map<string, number>(), won = new Set<string>()
  for (const e of ev) { if (e.kind === "order_won") won.add(e.order.id); if (e.kind === "ledger" && e.line.orderId) pnl.set(e.line.orderId, (pnl.get(e.line.orderId) ?? 0) + e.line.cents) }
  // gig driver fees without orderId are attributed via gig -> order from actions
  const gigOrder = new Map<string, string>()
  for (const l of readFileSync(`${dir}/actions.jsonl`, "utf8").trim().split("\n")) { const a = JSON.parse(l); if (a.action.type === "post" && a.result?.ok) gigOrder.set(a.result.id, a.action.stops[0].orderId) }
  for (const e of ev) if (e.kind === "ledger" && !e.line.orderId && e.line.gigId) { const o = gigOrder.get(e.line.gigId); if (o) pnl.set(o, (pnl.get(o) ?? 0) + e.line.cents) }
  for (const l of readFileSync(`${dir}/decisions.jsonl`, "utf8").trim().split("\n")) {
    const d = JSON.parse(l)
    if (d.kind !== "quote") continue
    const adm = d.opts.filter((o: any) => o.admitted)
    if (!adm.length) continue
    const r = Math.min(...adm.map((o: any) => o.price / o.list))
    const b = (Math.floor(r * 10) / 10).toFixed(1)
    agg[b] ??= { n: 0, m: 0, q: 0 }
    agg[b].q++
    if (won.has(d.id)) (agg[b].n++, (agg[b].m += pnl.get(d.id) ?? 0))
  }
}
for (const [b, v] of Object.entries(agg).sort()) console.log(`r ${b}: quotes ${String(v.q).padStart(4)} won ${String(v.n).padStart(4)} (${(100 * v.n / v.q).toFixed(0)}%)  margin/won €${(v.m / 100 / Math.max(1, v.n)).toFixed(1)}  margin/quote €${(v.m / 100 / v.q).toFixed(1)}`)
