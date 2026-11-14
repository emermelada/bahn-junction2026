/** 6.5 Online competitor interval. Per bucket (option kind x pickup pool x delivery pool, with fallbacks) and per
 * day: lo = the highest price ratio (quote / list) that won, hi = the lowest that lost. Quote the midpoint; every
 * probeEvery-th quote in a bucket probes above it (a lost quote costs nothing). Trust and the dealer-share penalty
 * shift the ratio; the war guard (later) freezes learning, never lowers prices. */
import type { DeliveryOption, PriceRequest } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import type { Books } from "./books.ts"
import { dayOf } from "./books.ts"
import type { Geo } from "./geo.ts"

type Interval = { lo: number; hi: number; decided: number; quotes: number; day: number }

export class Pricing {
  readonly cfg: Cfg
  readonly geo: Geo
  readonly books: Books
  readonly buckets = new Map<string, Interval>()
  /** requestId -> the base ratio quoted and the buckets it belongs to (for the outcome). */
  readonly sent = new Map<string, { r: number; keys: string[] }>()
  frozen = false // war guard

  constructor(cfg: Cfg, geo: Geo, books: Books) {
    this.cfg = cfg
    this.geo = geo
    this.books = books
  }

  keys(request: PriceRequest, option: DeliveryOption): string[] {
    const leg = request.legs[0]!
    const p = this.geo.poolId(leg.pickup.placeId)
    const d = this.geo.poolId(leg.delivery.placeId)
    return [`${option.kind}|${p}|${d}`, `${option.kind}|${p}`, option.kind]
  }

  /** Today's interval of a bucket: yesterday's widened by morningWiden each new day; the Monday prior when new. */
  interval(key: string, day: number): Interval {
    const P = this.cfg.pricing
    let iv = this.buckets.get(key)
    if (!iv) {
      const parent = key.includes("|") ? this.buckets.get(key.split("|").slice(0, -1).join("|")) : undefined
      iv = { lo: parent?.lo ?? P.prior.lo, hi: parent?.hi ?? P.prior.hi, decided: 0, quotes: 0, day }
      this.buckets.set(key, iv)
    }
    while (iv.day < day) {
      iv.lo -= P.morningWiden
      iv.hi += P.morningWiden
      iv.decided = 0
      iv.day++
    }
    return iv
  }

  /** The quoted ratio for the slowest admitted option: interval midpoint (or probe) x trust + dealer-share penalty. */
  quoteRatio(request: PriceRequest, option: DeliveryOption, now: number, penalty: number): number {
    const r0 = this.ratio(request, option, now)
    const r = Math.min(this.cfg.pricing.clamp.hi + penalty, r0 * this.trustMult(request.dealerId) + penalty)
    this.sent.get(request.id)!.r = r
    return r
  }

  /** The base ratio for the slowest admitted option of a request at minute `now`. */
  ratio(request: PriceRequest, option: DeliveryOption, now: number): number {
    const P = this.cfg.pricing
    const day = dayOf(now)
    const keys = this.keys(request, option)
    const ivs = keys.map((k) => this.interval(k, day))
    const iv = ivs.find((x) => x.decided >= P.minBucketSamples) ?? ivs.at(-1)!
    let r = iv.lo + 0.5 * (iv.hi - iv.lo)
    const finest = ivs[0]!
    finest.quotes++
    if (P.probeEvery > 0 && finest.quotes % P.probeEvery === 0) r *= P.probeMult
    r = Math.min(P.clamp.hi, Math.max(P.clamp.lo, r))
    this.sent.set(request.id, { r, keys })
    return r
  }

  /** Multiplier on the ratio from dealer trust (+perOrder per on-time order, capped), when trust is on. */
  trustMult(dealer: string): number {
    if (!this.cfg.flags.trust) return 1
    const t = Math.min(this.cfg.trust.cap, this.books.trust.get(dealer) ?? 0)
    return 1 + this.cfg.trust.perOrder * t
  }

  outcome(requestId: string, won: boolean, at: number): void {
    const s = this.sent.get(requestId)
    if (!s) return
    this.sent.delete(requestId)
    if (this.frozen) return
    const day = dayOf(at)
    for (const key of s.keys) {
      const iv = this.interval(key, day)
      iv.decided++
      if (won) iv.lo = Math.max(iv.lo, s.r)
      else iv.hi = Math.min(iv.hi, s.r)
      if (iv.hi <= iv.lo) {
        const mid = (iv.lo + iv.hi) / 2
        iv.lo = mid - this.cfg.pricing.invertWiden
        iv.hi = mid + this.cfg.pricing.invertWiden
      }
    }
  }
}
