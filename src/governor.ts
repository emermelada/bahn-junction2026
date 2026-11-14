/** 6.6 On-time governor: a marginal admission test against a late budget. One late order needs nine on-time
 * ones to keep 90%; the final cannot be replayed, so the budget is 7% with a floored denominator. */
import type { Cfg } from "./config.ts"
import type { Books } from "./books.ts"
import type { Tier } from "./feasibility.ts"

export type Mode = "GREEN" | "AMBER" | "RED"

export class Governor {
  readonly cfg: Cfg
  readonly books: Books
  mode: Mode = "GREEN"

  constructor(cfg: Cfg, books: Books) {
    this.cfg = cfg
    this.books = books
  }

  /** Orders without a booked driver whose last pickup is within atRiskMin minutes. */
  atRisk(now: number, gigStatus: (orderId: string) => "none" | "open" | "booked"): number {
    let n = 0
    for (const book of this.books.orders.values()) {
      if (book.late || book.deliveredAll) continue
      if (gigStatus(book.order.id) === "booked") continue
      if (book.order.lastPickupAt - now < this.cfg.governor.atRiskMin) n++
    }
    return n
  }

  /** Headroom under the budget when the candidate with on-time probability p is added. */
  headroom(now: number, p: number, atRisk: number, extra = { late: 0, won: 0 }): number {
    const g = this.cfg.governor
    const won = this.books.wonCount + extra.won
    const late = this.books.lateCount + extra.late + g.atRiskWeight * atRisk + (1 - p)
    return g.lateBudget - late / Math.max(won + 1, g.minDenominator)
  }

  /** Updates the mode with hysteresis and tells whether a candidate of this tier is admitted now. */
  /** `extra` = expected late cars and expected wins of quotes still pending (sent, outcome not known). */
  admit(tier: Tier, now: number, atRisk: number, extra = { late: 0, won: 0 }): { ok: boolean; mode: Mode; headroom: number } {
    const g = this.cfg.governor
    const p = g.pOnTime[tier]
    const h = this.headroom(now, p, atRisk, extra)
    const hNoCandidate = this.headroom(now, 1, atRisk, extra)
    if (this.mode === "GREEN" && hNoCandidate <= g.amberHeadroom) this.mode = "AMBER"
    else if (this.mode === "AMBER" && hNoCandidate > g.greenHeadroom) this.mode = "GREEN"
    if (this.mode !== "RED" && hNoCandidate <= 0) this.mode = "RED"
    else if (this.mode === "RED" && hNoCandidate > g.amberHeadroom) this.mode = "AMBER"
    let ok: boolean
    if (this.mode === "GREEN") ok = tier !== "C" ? h >= 0 : g.admitC && h >= g.cMinHeadroom
    else if (this.mode === "AMBER") ok = tier === "A" && h >= 0
    else ok = tier === "A" && h >= 0
    // A safe order always helps the ratio: admit tier A even when the budget is tight, as long as it does not go negative.
    if (!ok && tier === "A" && h >= 0 && p >= 0.95) ok = true
    return { ok, mode: this.mode, headroom: h }
  }

  /** Calendar guard: from Friday noon only tier A (weekend supply is thin, Monday deadlines leave no second chance). */
  calendarMaxTier(now: number): Tier {
    return now >= this.cfg.governor.fridayTierAOnlyFrom && now < 7 * 24 * 60 ? "A" : "B"
  }
}
