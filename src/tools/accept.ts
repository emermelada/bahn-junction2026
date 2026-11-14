/** Booking rate per view by fee / reference fee, and booked ratio by hour. node src/tools/accept.ts runs/<run> */
import { readFileSync } from "node:fs"
const dir = process.argv[2]!
const ev = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
const acts = readFileSync(`${dir}/actions.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l))
const ref = new Map<string, number>(), legs = new Map<string, number>()
for (const e of ev) if (e.kind === "price_request") (ref.set(e.request.id, e.request.referenceFeeCents), legs.set(e.request.id, e.request.legs.length))
const gigRef = new Map<string, number>()
for (const a of acts) if (a.action?.type === "post" && a.result?.ok) {
  const o = a.action.stops[0].orderId; const cars = a.action.stops.filter((s: any) => s.kind === "pickup").length
  gigRef.set(a.result.id, (ref.get(o)! * cars) / legs.get(o)!)
}
const views = new Map<string, number>(), books = new Map<string, number>()
const key = (r: number) => (Math.floor(r * 10) / 10).toFixed(1)
const byHour: Record<number, number[]> = {}
for (const e of ev) {
  const r0 = gigRef.get(e.gigId)
  if (!r0) continue
  if (e.kind === "gig_viewed") { /* fee not in event; skip */ }
  if (e.kind === "gig_booked") { const r = e.feeCents / r0; books.set(key(r), (books.get(key(r)) ?? 0) + 1); (byHour[Math.floor((e.at % 1440) / 60)] ??= []).push(r) }
}
console.log("bookings by fee/ref:", [...books.entries()].sort().map(([k, v]) => `${k}:${v}`).join(" "))
console.log("median booked ratio by hour:", Object.entries(byHour).map(([h, rs]) => `${h}h n${rs.length} ${rs.sort((a, b) => a - b)[Math.floor(rs.length / 2)]!.toFixed(2)}`).join(" | "))
