/** The v2 books: everything the modules read, kept up to date from events alone (so a restart rebuilds it
 * from world.events()). Pure bookkeeping, no decisions. */
import type { DeskEvent, DeskSnapshot, Gig, LedgerLine, Order, PriceRequest } from "./client/types.ts"
import { DAY } from "./desk-api.ts"
import type { Geo } from "./geo.ts"

export type GigBook = {
  id: string
  orderIds: string[]
  cars: number
  postedAt: number
  firstFee: number
  status: "open" | "booked" | "working" | "done" | "withdrawn"
  driverId: string | null
  bookedAt: number | null
  bookedFee: number | null
  lastStop: { placeId: string; at: number } | null // where and when the gig is planned to end
  stage: string // the fee stage the desk applied (fees.ts / dispatch.ts), "" = opening
}

export type DriverBook = {
  id: string
  home: string
  position: { placeId: string; at: number } | null // where our driver will be free, if they work one of our gigs
  viewedDay: number // last day the driver viewed one of our gigs (-1 = never)
  offersDay: number // day of the offer counter
  offersToday: number
  droppedDay: number // last day the driver dropped one of our gigs (-1 = never)
}

export type OrderBook = {
  order: Order
  request: PriceRequest
  wonAt: number
  late: boolean // sticky: once true, the order counts as late in the budget
  lateReason: string
  revenue: number
  refund: number
  fees: number
  deliveredAll: boolean
  warnings: number
}

export const dayOf = (t: number): number => Math.floor(t / DAY)
export const minuteOfDay = (t: number): number => t - dayOf(t) * DAY
export const weekday = (t: number): number => dayOf(t) % 7 // 0 = Monday
export const isWeekend = (t: number): boolean => weekday(t) >= 5

export class Books {
  readonly geo: Geo
  readonly requests = new Map<string, PriceRequest>()
  readonly orders = new Map<string, OrderBook>()
  readonly gigs = new Map<string, GigBook>()
  readonly drivers = new Map<string, DriverBook>()
  readonly lost = new Set<string>()
  readonly cancelled = new Set<string>()
  readonly trust = new Map<string, number>() // dealer -> on-time orders counted (cap applied by the reader)
  readonly dealerDay = new Map<string, { requests: number; wins: number; losses: number }>() // `${dealer}|${day}`
  readonly poolSeen = new Map<string, Set<string>>() // `${poolId}|${day}` -> distinct drivers seen viewing/booking
  readonly forecasts: { from: number; to: number; placeIds: Set<string> }[] = []
  wonCount = 0
  onTimeCount = 0
  lateCount = 0

  constructor(geo: Geo) {
    this.geo = geo
  }

  driver(id: string): DriverBook {
    let d = this.drivers.get(id)
    if (!d) {
      d = { id, home: this.geo.driverHome.get(id) ?? "", position: null, viewedDay: -1, offersDay: -1, offersToday: 0, droppedDay: -1 }
      this.drivers.set(id, d)
    }
    return d
  }

  /** Seeds the gig book from a snapshot (rejoin). Events then keep it current. */
  seed(snapshot: DeskSnapshot): void {
    for (const gig of snapshot.gigs) this.gigFromSnapshot(gig)
    for (const position of snapshot.driverPositions) {
      const d = this.driver(position.driverId)
      d.position = { placeId: position.placeId, at: snapshot.now }
    }
  }

  gigFromSnapshot(gig: Gig): void {
    const existing = this.gigs.get(gig.id)
    const cars = gig.stops.filter((s) => s.kind === "pickup").length
    const last = gig.stops.at(-1)
    const book: GigBook = existing ?? {
      id: gig.id,
      orderIds: [...new Set(gig.stops.map((s) => s.orderId))],
      cars,
      postedAt: gig.postedAt,
      firstFee: gig.schedule[0]?.feeCents ?? gig.feeCents,
      status: gig.status,
      driverId: gig.driverId,
      bookedAt: null,
      bookedFee: gig.driverId ? gig.feeCents : null,
      lastStop: last ? { placeId: this.placeOf(last.orderId, last.leg, last.kind), at: 0 } : null,
      stage: "",
    }
    book.status = gig.status
    book.driverId = gig.driverId
    this.gigs.set(gig.id, book)
  }

