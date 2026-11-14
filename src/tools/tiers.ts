/** Observed on-time share by (option taken, tier at quote) over runs: node src/tools/tiers.ts runs/a runs/b ... */
import { existsSync, readFileSync } from "node:fs"
const agg: Record<string, { n: number; late: number }> = {}
for (const dir of process.argv.slice(2)) {
  if (!existsSync(`${dir}/decisions.jsonl`)) continue
  const dec = readFileSync(`${dir}/decisions.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((d) => d.kind === "quote")
  const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
  const tier = new Map<string, any>()
  for (const d of dec) tier.set(d.id, d)
  const late = new Set<string>()
  const won = new Map<string, string>()
  for (const e of ev) {
    if (e.kind === "order_won") won.set(e.order.id, e.order.option)
    if (e.kind === "ledger" && e.line.orderId && (e.line.kind === "late_refund" || e.line.kind === "undelivered_penalty")) late.add(e.line.orderId)
  }
  for (const [id, opt] of won) {
    const d = tier.get(id)
    const o = d?.opts.find((x: any) => x.kind === opt)
    const slack = o ? (o.slack >= 24 ? "s24+" : o.slack >= 12 ? "s12-24" : o.slack >= 6 ? "s6-12" : "s<6") : "?"
    const k = `${opt}:${o?.tier ?? "?"}:${slack}`
    agg[k] ??= { n: 0, late: 0 }
    agg[k].n++
    if (late.has(id)) agg[k].late++
  }
}
for (const [k, v] of Object.entries(agg).sort()) console.log(k.padEnd(28), `n=${String(v.n).padStart(4)}  on-time ${(100 * (1 - v.late / v.n)).toFixed(1)}%`)
