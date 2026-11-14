/** Every tunable of the desk, with its reason. All flags false = the kit's starter behaviour (regression test). */
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"

export type Cfg = {
  name: string
  flags: {
    gate: boolean       // 6.1 feasibility tiers; decline tier C by quoting decline.mult x list
    capacity: boolean   // 6.2 pool-day ledger with quote-time reservations
    ladder: boolean     // 6.3 quote every option, slower cheaper
    governor: boolean   // 6.6 late budget admission test
    fees: boolean       // 6.4 flat-then-cliff schedules + rescue ladder (else starter schedules)
    pricing: boolean    // 6.5 online competitor interval (else list price)
    trust: boolean      // 6.5 dealer-trust multiplier + anchor dealers
    guards: boolean     // 6.5 price-war / outage guards
    offers: boolean     // 6.7 direct offers
    bundles: boolean    // 6.8 multi-car gigs
    notes: boolean      // 6.8 note reader (else the starter's clock-time regex)
    triage: boolean     // dispatch: at-risk sweep, bounded rescue, straggler policy
  }
  decline: { mult: number }                       // decline = quote mult x list on every offered option (a losing quote costs nothing)
  gate: {
    tierA: { slackHours: number; reach30Pickup: number; reach30Delivery: number }
    tierB: { slackHours: number; reach30Pickup: number; reach80Pickup: number; reach30Delivery: number }
    sameDay: { maxDriveMin: number; slackHours: number; reach30Pickup: number }
    nextDay: { maxDriveMin: number }               // next_day with a longer drive is tier C (measured 82-85% on time at 4h+)
    poolBrake: { warnings: number; windowMin: number } // a pickup pool with this many deadline warnings on unbooked cars in the window: tier A only; warnings 0 = off
    reachMarginMin: number                         // minutes a driver needs to see a gig and get to the pickup
    downgrades: string[]                           // flags that each cost one tier
    snowFactor: number
  }
  capacity: { safety: number; active: number; active80: number; pWin: number; dealerShareMax: number; dealerShareMinRequests: number; dealerSharePenalty: number; globalDayCap: number }
  governor: { admitC: boolean; cMinHeadroom: number; cMinSlack: number; lateBudget: number; atRiskWeight: number; atRiskMin: number; minDenominator: number; pOnTime: { A: number; B: number; C: number }; amberHeadroom: number; greenHeadroom: number; fridayTierAOnlyFrom: number }
  fees: {
    kBands: { upTo: number; k: number }[]          // by reach30(pickup): 0-2 -> 1.35, 3-9 -> 1.15, 10-39 -> 1.00, 40+ -> 0.90
    homeboundMult: number; eveningMult: number; privateMult: number; extraLegMult: number; premiumMult: number
    steps: { atMin: number; mult: number }[]      // atMin >= 0: minutes after now; atMin < 0: minutes before lastPickup
    nightFrom: number; nightTo: number             // steps in [nightFrom, nightTo) (minutes of day) move to nightTo
    dropRaise: number
    eveningBefore: { at: number; mult: number }  // a step at this minute of the day before the last-pickup day (drivers plan tomorrow 18-20h); mult 0 = off
    learn: { step1Target: number; cliffMax: number; delta: number; kMin: number; kMax: number; minSamples: number }
    rescue: { warnMinBefore: number; capPriceShare: number; capRefMult: number; capPriceAdd: number; amberPriceAdd: number; doomedPriceCap: number; finalPriceCap: number }
  }
  pricing: {
    prior: { lo: number; hi: number }; morningWiden: number; invertWiden: number; probeEvery: number; probeMult: number; clamp: { lo: number; hi: number }
    optionMult: { within_3_days: number; next_day: number; same_day: number }
    minBucketSamples: number
  }
  trust: { perOrder: number; cap: number; anchorDealers: number; anchorReach30: number; anchorTierBonus: number }
  guards: { war: { minQuotes: number; minDealers: number; minPools: number; ratio: number; windows: number }; outage: { minQuotes: number; lift: number; add: number; capRatio: number }; until: number }
  offers: { reach30Trigger: number; openMinTrigger: number; warnMinBefore: number; relayRoadMin: number; activeKm: number; homeboundKm: number; feeMult: number; perDriverPerDay: number; reserveAfter: number; quietFrom: number; quietTo: number; costPt: number; ticketOut: number; ticketHome: number }
  bundles: { maxDriveMin: number; pairRoadMin: number; minSaving: number; feeMult: number } // bundle opening fee = (sum of the two single opening fees) x feeMult
  triage: { sweepEveryMin: number; warmMinBefore: number }
}

