/** The quote path: request -> QuoteAction. gate (6.1) -> capacity (6.2) -> governor (6.6) -> price (6.3 ladder;
 * 6.5 pricing later). All requests of one step are decided in one pass, easiest first, so reservations taken by
 * earlier requests count against later ones. Every request gets a quote: a non-admitted option goes at
 * decline.mult x list (a losing quote costs nothing; an unquoted request costs goodwill). */
import type { DeliveryOption, Order, PriceRequest, QuoteAction } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import type { Books } from "./books.ts"
import type { Capacity } from "./capacity.ts"
import type { Governor } from "./governor.ts"
import type { Geo } from "./geo.ts"
import type { Feasibility, Tier } from "./feasibility.ts"
import { assess } from "./feasibility.ts"
import { readNote } from "./notes.ts"
import { dayOf } from "./books.ts"

type Kind = DeliveryOption["kind"]
const SLOW_FIRST: Kind[] = ["within_3_days", "next_day", "same_day"]
const TIER_RANK: Record<Tier, number> = { A: 0, B: 1, C: 2 }

export type OptionDecision = { kind: Kind; tier: Tier; slack: number; day: number | null; admitted: boolean; why: string; price: number; list: number; flags?: string[]; drive?: number; r30?: number }

/** Price ratio source (pricing.ts later): returns the ratio to list for the slowest admitted option. */
export type RatioFn = (request: PriceRequest, option: DeliveryOption, f: Feasibility) => number

export class Quoter {
  readonly cfg: Cfg
  readonly geo: Geo
  readonly books: Books
  readonly capacity: Capacity
  readonly governor: Governor
  ratio: RatioFn = () => 1
  /** requestId -> planned pickup day per admitted option (for the commit on order_won). */
  readonly planned = new Map<string, Partial<Record<Kind, number>>>()
  /** requestId -> expected late share of the quote (1 - p of the worst admitted tier), while the outcome is unknown. */
  readonly pendingRisk = new Map<string, number>()

  constructor(cfg: Cfg, geo: Geo, books: Books, capacity: Capacity, governor: Governor) {
    this.cfg = cfg
    this.geo = geo
    this.books = books
    this.capacity = capacity
    this.governor = governor
  }