  placeOf(orderId: string, leg: number, kind: "pickup" | "delivery"): string {
    const order = this.orders.get(orderId)?.order ?? null
    const l = order?.legs[leg] ?? this.requests.get(orderId)?.legs[leg]
    return l ? (kind === "pickup" ? l.pickup.placeId : l.delivery.placeId) : ""
  }

  /** Registers a gig the world accepted for a post the desk made. */
  posted(gigId: string, orderIds: string[], cars: number, postedAt: number, firstFee: number, lastPlace: string, stage: string): void {
    this.gigs.set(gigId, { id: gigId, orderIds, cars, postedAt, firstFee, status: "open", driverId: null, bookedAt: null, bookedFee: null, lastStop: { placeId: lastPlace, at: 0 }, stage })
  }

  track(event: DeskEvent): void {
    const day = dayOf(event.at)
    switch (event.kind) {
      case "price_request": {
        this.requests.set(event.request.id, event.request)
        const key = `${event.request.dealerId}|${day}`
        const d = this.dealerDay.get(key) ?? { requests: 0, wins: 0, losses: 0 }
        d.requests++
        this.dealerDay.set(key, d)
        break
      }
      case "order_won": {
        const request = this.requests.get(event.order.id)
        if (!request) break
        if (!this.orders.has(event.order.id)) {
          this.orders.set(event.order.id, { order: event.order, request, wonAt: event.at, late: false, lateReason: "", revenue: 0, refund: 0, fees: 0, deliveredAll: false, warnings: 0 })
          this.wonCount++
          const key = `${event.order.dealerId}|${dayOf(request.arrivedAt)}`
          const d = this.dealerDay.get(key) ?? { requests: 0, wins: 0, losses: 0 }
          d.wins++
          this.dealerDay.set(key, d)
        } else this.orders.get(event.order.id)!.order = event.order
        break
      }
      case "order_lost": {
        this.lost.add(event.requestId)
        const request = this.requests.get(event.requestId)
        if (request) {
          const key = `${request.dealerId}|${dayOf(request.arrivedAt)}`
          const d = this.dealerDay.get(key) ?? { requests: 0, wins: 0, losses: 0 }
          d.losses++
          this.dealerDay.set(key, d)
        }
        break
      }
      case "order_changed": {
        const book = this.orders.get(event.order.id)
        if (book) book.order = event.order
        break
      }
      case "order_cancelled": {
        const book = this.orders.get(event.orderId)
        if (book) {
          this.cancelled.add(event.orderId)
          this.orders.delete(event.orderId)
          this.wonCount--
          if (book.late) this.lateCount--
        }
        for (const g of event.gigs) {
          const gig = this.gigs.get(g.gigId)
          if (gig && (g.outcome === "withdrawn" || g.outcome === "released")) gig.status = "withdrawn"
        }
        break
      }
      case "gig_viewed": {
        const d = this.driver(event.driverId)
        d.viewedDay = day
        const gig = this.gigs.get(event.gigId)
        if (gig) this.seen(gig, d, day)
        break
      }
      case "gig_booked": {
        const gig = this.gigs.get(event.gigId)
        const d = this.driver(event.driverId)
        if (gig) {
          gig.status = "booked"
          gig.driverId = event.driverId
          gig.bookedAt = event.at
          gig.bookedFee = event.feeCents
          this.seen(gig, d, day)
          d.position = gig.lastStop ? { placeId: gig.lastStop.placeId, at: this.plannedEnd(gig) } : d.position
        }
        break
      }
      case "offer_answered": {
        if (event.answer === "accepted") {
          const gig = this.gigs.get(event.gigId)
          if (gig && gig.status === "open") {
            gig.status = "booked"
            gig.driverId = event.driverId
            gig.bookedAt = event.at
          }
        }
        break
      }
      case "gig_dropped":
      case "no_show": {
        const gig = this.gigs.get(event.gigId)
        if (gig) {
          gig.status = "open"
          gig.driverId = null
          gig.bookedAt = null
        }
        const d = this.driver(event.driverId)
        d.droppedDay = day
        d.position = null
        break
      }
      case "gig_started": {
        const gig = this.gigs.get(event.gigId)
        if (gig) gig.status = "working"
        break
      }
      case "picked_up": {
        const d = this.driver(event.gigId ? this.gigs.get(event.gigId)?.driverId ?? "" : "")
        if (d.id) d.position = { placeId: event.placeId, at: event.at }
        break
      }
      case "delivered": {
        const gig = this.gigs.get(event.gigId)
        const d = gig?.driverId ? this.driver(gig.driverId) : null
        if (d) d.position = { placeId: event.placeId, at: event.at }
        const book = this.orders.get(event.orderId)
        if (book) {
          book.order.deliveredAt[event.leg] = event.at
          book.deliveredAll = book.order.deliveredAt.every((t) => t !== null)
          if (gig && gig.orderIds.every((id) => this.orders.get(id)?.deliveredAll ?? true)) gig.status = "done"
          if (event.at > book.order.deadline) this.markLate(book, "delivered_late")
        }
        break
      }
      case "gig_expired": {
        const gig = this.gigs.get(event.gigId)
        if (gig) gig.status = "withdrawn"
        break
      }
      case "deadline_close": {
        const book = this.orders.get(event.orderId)
        if (book) book.warnings++
        break
      }
      case "forecast":
        this.forecasts.push({ from: event.from, to: event.to, placeIds: new Set(event.placeIds) })
        break
      case "ledger":
        this.ledger(event.line)
        break
    }
  }

