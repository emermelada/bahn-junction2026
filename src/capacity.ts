/** 6.2 Capacity: a pool-day ledger with reservations taken at quote time, so a batch of requests decided in one
 * step, and the 15 minutes before the dealer answers, cannot overbook the drivers of a town. */
import type { Cfg } from "./config.ts"
import { DAY } from "./desk-api.ts"
import type { Books } from "./books.ts"
import { dayOf, weekday } from "./books.ts"
import type { Geo } from "./geo.ts"
import type { Feasibility } from "./feasibility.ts"

export type Reservation = { pool: string; day: number; weight: number }

export class Capacity {
  readonly cfg: Cfg
  readonly geo: Geo
  readonly books: Books
  readonly pending = new Map<string, Reservation>() // requestId -> reservation
  readonly committed = new Map<string, Reservation>() // orderId -> reservation
  readonly load = new Map<string, number>() // `${pool}|${day}` -> weighted cars

  constructor(cfg: Cfg, geo: Geo, books: Books) {
    this.cfg = cfg
    this.geo = geo
    this.books = books
  }

  key(pool: string, day: number): string {
    return `${pool}|${day}`
  }

  /** Cars per day the pool's drivers can move for us: SAFETY x (ACTIVE x reach30 + ACTIVE80 x (reach80 - reach30)).
   * From the second day on, ACTIVE for a pool is at least the share of its roster we saw viewing or booking the day before. */
  cap(place: string, day: number): number {
    const c = this.cfg.capacity
    const r30 = this.geo.reach30(place).all
    const r80 = this.geo.reach80(place).all
    let active = c.active
    const seen = this.books.poolSeen.get(this.key(this.geo.poolId(place), day - 1))?.size ?? 0
    if (r30 > 0 && seen > 0) active = Math.max(active, Math.min(1, seen / r30))
    return c.safety * (active * r30 + c.active80 * Math.max(0, r80 - r30))
  }

  loadOf(place: string, day: number): number {
    return this.load.get(this.key(this.geo.poolId(place), day)) ?? 0
  }

  room(place: string, day: number): number {
    return this.cap(place, day) - this.loadOf(place, day)
  }

  /** The business day on which we plan to collect the car for this option: the allowed day with the most room.
   * Saturday only when both sites open on Saturday; never Sunday. Null when no day has room. */
  planDay(f: Feasibility, pickup: string, pickupSaturday: boolean, deliverySaturday: boolean): number | null {
    const first = dayOf(Math.max(f.readyFrom, 0))
    const last = dayOf(f.lastPickup)
    let best: number | null = null
    let bestRoom = 0
    for (let day = first; day <= last; day++) {
      const wd = day % 7
      if (wd === 6) continue
      if (wd === 5 && !(pickupSaturday && deliverySaturday)) continue
      const room = this.room(pickup, day)
      if (room > bestRoom) { best = day; bestRoom = room }
    }
    return best
  }

  reserve(requestId: string, pickup: string, day: number): void {
    const pool = this.geo.poolId(pickup)
    const r: Reservation = { pool, day, weight: this.cfg.capacity.pWin }
    this.release(requestId)
    this.pending.set(requestId, r)
    this.add(r, +1)
  }

  release(requestId: string): void {
    const r = this.pending.get(requestId)
    if (!r) return
    this.pending.delete(requestId)
    this.add(r, -1)
  }

  /** On order_won: the reservation becomes a committed car (weight 1) until a driver books it or it is delivered. */
  commit(orderId: string): void {
    const r = this.pending.get(orderId)
    if (!r) return
    this.pending.delete(orderId)
    this.add(r, -1)
    const c: Reservation = { pool: r.pool, day: r.day, weight: 1 }
    this.committed.set(orderId, c)
    this.add(c, +1)
  }

  /** When a driver books the car (or the order ends) its load is given back: the driver is now accounted for. */
  free(orderId: string): void {
    const c = this.committed.get(orderId)
    if (!c) return
    this.committed.delete(orderId)
    this.add(c, -1)
  }

  private add(r: Reservation, sign: number): void {
    const k = this.key(r.pool, r.day)
    this.load.set(k, Math.max(0, (this.load.get(k) ?? 0) + sign * r.weight))
  }

  /** Daily total across pools, as a share of the summed caps; the global cap guards against many pools each at their edge. */
  globalShare(day: number): number {
    let load = 0
    let cap = 0
    const seen = new Set<string>()
    for (const place of this.geo.places) {
      const pool = this.geo.poolId(place)
      if (seen.has(pool)) continue
      seen.add(pool)
      load += this.load.get(this.key(pool, day)) ?? 0
      cap += this.cap(place, day)
    }
    return cap > 0 ? load / cap : 1
  }

  /** The dealer-share penalty on the price ratio: +penalty once we won most of a dealer's requests today. */
  dealerPenalty(dealer: string, now: number): number {
    const c = this.cfg.capacity
    const { requests, wins } = this.books.dealerShareToday(dealer, dayOf(now))
    return requests >= c.dealerShareMinRequests && wins / requests > c.dealerShareMax ? c.dealerSharePenalty : 0
  }
}

export const isBusinessDay = (t: number): boolean => weekday(t) < 5
export { DAY }
