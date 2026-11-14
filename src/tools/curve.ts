/** Win rate by quoted ratio of the slowest quoted option, per kind, over runs. node src/tools/curve.ts runs/a ... */
import { existsSync, readFileSync } from "node:fs"
const agg: Record<string, Record<string, [number, number]>> = {}
for (const dir of process.argv.slice(2)) {
  if (!existsSync(`${dir}/actions.jsonl`)) continue
  const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
  const req = new Map<string, any>(), won = new Set<string>(), lost = new Set<string>()
  for (const e of ev) { if (e.kind === "price_request") req.set(e.request.id, e.request); if (e.kind === "order_won") won.add(e.order.id); if (e.kind === "order_lost") lost.add(e.requestId) }
  for (const l of readFileSync(`${dir}/actions.jsonl`, "utf8").trim().split("\n")) {
    const a = JSON.parse(l)
    if (a.action.type !== "quote" || !a.result?.ok) continue
    const r = req.get(a.action.requestId)
    const slow = ["within_3_days", "next_day", "same_day"].find((k) => a.action.prices[k] && a.action.prices[k] < 2.5 * r.options.find((o: any) => o.kind === k).listPriceCents)
    if (!slow) continue
    const ratio = a.action.prices[slow] / r.options.find((o: any) => o.kind === slow).listPriceCents
    const bin = (Math.round(ratio * 10) / 10).toFixed(1)
    agg[slow] ??= {}
    agg[slow][bin] ??= [0, 0]
    if (won.has(r.id)) agg[slow][bin][0]++
    if (won.has(r.id) || lost.has(r.id)) agg[slow][bin][1]++
  }
}
for (const [k, bins] of Object.entries(agg)) console.log(k.padEnd(14), Object.entries(bins).sort().map(([b, [w, n]]) => `${b}:${(100 * w / n).toFixed(0)}%/${n}`).join("  "))
