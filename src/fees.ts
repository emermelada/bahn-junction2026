/** 6.4 Fees: flat-then-cliff. Open near the clearing fee, one small raise after an hour, then the cliff before the
 * last pickup; never more steps later, so drivers do not learn to wait. Bands by drivers within the notification
 * radius of the pickup; a two-sided learner moves each band's k within the week. */
import type { FeeStep, Order, PriceRequest } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import { DAY } from "./desk-api.ts"
import { dayOf, weekday } from "./books.ts"
import type { Geo } from "./geo.ts"

export type BandStats = { step1: number; cliff: number; resolved: number; bookings: number; drops: number }

export class Fees {
  readonly cfg: Cfg
  readonly geo: Geo
  readonly k: number[]
  readonly stats: BandStats[]
  readonly log?: (line: Record<string, unknown>) => void

  constructor(cfg: Cfg, geo: Geo, log?: (line: Record<string, unknown>) => void) {
    this.cfg = cfg
    this.geo = geo
    this.k = cfg.fees.kBands.map((b) => b.k)
    this.stats = cfg.fees.kBands.map(() => ({ step1: 0, cliff: 0, resolved: 0, bookings: 0, drops: 0 }))
    this.log = log
  }

  band(pickup: string): number {
    const r = this.geo.reach30(pickup).all
    return this.cfg.fees.kBands.findIndex((b) => r <= b.upTo)
  }

  /** The opening fee for `cars` of the order's legs. */
  open(order: Order, request: PriceRequest, cars: number): number {
    const f = this.cfg.fees
    const leg0 = order.legs[0]!
    const ref = (request.referenceFeeCents * cars) / order.legs.length
    let m = this.k[this.band(leg0.pickup.placeId)]!
    if (order.legs.some((l) => l.pickup.privateAddress || l.delivery.privateAddress)) m *= f.privateMult
    if (cars > 1) m *= f.extraLegMult ** (cars - 1)
    if (order.legs.some((l) => l.car.premium)) m *= f.premiumMult
    if (this.geo.reach30(leg0.delivery.placeId).all >= 40) m *= f.homeboundMult
    // Saturday or evening work needs a higher fee: when the last pickup falls on Saturday, or after 17:00.
    const lp = order.lastPickupAt
    if (weekday(lp) === 5 || (lp - dayOf(lp) * DAY >= 17 * 60 && dayOf(lp) === dayOf(leg0.pickup.window.from))) m *= f.eveningMult
    return Math.max(100, ref * m)
  }

  /** Flat-then-cliff schedule from `now` for a car whose last pickup is `lastPickup`. `base` = opening fee. */
  schedule(now: number, base: number, lastPickup: number, mult = 1): FeeStep[] {
    const steps: FeeStep[] = []
    for (const s of this.cfg.fees.steps) {
      let at = s.atMin >= 0 ? now + s.atMin : lastPickup + s.atMin
      at = this.dayShift(at)
      if (at < now) continue
      steps.push({ at, feeCents: Math.round(base * mult * s.mult) })
    }
    return normalize(now, steps, Math.round(base * mult))
  }

  /** Rescue at the deadline warning: one fee at the on-time cap at once. */
  rescue(now: number, base: number, price: number, ref: number, amber: boolean): FeeStep[] {
    return [{ at: now, feeCents: Math.round(this.capOnTime(base, price, ref, amber)) }]
  }

  capOnTime(base: number, price: number, ref: number, amber: boolean): number {
    const r = this.cfg.fees.rescue
    let cap = Math.max(1.7 * base, r.capRefMult * ref + r.capPriceAdd * price)
    if (amber) cap += r.amberPriceAdd * price
    return Math.max(base, Math.min(r.capPriceShare * price + (amber ? r.amberPriceAdd * price : 0), cap))
  }

  /** A doomed car (its last on-time pickup has passed): a calm schedule capped at doomedPriceCap x price, rising
   * to finalPriceCap x price - €1 only near the end of the world (an undelivered car costs more than that). */
  doomed(now: number, base: number, price: number, endsAt: number): FeeStep[] {
    const r = this.cfg.fees.rescue
    const calm = Math.max(base, Math.min(r.doomedPriceCap * price, 1.4 * base))
    const steps: FeeStep[] = [{ at: now, feeCents: Math.round(calm) }, { at: now + 120, feeCents: Math.round(Math.max(calm, Math.min(r.doomedPriceCap * price, 1.8 * base))) }]
    const late = endsAt - 2 * DAY
    if (late > now) steps.push({ at: this.dayShift(late), feeCents: Math.round(Math.max(calm, r.finalPriceCap * price - 100)) })
    else steps.push({ at: now + 240, feeCents: Math.round(Math.max(calm, r.finalPriceCap * price - 100)) })
    return normalize(now, steps, Math.round(calm))
  }

  /** Steps at night (nightFrom..nightTo) move to nightTo: no one reads them then and it teaches waiting. */
  dayShift(at: number): number {
    const f = this.cfg.fees
    const mod = at - dayOf(at) * DAY
    if (mod >= f.nightFrom) return dayOf(at) * DAY + DAY + f.nightTo
    if (mod < f.nightTo) return dayOf(at) * DAY + f.nightTo
    return at
  }

  // -------- learner (two-sided, per band)

  /** A gig was booked: at step 1 within 60 minutes of its posting, or later / higher. */
  booked(pickup: string, step1: boolean): void {
    const s = this.stats[this.band(pickup)]!
    s.bookings++
    s.resolved++
    if (step1) s.step1++
    this.learn(pickup)
  }

  /** A gig reached its cliff (the first step at or after lastPickup - 300) without a driver. */
  cliff(pickup: string): void {
    const s = this.stats[this.band(pickup)]!
    s.resolved++
    s.cliff++
    this.learn(pickup)
  }

  dropped(pickup: string): void {
    this.stats[this.band(pickup)]!.drops++
  }

  private learn(pickup: string): void {
    const b = this.band(pickup)
    const s = this.stats[b]!
    const L = this.cfg.fees.learn
    if (s.resolved < L.minSamples) return
    const step1 = s.step1 / s.resolved
    const cliff = s.cliff / s.resolved
    const drops = s.bookings ? s.drops / s.bookings : 0
    const before = this.k[b]!
    if (cliff >= L.cliffMax || drops > 0.25) this.k[b] = Math.min(L.kMax, before + L.delta)
    else if (step1 >= L.step1Target) this.k[b] = Math.max(L.kMin, before - L.delta)
    this.log?.({ kind: "fee_learn", band: b, step1, cliff, drops, k: this.k[b], before })
    this.stats[b] = { step1: 0, cliff: 0, resolved: 0, bookings: 0, drops: 0 }
  }
}

/** Sorted, strictly later, never falling; the first step at `now`. */
function normalize(now: number, steps: FeeStep[], first: number): FeeStep[] {
  const out: FeeStep[] = [{ at: now, feeCents: Math.max(1, first) }]
  for (const s of steps.sort((a, b) => a.at - b.at)) {
    const last = out.at(-1)!
    if (s.at <= last.at) { last.feeCents = Math.max(last.feeCents, s.feeCents); continue }
    if (s.feeCents <= last.feeCents) continue
    out.push({ at: s.at, feeCents: s.feeCents })
  }
  return out
}
