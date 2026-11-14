/** Quick diagnostics of one run: node src/analyze.ts runs/<runId>
 * Ledger by kind, won/lost by option and quoted ratio, booked fee / reference by reach band, late orders by option
 * and pickup town, warnings, decisions summary. */
import { existsSync, readFileSync } from "node:fs"
import type { DeskEvent, PriceRequest } from "./client/types.ts"
import { Geo } from "./geo.ts"

const dir = process.argv[2]!
const lines = (f: string) => (existsSync(`${dir}/${f}`) ? readFileSync(`${dir}/${f}`, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [])
const events: DeskEvent[] = lines("events.jsonl")
const actions: any[] = lines("actions.jsonl")
const decisions: any[] = lines("decisions.jsonl")
const roster = JSON.parse(readFileSync(`${dir}/roster.json`, "utf8"))
const map = JSON.parse(readFileSync(new URL("../data/map.json", import.meta.url), "utf8"))
const geo = new Geo(map, roster)
const eur = (c: number) => `€${(c / 100).toFixed(0)}`

const requests = new Map<string, PriceRequest>()
const quotes = new Map<string, Record<string, number>>()
const won = new Map<string, any>()
const lost = new Set<string>()
const ledger: Record<string, number> = {}
const orderLedger = new Map<string, Record<string, number>>()
for (const e of events) {
  if (e.kind === "price_request") requests.set(e.request.id, e.request)
  else if (e.kind === "order_won") won.set(e.order.id, e.order)
  else if (e.kind === "order_lost") lost.add(e.requestId)
  else if (e.kind === "ledger") {
    ledger[e.line.kind] = (ledger[e.line.kind] ?? 0) + e.line.cents
    if (e.line.orderId) {
      const o = orderLedger.get(e.line.orderId) ?? {}
      o[e.line.kind] = (o[e.line.kind] ?? 0) + e.line.cents
      orderLedger.set(e.line.orderId, o)
    }
  }
}
for (const a of actions) if (a.action.type === "quote" && a.result?.ok) quotes.set(a.action.requestId, a.action.prices)

console.log("ledger:", Object.fromEntries(Object.entries(ledger).map(([k, v]) => [k, eur(v)])))

// Win rate by quoted ratio of the option the dealer could take (min ratio among quoted options).
const byRatio: Record<string, { won: number; lost: number }> = {}
for (const [id, prices] of quotes) {
  const req = requests.get(id)
  if (!req) continue
  const ratios = req.options.filter((o) => prices[o.kind]).map((o) => prices[o.kind]! / o.listPriceCents)
  const r = Math.min(...ratios)
  const b = r >= 2.5 ? "decline" : (Math.floor(r * 20) / 20).toFixed(2)
  byRatio[b] ??= { won: 0, lost: 0 }
  if (won.has(id)) byRatio[b].won++
  else if (lost.has(id)) byRatio[b].lost++
}
console.log("win by min quoted ratio:", Object.entries(byRatio).sort().map(([k, v]) => `${k}: ${v.won}/${v.won + v.lost}`).join("  "))

const optTaken: Record<string, number> = {}
for (const o of won.values()) optTaken[o.option] = (optTaken[o.option] ?? 0) + 1
console.log("option taken:", optTaken)

// Late orders: by option and pickup town; margin per order.
const late: Record<string, number> = {}
const lateTown: Record<string, number> = {}
let orderMargin = 0
const townPnl: Record<string, { n: number; margin: number; late: number }> = {}
for (const [id, o] of won) {
  const l = orderLedger.get(id) ?? {}
  const m = Object.values(l).reduce((s, v) => s + v, 0)
  orderMargin += m
  const town = o.legs[0].pickup.placeId
  townPnl[town] ??= { n: 0, margin: 0, late: 0 }
  townPnl[town].n++
  townPnl[town].margin += m
  if (l.late_refund || l.undelivered_penalty) {
    late[o.option] = (late[o.option] ?? 0) + 1
    lateTown[town] = (lateTown[town] ?? 0) + 1
    townPnl[town].late++
  }
}
console.log("late by option:", late)
console.log("town P&L (pickup):", Object.entries(townPnl).sort((a, b) => a[1].margin - b[1].margin).map(([t, v]) => `${t}(r30=${geo.reach30(t).all}) n${v.n} ${eur(v.margin)} late${v.late}`).join(" | "))

const kinds: Record<string, number> = {}
for (const e of events) kinds[e.kind] = (kinds[e.kind] ?? 0) + 1
console.log("events:", kinds)
const dk: Record<string, number> = {}
for (const d of decisions) dk[d.kind] = (dk[d.kind] ?? 0) + 1
const why: Record<string, number> = {}
for (const d of decisions) if (d.kind === "quote") for (const o of d.opts) why[`${o.kind}:${o.why || "ok"}`] = (why[`${o.kind}:${o.why || "ok"}`] ?? 0) + 1
console.log("decisions:", dk, why)
const stages: Record<string, number> = {}
for (const d of decisions) if (d.kind === "fee") stages[d.stage] = (stages[d.stage] ?? 0) + 1
console.log("fee stages:", stages)
const refused: Record<string, number> = {}
for (const a of actions) if (!a.result?.ok) refused[`${a.action.type}: ${String(a.result?.reason ?? "no result").slice(0, 60)}`] = (refused[`${a.action.type}: ${String(a.result?.reason ?? "").slice(0, 60)}`] ?? 0) + 1
console.log("refused:", refused)