export const DEFAULT_CFG: Cfg = {
  name: "starter",
  flags: { gate: false, capacity: false, ladder: false, governor: false, fees: false, pricing: false, trust: false, guards: false, offers: false, bundles: false, notes: false, triage: false },
  decline: { mult: 3 },
  gate: {
    tierA: { slackHours: 24, reach30Pickup: 3, reach30Delivery: 10 },
    tierB: { slackHours: 8, reach30Pickup: 1, reach80Pickup: 20, reach30Delivery: 3 },
    sameDay: { maxDriveMin: 180, slackHours: 4, reach30Pickup: 5 },
    nextDay: { maxDriveMin: 100000 },
    poolBrake: { warnings: 0, windowMin: 1440 },
    reachMarginMin: 90,
    downgrades: ["private_pickup", "trade_in", "unparsed_note", "weekend_crossing"],
    snowFactor: 1.3,
  },
  capacity: { safety: 0.8, active: 0.3, active80: 0.1, pWin: 0.9, dealerShareMax: 0.6, dealerShareMinRequests: 5, dealerSharePenalty: 0.08, globalDayCap: 0.8 },
  governor: { admitC: false, cMinHeadroom: 0.03, cMinSlack: 2, lateBudget: 0.07, atRiskWeight: 0.5, atRiskMin: 240, minDenominator: 30, pOnTime: { A: 0.97, B: 0.92, C: 0.8 }, amberHeadroom: 0.03, greenHeadroom: 0.045, fridayTierAOnlyFrom: 4 * 24 * 60 + 12 * 60 },
  fees: {
    kBands: [{ upTo: 2, k: 1.35 }, { upTo: 9, k: 1.15 }, { upTo: 39, k: 1.0 }, { upTo: 1e9, k: 0.9 }],
    homeboundMult: 0.9, eveningMult: 1.15, privateMult: 1.15, extraLegMult: 1.1, premiumMult: 1.1,
    steps: [{ atMin: 0, mult: 1.0 }, { atMin: 60, mult: 1.15 }, { atMin: -300, mult: 1.4 }, { atMin: -180, mult: 1.7 }],
    nightFrom: 23 * 60, nightTo: 7 * 60,
    dropRaise: 1.15,
    eveningBefore: { at: 17 * 60 + 30, mult: 1.3 },
    learn: { step1Target: 0.7, cliffMax: 0.3, delta: 0.05, kMin: 0.8, kMax: 1.8, minSamples: 10 },
    rescue: { warnMinBefore: 240, capPriceShare: 1.5, capRefMult: 1.5, capPriceAdd: 0.25, amberPriceAdd: 0.25, doomedPriceCap: 1.0, finalPriceCap: 2.0 },
  },
  pricing: {
    prior: { lo: 1.15, hi: 1.4 }, morningWiden: 0.05, invertWiden: 0.03, probeEvery: 10, probeMult: 1.1, clamp: { lo: 1.05, hi: 1.6 },
    optionMult: { within_3_days: 1.0, next_day: 1.05, same_day: 1.15 },
    minBucketSamples: 3,
  },
  trust: { perOrder: 0.01, cap: 25, anchorDealers: 5, anchorReach30: 10, anchorTierBonus: 0.3 },
  guards: { war: { minQuotes: 12, minDealers: 4, minPools: 2, ratio: 0.45, windows: 2 }, outage: { minQuotes: 5, lift: 0.3, add: 0.2, capRatio: 1.6 }, until: 18 * 60 },
  offers: { reach30Trigger: 3, openMinTrigger: 150, warnMinBefore: 240, relayRoadMin: 90, activeKm: 80, homeboundKm: 30, feeMult: 1.05, perDriverPerDay: 3, reserveAfter: 12 * 60, quietFrom: 22 * 60 + 50, quietTo: 7 * 60, costPt: 0.3, ticketOut: 0.08, ticketHome: 0.16 },
  bundles: { maxDriveMin: 480, pairRoadMin: 30, minSaving: 0.15, feeMult: 0.8 },
  triage: { sweepEveryMin: 30, warmMinBefore: 360 },
}

/** Deep-merges a JSON file over the defaults. Unknown keys are kept (and hashed). */
export function loadCfg(path?: string): Cfg {
  if (!path) return structuredClone(DEFAULT_CFG)
  const file = JSON.parse(readFileSync(path, "utf8"))
  return merge(structuredClone(DEFAULT_CFG), file) as Cfg
}

function merge(base: any, over: any): any {
  if (Array.isArray(over) || typeof over !== "object" || over === null) return over
  for (const [k, v] of Object.entries(over)) {
    const current = base?.[k]
    base[k] = current && typeof current === "object" && !Array.isArray(current) ? merge(current, v) : v
  }
  return base
}

/** sha256 (first 12 hex) of the canonical JSON with sorted keys. */
export function cfgHash(cfg: Cfg): string {
  return createHash("sha256").update(canonical(cfg)).digest("hex").slice(0, 12)
}

export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical((value as any)[k])}`).join(",")}}`
  return JSON.stringify(value)
}
