/** Late-order autopsy: node src/tools/late.ts runs/<run> */
import { readFileSync } from "node:fs"
const dir = process.argv[2]!
const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
const acts = readFileSync(`${dir}/actions.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
const gigOrder = new Map<string, string>()
for (const a of acts) if (a.action.type === "post" && a.result?.ok) gigOrder.set(a.result.id, a.action.stops[0].orderId)
const o = new Map<string, any>()
const get = (id: string) => o.get(id) ?? (o.set(id, { books: 0, drops: 0, warn: 0, expired: 0, late: false, fees: [] }), o.get(id))
for (const e of ev) {
  if (e.kind === "order_won") Object.assign(get(e.order.id), { won: e.at, opt: e.order.option, lp: e.order.lastPickupAt, dl: e.order.deadline, from: e.order.legs[0].pickup.window.from, P: e.order.legs[0].pickup.placeId })
  const oid = e.kind === "ledger" ? e.line.orderId : e.gigId ? gigOrder.get(e.gigId) : e.orderId
  if (!oid) continue
  const b = get(oid)
  if (e.kind === "gig_booked") (b.books++, b.firstBook ??= e.at, b.fees.push(e.feeCents))
  if (e.kind === "gig_dropped") b.drops++
  if (e.kind === "deadline_close") b.warn++
  if (e.kind === "gig_expired") b.expired++
  if (e.kind === "visit_failed") b.failed = e.reason
  if (e.kind === "ledger" && (e.line.kind === "late_refund" || e.line.kind === "undelivered_penalty")) b.late = true
}
const late = [...o.entries()].filter(([, b]) => b.late && b.won !== undefined)
const fmt = (t: number) => `d${Math.floor(t / 1440)} ${String(Math.floor((t % 1440) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`
for (const [id, b] of late.slice(0, 40)) console.log(`${id} ${b.opt.padEnd(13)} ${b.P.padEnd(12)} won ${fmt(b.won)} ready ${fmt(b.from)} lastPU ${fmt(b.lp)} dl ${fmt(b.dl)} firstBook ${b.firstBook ? fmt(b.firstBook) : "never"} books ${b.books} drops ${b.drops} warn ${b.warn} exp ${b.expired} ${b.failed ?? ""}`)
const s = { n: late.length, neverBooked: late.filter(([, b]) => !b.firstBook).length, bookedAfterLP: late.filter(([, b]) => b.firstBook > b.lp).length, dropped: late.filter(([, b]) => b.drops > 0).length, failed: late.filter(([, b]) => b.failed).length }
console.log(s)
