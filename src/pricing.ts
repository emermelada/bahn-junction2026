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

  /** The quoted ratio for the slowest admitted option: interval midpoint (or probe) x trust + dealer-share penalty.
   * With pricing.model: the margin-optimal ratio under the fitted threshold model (see modelRatio).
   * The interval learns in trust-free units (the base ratio), so trusted dealers' wins do not lift everyone's price. */
  quoteRatio(request: PriceRequest, option: DeliveryOption, now: number, penalty: number, cost = 1): number {
    if (this.cfg.pricing.model.on) return this.modelRatio(request, option, now, cost)
    const r0 = this.ratio(request, option, now)
    const t = this.trustMult(request.dealerId)
    const r = Math.min(this.cfg.pricing.clamp.hi + penalty, r0 * t + penalty)
    this.sent.get(request.id)!.r = this.cfg.pricing.deflateTrust ? r / t : r
    return r
  }

  // ---- Model pricing -------------------------------------------------------------------------------------------
  // Measured on ~20 runs per gate seed (interval-censored fit): the ratio at which a request flips from won to lost
  // is lognormal, median ~1.36 x list, sigma ~0.23 (P(win) 0.91 at 1.0, 0.58 at 1.3, 0.34 at 1.5). Dealer trust t
  // scales the threshold by t. Per world, day, lane, option kind and dealer the median moves: learnt online by
  // stochastic gradient on the censored log-likelihood. The quote maximises P(win) x (ratio - cost + bonus), where
  // cost = the expected driver fee / list and bonus = the value of one more on-time order at a dealer still building trust.
  worldMu = NaN
  readonly dayMu = new Map<number, number>()
  readonly offsets = new Map<string, number>()
  readonly dealerSeen = new Map<string, number>()
  totalSeen = 0
  readonly modelSent = new Map<string, { y: number; keys: string[]; day: number }>()

  modelKeys(request: PriceRequest, option: DeliveryOption): string[] {
    const leg = request.legs[0]!
    return [`k|${option.kind}`, `l|${this.geo.poolId(leg.pickup.placeId)}|${this.geo.poolId(leg.delivery.placeId)}`, `d|${request.dealerId}`]
  }

  mu(keys: string[], day: number): number {
    const M = this.cfg.pricing.model
    if (Number.isNaN(this.worldMu)) this.worldMu = Math.log(M.median)
    return this.worldMu + (this.dayMu.get(day) ?? 0) + keys.reduce((s, k) => s + (this.offsets.get(k) ?? 0), 0)
  }

  /** P(win) at trust-free ratio y under median exp(mu). */
  pWin(y: number, mu: number): number {
    return 1 - phiCdf((Math.log(y) - mu) / this.cfg.pricing.model.sigma)
  }

  /** On-time orders the dealer is on its way to counting: counted trust + won orders not yet delivered. */
  trustSoon(dealer: string): number {
    let open = 0
    for (const b of this.books.orders.values()) if (b.order.dealerId === dealer && !b.deliveredAll && !b.late) open++
    return (this.books.trust.get(dealer) ?? 0) + open
  }

  modelRatio(request: PriceRequest, option: DeliveryOption, now: number, cost: number): number {
    const M = this.cfg.pricing.model
    const C = this.cfg.pricing.clamp
    const day = dayOf(now)
    const keys = this.modelKeys(request, option)
    const mu = this.mu(keys, day)
    const t = this.trustMult(request.dealerId)
    const seen = (this.dealerSeen.get(request.dealerId) ?? 0) + 1
    this.dealerSeen.set(request.dealerId, seen)
    this.totalSeen++
    // The value of one more on-time order at a dealer still building trust: +1% on the threshold of each of its
    // remaining requests, worth ~anchorPerRequest x list each (0.37 vs 0.18 x list at full vs no trust, /25).
    // In this request's list units; the dealer's remaining requests = its share so far x the week's remaining requests.
    const anchor = M.anchorBonus > 0 && seen >= M.anchorMinRequests && this.trustSoon(request.dealerId) < this.cfg.trust.cap
    const remaining = (seen / this.totalSeen) * Math.max(0, M.anchorWeekRequests - this.totalSeen)
    const bonus = anchor ? Math.min(M.anchorBonus, (M.anchorPerRequest * remaining * M.anchorAvgList) / option.listPriceCents) : 0
    let best = C.hi
    let bestV = -Infinity
    for (let x = C.lo; x <= M.hi + 1e-9; x += 0.01) {
      const v = this.pWin(x / t, mu) * (x - cost + bonus)
      if (v > bestV) (bestV = v), (best = x)
    }
    // Nothing to earn: decline (a losing quote costs nothing).
    if (bestV - this.pWin(best / t, mu) * bonus < M.minValue) return this.cfg.decline.mult
    this.modelSent.set(request.id, { y: best / t, keys, day })
    return best
  }

  modelOutcome(requestId: string, won: boolean): void {
    const s = this.modelSent.get(requestId)
    if (!s) return
    this.modelSent.delete(requestId)
    if (this.frozen) return
    const M = this.cfg.pricing.model
    const mu = this.mu(s.keys, s.day)
    const z = (Math.log(s.y) - mu) / M.sigma
    const pdf = Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI)
    const cdf = phiCdf(z)
    // d/dmu log-likelihood x sigma: a win says the threshold is above y (mu up), a loss below (mu down).
    const g = won ? pdf / Math.max(1e-6, 1 - cdf) : -pdf / Math.max(1e-6, cdf)
    const step = (eta: number) => eta * M.sigma * Math.max(-3, Math.min(3, g))
    this.worldMu += step(M.etaWorld)
    this.dayMu.set(s.day, (this.dayMu.get(s.day) ?? 0) + step(M.etaDay))
    for (const k of s.keys) {
      const eta = k.startsWith("l|") ? M.etaLane : k.startsWith("d|") ? M.etaDealer : M.etaKind
      const o = (this.offsets.get(k) ?? 0) * (1 - M.shrink) + step(eta)
      this.offsets.set(k, Math.max(-M.maxOffset, Math.min(M.maxOffset, o)))
    }
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
    if (this.cfg.pricing.model.on) return this.modelOutcome(requestId, won)
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

/** Standard normal CDF (Abramowitz-Stegun 7.1.26 erf). */
export function phiCdf(z: number): number {
  const x = Math.abs(z) / Math.SQRT2
  const t = 1 / (1 + 0.3275911 * x)
  const erf = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x)
  return z >= 0 ? 0.5 * (1 + erf) : 0.5 * (1 - erf)
}
