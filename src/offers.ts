/** 6.7 Direct offers: reach drivers a notification does not. Candidates, nearest first:
 *  relay     — a driver who will be free (end of one of our gigs) within relayRoadMin road minutes of the pickup;
 *  active    — a driver who viewed one of our gigs today and lives within activeKm of the pickup;
 *  homebound — a roster driver living within homeboundKm of the delivery and within activeKm of the pickup.
 * Quotas: perDriverPerDay offers a driver a day (one kept for after reserveAfter), 3 open per gig, none in quiet hours,
 * never to a driver who dropped one of our gigs today; licence and experience must fit. */
import type { OfferAction } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import type { Books } from "./books.ts"
import { dayOf } from "./books.ts"
import { DAY } from "./desk-api.ts"
import type { Geo } from "./geo.ts"

export type OfferNeed = { gigId: string; pickup: string; delivery: string; lastPickup: number; fee: number; premium: boolean; manual: boolean; reason: string }

export class Offers {
  readonly cfg: Cfg
  readonly geo: Geo
  readonly books: Books
  readonly open = new Map<string, Map<string, number>>() // gigId -> driverId -> minute sent
  readonly lastRound = new Map<string, number>() // gigId -> minute of the last offer round
  sent = 0
  accepted = 0

  constructor(cfg: Cfg, geo: Geo, books: Books) {
    this.cfg = cfg
    this.geo = geo
    this.books = books
  }

  quiet(now: number): boolean {
    const o = this.cfg.offers
    const mod = now - dayOf(now) * DAY
    return mod >= o.quietFrom || mod < o.quietTo
  }

  /** Offers for one gig now; empty when quiet, at quota, or no candidate. */
  round(need: OfferNeed, now: number, log?: (line: Record<string, unknown>) => void): OfferAction[] {
    const o = this.cfg.offers
    if (this.quiet(now)) return []
    const open = this.open.get(need.gigId) ?? new Map<string, number>()
    for (const [d, at] of open) if (now - at >= 10) open.delete(d) // the 10-minute window is over
    const slots = 3 - open.size
    if (slots <= 0) return []
    const today = dayOf(now)
    const scored = new Map<string, { score: number; kind: string }>()
    const consider = (id: string, score: number, kind: string) => {
      const best = scored.get(id)
      if (!best || score < best.score) scored.set(id, { score, kind })
    }
    // relay and active from the driver book
    for (const d of this.books.drivers.values()) {
      if (d.position && d.position.at <= Math.min(need.lastPickup - 60, now + 180) && d.position.at >= now - 240) {
        const road = this.geo.road(d.position.placeId, need.pickup)
        if (road <= o.relayRoadMin) consider(d.id, road, "relay")
      }
      if (d.viewedDay === today && d.home && this.geo.dist(d.home, need.pickup) <= o.activeKm) consider(d.id, this.geo.road(d.home, need.pickup) + 30, "active")
    }
    // homebound from the roster
    for (const [id, home] of this.geo.driverHome) {
      if (this.geo.dist(home, need.delivery) <= o.homeboundKm && this.geo.dist(home, need.pickup) <= o.activeKm) consider(id, this.geo.road(home, need.pickup) + 60, "homebound")
    }
    const out: OfferAction[] = []
    const ranked = [...scored.entries()].sort((a, b) => a[1].score - b[1].score)
    for (const [id, { kind }] of ranked) {
      if (out.length >= slots) break
      if (open.has(id)) continue
      const prof = this.geo.drivers.get(id)
      if (!prof) continue
      if (need.premium && !(prof.rating >= 4.8 && prof.completedGigs >= 50)) continue
      if (need.manual && prof.licence !== "manual") continue
      const d = this.books.driver(id)
      if (d.droppedDay === today) continue
      if (d.offersDay !== today) (d.offersDay = today), (d.offersToday = 0)
      const limit = now - dayOf(now) * DAY < o.reserveAfter ? o.perDriverPerDay - 1 : o.perDriverPerDay
      if (d.offersToday >= limit) continue
      d.offersToday++
      open.set(id, now)
      out.push({ type: "offer", gigId: need.gigId, driverId: id, feeCents: Math.max(1, Math.round(need.fee)) })
      log?.({ at: now, kind: "offer", gig: need.gigId, driver: id, cand: kind, fee: Math.round(need.fee), reason: need.reason })
    }
    if (out.length) {
      this.open.set(need.gigId, open)
      this.lastRound.set(need.gigId, now)
      this.sent += out.length
    }
    return out
  }

  answered(gigId: string, driverId: string, answer: string): void {
    this.open.get(gigId)?.delete(driverId)
    if (answer === "accepted") this.accepted++
  }
}