  private seen(gig: GigBook, d: DriverBook, day: number): void {
    const pool = this.geo.poolId(d.home)
    const key = `${pool}|${day}`
    let set = this.poolSeen.get(key)
    if (!set) this.poolSeen.set(key, (set = new Set()))
    set.add(d.id)
  }

  /** When a booked gig is planned to end: the road minutes of its stops from the first pickup window. */
  plannedEnd(gig: GigBook): number {
    const order = this.orders.get(gig.orderIds[0] ?? "")
    if (!order || !gig.lastStop) return 0
    let t = Math.max(order.order.legs[0]!.pickup.window.from, gig.bookedAt ?? 0)
    let at = order.order.legs[0]!.pickup.placeId
    for (const id of gig.orderIds) {
      const o = this.orders.get(id)
      if (!o) continue
      for (const leg of o.order.legs) {
        t += this.geo.road(at, leg.pickup.placeId) + this.geo.road(leg.pickup.placeId, leg.delivery.placeId) + 15
        at = leg.delivery.placeId
      }
    }
    return t
  }

  private ledger(line: LedgerLine): void {
    if (line.orderId) {
      const book = this.orders.get(line.orderId)
      if (book) {
        if (line.kind === "revenue") book.revenue += line.cents
        else if (line.kind === "late_refund") { book.refund += line.cents; this.markLate(book, "late_refund") }
        else if (line.kind === "undelivered_penalty") { book.refund += line.cents; this.markLate(book, "undelivered") }
        else if (line.kind === "driver_fee") book.fees += line.cents
      }
      if (line.kind === "revenue" && book && !book.late) {
        // An order's revenue line with no late refund is an order on time (RULES, Dealer trust). The refund line,
        // when there is one, comes with the revenue; markLate handles the order of arrival either way.
        this.onTimeCount++
        this.trust.set(book.order.dealerId, (this.trust.get(book.order.dealerId) ?? 0) + 1)
      }
    } else if (line.gigId && line.kind === "driver_fee") {
      const gig = this.gigs.get(line.gigId)
      if (gig) for (const id of gig.orderIds) { const b = this.orders.get(id); if (b) b.fees += line.cents / gig.orderIds.length }
    }
  }

  markLate(book: OrderBook, reason: string): void {
    if (book.late) return
    book.late = true
    book.lateReason = reason
    this.lateCount++
    const dealer = book.order.dealerId
    // A late order halves that dealer's trust count, rounded down; and if the revenue line was counted on time
    // before the refund line arrived, take that count back.
    if (book.revenue > 0 && reason === "late_refund") { this.onTimeCount--; this.trust.set(dealer, (this.trust.get(dealer) ?? 1) - 1) }
    this.trust.set(dealer, Math.floor((this.trust.get(dealer) ?? 0) / 2))
  }

  /** Snow factor for a leg in a window: 1 when no forecast covers either place in [from, to]. */
  snow(placeA: string, placeB: string, from: number, to: number): boolean {
    return this.forecasts.some((f) => f.from <= to && f.to >= from && (f.placeIds.has(placeA) || f.placeIds.has(placeB)))
  }

  dealerShareToday(dealer: string, day: number): { requests: number; wins: number } {
    const d = this.dealerDay.get(`${dealer}|${day}`)
    return { requests: d?.requests ?? 0, wins: d?.wins ?? 0 }
  }
}
