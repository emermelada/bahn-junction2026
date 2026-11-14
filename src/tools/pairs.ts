/** How many won orders could pair out-and-back (A->B, B'->A' with B' in pool(B), A' in pool(A)) on the same pickup day. */
import { readFileSync } from "node:fs"
import { Geo } from "../geo.ts"
const map = JSON.parse(readFileSync(new URL("../../data/map.json", import.meta.url), "utf8"))
for (const dir of process.argv.slice(2)) {
  const geo = new Geo(map, JSON.parse(readFileSync(`${dir}/roster.json`, "utf8")))
  const won = readFileSync(`${dir}/events.jsonl`, "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((e) => e.kind === "order_won" && e.order.legs.length === 1).map((e) => e.order)
  const day = (o: any) => Math.floor(Math.max(o.legs[0].pickup.window.from, 0) / 1440)
  const used = new Set<string>(); let pairs = 0, chainable = 0
  for (const a of won) {
    if (used.has(a.id)) continue
    const A = a.legs[0]
    for (const b of won) {
      if (b.id === a.id || used.has(b.id)) continue
      const B = b.legs[0]
      if (geo.road(A.delivery.placeId, B.pickup.placeId) > 30 || geo.road(B.delivery.placeId, A.pickup.placeId) > 30) continue
      if (Math.abs(day(a) - day(b)) > 0) continue
      const drive = geo.road(A.pickup.placeId, A.delivery.placeId) + geo.road(A.delivery.placeId, B.pickup.placeId) + geo.road(B.pickup.placeId, B.delivery.placeId)
      if (drive > 480) continue
      used.add(a.id); used.add(b.id); pairs++; break
    }
  }
  for (const a of won) for (const b of won) if (a !== b && geo.road(a.legs[0].delivery.placeId, b.legs[0].pickup.placeId) <= 30 && day(b) === day(a)) { chainable++; break }
  console.log(dir.split("/").pop(), "single-car won", won.length, "out-and-back pairs", pairs, "orders with a same-day chain successor", chainable)
}