  decide(requests: PriceRequest[], now: number, atRisk: number, log?: (line: Record<string, unknown>) => void): QuoteAction[] {
    const { flags } = this.cfg
    const snowy = (a: string, b: string, from: number, to: number) => this.books.snow(a, b, from, to)
    const assessed = requests.map((request) => {
      const facts = flags.notes ? readNote(request.note, request) : null
      const fs = request.options.map((option) => ({ option, f: assess(request, option, now, this.geo, this.cfg, facts, snowy) }))
      const best = Math.min(...fs.map(({ f }) => (flags.gate ? TIER_RANK[f.tier] : 0)))
      const drive = Math.min(...fs.map(({ f }) => f.drive))
      return { request, fs, best, drive }
    })
    assessed.sort((a, b) => a.best - b.best || a.drive - b.drive || a.request.arrivedAt - b.request.arrivedAt)

    const out: QuoteAction[] = []
    for (const { request, fs } of assessed) {
      const leg0 = request.legs[0]!
      const pickup = leg0.pickup.placeId
      const satOk = (request.legs.every((l) => l.pickup.privateAddress || l.pickup.hours?.saturday)) && request.legs.every((l) => l.delivery.privateAddress || l.delivery.hours?.saturday)
      const maxTier = flags.governor ? this.governor.calendarMaxTier(now) : "B"
      const decisions: OptionDecision[] = []
      const planned: Partial<Record<Kind, number>> = {}
      let worstP = 1
      let mode = ""
      let headroom = 0
      for (const { option, f } of fs) {
        let tier: Tier = flags.gate ? f.tier : "A"
        let why = ""
        if (flags.gate && tier === "C") why = "tier C"
        if (!why && flags.gate && option.kind === "next_day" && f.drive > this.cfg.gate.nextDay.maxDriveMin) (tier = "C"), (why = "long next_day")
        if (!why && flags.gate && tier === "B" && this.braked(pickup, now)) (tier = "C"), (why = "pool brake")
        if (!why && flags.governor && maxTier === "A" && tier === "B") (tier = "C"), (why = "calendar")
        let day: number | null = dayOf(Math.max(now, f.readyFrom))
        if (!why && flags.capacity) {
          day = this.capacity.planDay(f, pickup, !!satOk, !!satOk)
          if (day === null) why = "no room"
          else if (this.capacity.globalShare(day) >= this.cfg.capacity.globalDayCap) why = "global cap"
        }
        if (!why && flags.governor) {
          const extra = this.pendingExtra()
          const g = this.governor.admit(tier, now, atRisk, extra)
          mode = g.mode
          headroom = g.headroom
          if (!g.ok) why = `governor ${g.mode}`
        }
        const admitted = why === ""
        if (admitted && day !== null) planned[option.kind] = day
        if (admitted) worstP = Math.min(worstP, this.cfg.governor.pOnTime[tier])
        decisions.push({ kind: option.kind, tier, slack: Math.round(f.slackHours * 10) / 10, day, admitted, why, price: 0, list: option.listPriceCents, flags: f.flags, drive: f.drive, r30: f.reachPickup })
      }

      // Prices: the ladder quotes every admitted option, slower cheaper; without it only the first admitted option.
      const prices: QuoteAction["prices"] = {}
      const admittedKinds = decisions.filter((d) => d.admitted).map((d) => d.kind)
      const slowest = SLOW_FIRST.find((k) => admittedKinds.includes(k))
      if (slowest) {
        const slowOpt = request.options.find((o) => o.kind === slowest)!
        const r = this.ratio(request, slowOpt, fs.find((x) => x.option.kind === slowest)!.f)
        const m = this.cfg.pricing.optionMult
        const chosen = flags.ladder ? admittedKinds : [decisions.find((d) => d.admitted)!.kind]
        for (const d of decisions) {
          if (chosen.includes(d.kind)) d.price = Math.round(d.list * r * (flags.ladder ? m[d.kind] / m[slowest] : 1))
          else if (flags.ladder || !d.admitted) d.price = Math.round(d.list * this.cfg.decline.mult)
        }
      } else for (const d of decisions) d.price = Math.round(d.list * this.cfg.decline.mult)
      for (const d of decisions) if (d.price > 0) prices[d.kind] = d.price

      if (slowest) {
        // One reservation per request: on the planned day of the option the dealer most likely takes (the slowest, cheapest).
        const day = planned[slowest]
        if (flags.capacity && day !== undefined) this.capacity.reserve(request.id, pickup, day)
        this.planned.set(request.id, planned)
        this.pendingRisk.set(request.id, 1 - worstP)
      }
      out.push({ type: "quote", requestId: request.id, prices })
      log?.({ at: now, kind: "quote", id: request.id, dealer: request.dealerId, batch: request.batchId, pickup, mode, headroom: Math.round(headroom * 1000) / 1000, opts: decisions })
    }
    return out
  }

  /** Pool brake: this pickup pool had >= poolBrake.warnings deadline warnings in the window on orders not yet delivered. */
  braked(pickup: string, now: number): boolean {
    const b = this.cfg.gate.poolBrake
    if (b.warnings <= 0) return false
    const pool = this.geo.poolId(pickup)
    let n = 0
    for (const book of this.books.orders.values()) {
      if (book.lastWarnAt < 0 || now - book.lastWarnAt > b.windowMin) continue
      if (this.geo.poolId(book.order.legs[0]!.pickup.placeId) === pool) n++
    }
    return n >= b.warnings
  }

  /** Expected late cars and wins among quotes sent whose outcome is not known yet. */
  pendingExtra(): { late: number; won: number } {
    let late = 0
    let won = 0
    for (const risk of this.pendingRisk.values()) {
      late += this.cfg.capacity.pWin * risk
      won += this.cfg.capacity.pWin
    }
    return { late, won }
  }

  onWon(order: Order): void {
    this.pendingRisk.delete(order.id)
    if (!this.cfg.flags.capacity) return
    const day = this.planned.get(order.id)?.[order.option]
    const pickup = order.legs[0]!.pickup.placeId
    if (day !== undefined) this.capacity.commitAt(order.id, pickup, day)
    else this.capacity.commitAt(order.id, pickup, dayOf(order.legs[0]!.pickup.window.from))
  }

  onLost(requestId: string): void {
    this.pendingRisk.delete(requestId)
    this.capacity.release(requestId)
  }

  onCancelled(orderId: string): void {
    this.pendingRisk.delete(orderId)
    this.capacity.release(orderId)
    this.capacity.free(orderId)
  }
}
