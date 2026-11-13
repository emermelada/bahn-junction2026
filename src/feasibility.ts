/** 6.1 Feasibility: can a driver near this car move it inside its windows, and how much slack is there?
 * Everything here is public: the request, the map, the roster, the rules on hours and deadlines. */
import type { DeliveryOption, Leg, OpeningHours, PriceRequest } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import { DAY, HOUR } from "./desk-api.ts"
import { dayOf, minuteOfDay, weekday } from "./books.ts"
import type { Geo } from "./geo.ts"
import type { NoteFacts } from "./notes.ts"

export type Tier = "A" | "B" | "C"

export type Feasibility = {
  kind: DeliveryOption["kind"]
  tier: Tier
  drive: number
  readyFrom: number
  latestArrival: number
  lastPickup: number
  slackHours: number
  flags: string[]
  reachPickup: number
  reachDelivery: number
}

const WORK_FROM = 7 * HOUR
const WORK_TO = 21 * HOUR

/** Driver-visible hours between two minutes: 07:00-21:00 Monday-Friday, Saturday 09:00-14:00, nothing on Sunday. */
export function driverHours(from: number, to: number): number {
  if (to <= from) return 0
  let hours = 0
  for (let day = dayOf(from); day <= dayOf(to); day++) {
    const wd = day % 7
    if (wd === 6) continue
    const open = day * DAY + (wd === 5 ? 9 * HOUR : WORK_FROM)
    const close = day * DAY + (wd === 5 ? 14 * HOUR : WORK_TO)
    hours += Math.max(0, Math.min(to, close) - Math.max(from, open)) / HOUR
  }
  return hours
}

/** The latest minute on `day` at which a site with these hours is open, or null when it is closed that day. */
export function closesOn(hours: OpeningHours | null, day: number): number | null {
  if (!hours) return null
  const wd = day % 7
  if (wd === 6) return null
  if (wd === 5) return hours.saturday ? day * DAY + hours.saturday.closes : null
  return hours.weekdays.includes(wd) ? day * DAY + hours.closes : null  // weekdays are 0 = Monday (checked in data)
}

export function opensOn(hours: OpeningHours | null, day: number): number | null {
  if (!hours) return null
  const wd = day % 7
  if (wd === 6) return null
  if (wd === 5) return hours.saturday ? day * DAY + hours.saturday.opens : null
  return day * DAY + hours.opens
}

/** Assesses one option of a request. `now` is the quote minute. */
export function assess(request: PriceRequest, option: DeliveryOption, now: number, geo: Geo, cfg: Cfg, facts: NoteFacts | null, snowy: (a: string, b: string, from: number, to: number) => boolean): Feasibility {
  const flags: string[] = []
  const legs = request.legs
  let worst: Feasibility | null = null
  for (const leg of legs) {
    const f = assessLeg(request, leg, option, now, geo, cfg, facts, snowy, flags)
    if (!worst || f.slackHours < worst.slackHours) worst = f
  }
  const f = worst!
  if (legs.length > 1) flags.push("trade_in")
  if (legs.some((l) => l.pickup.privateAddress)) flags.push("private_pickup")
  if (legs.some((l) => l.delivery.privateAddress)) flags.push("private_delivery")
  if (facts?.unparsed) flags.push("unparsed_note")
  if (facts?.manual) flags.push("manual")
  if (facts?.plates) flags.push("plates")
  if (weekday(f.readyFrom) === 4 && dayOf(option.deadline) > dayOf(f.readyFrom) + 2) flags.push("weekend_crossing")
  f.flags = [...new Set(flags)]
  f.tier = tierOf(f, option, legs, geo, cfg)
  return f
}

function assessLeg(request: PriceRequest, leg: Leg, option: DeliveryOption, now: number, geo: Geo, cfg: Cfg, facts: NoteFacts | null, snowy: (a: string, b: string, from: number, to: number) => boolean, flags: string[]): Feasibility {
  const P = leg.pickup.placeId
  const D = leg.delivery.placeId
  const readyFrom = Math.max(leg.pickup.window.from, facts?.readyFrom ?? 0, facts?.afterPayment ?? 0)
  let drive = geo.road(P, D)
  if (leg.car.electric && leg.car.chargePercent !== null && leg.car.chargePercent < 30 && geo.km(P, D) > 200) drive += 40
  if (facts?.plates) drive += 30
  let deadline = Math.min(option.deadline, facts?.deadline ?? Infinity)
  if (leg.delivery.privateAddress) deadline = Math.min(deadline, leg.delivery.window.to + 30)
  if (snowy(P, D, readyFrom, deadline)) { drive = Math.round(drive * cfg.gate.snowFactor); flags.push("snow") }
  // The delivery counts when the site is open: on the deadline day the real cutoff is the site's closing time.
  let latestArrival = deadline
  if (!leg.delivery.privateAddress) {
    const hours = facts?.deliveryHours ? { ...(leg.delivery.hours ?? { opens: 0, closes: DAY, weekdays: [0, 1, 2, 3, 4], saturday: null }), ...facts.deliveryHours } : leg.delivery.hours
    for (let day = dayOf(deadline); day >= dayOf(readyFrom); day--) {
      const close = closesOn(hours, day)
      if (close !== null) { latestArrival = Math.min(deadline, close); break }
    }
  }
  let lastPickup = latestArrival - drive
  if (!leg.pickup.privateAddress) {
    const hours = facts?.pickupHours ? { ...(leg.pickup.hours ?? { opens: 0, closes: DAY, weekdays: [0, 1, 2, 3, 4], saturday: null }), ...facts.pickupHours } : leg.pickup.hours
    // The last pickup must fall inside the pickup site's hours on some day: walk back to the latest such minute.
    for (let day = dayOf(lastPickup); day >= dayOf(readyFrom) - 1 && day >= 0; day--) {
      const close = closesOn(hours, day)
      const open = opensOn(hours, day)
      if (close === null || open === null) continue
      if (day === dayOf(lastPickup) && lastPickup >= open) { lastPickup = Math.min(lastPickup, close); break }
      if (day < dayOf(lastPickup)) { lastPickup = close; break }
    }
  } else lastPickup = Math.min(lastPickup, leg.pickup.window.to)
  const slackHours = driverHours(Math.max(now, readyFrom), lastPickup - cfg.gate.reachMarginMin)
  return { kind: option.kind, tier: "C", drive, readyFrom, latestArrival, lastPickup, slackHours, flags: [], reachPickup: geo.reach30(P).all, reachDelivery: geo.reach30(D).all }
}

function tierOf(f: Feasibility, option: DeliveryOption, legs: Leg[], geo: Geo, cfg: Cfg): Tier {
  const premium = legs.some((l) => l.car.premium)
  const manual = f.flags.includes("manual")
  const pick = legs[0]!.pickup.placeId
  const deli = legs[0]!.delivery.placeId
  const r30p = premium ? geo.reach30(pick).experienced : manual ? geo.reach30(pick).manual : geo.reach30(pick).all
  const r30d = premium ? geo.reach30(deli).experienced : manual ? geo.reach30(deli).manual : geo.reach30(deli).all
  const r80p = premium ? geo.reach80(pick).experienced : manual ? geo.reach80(pick).manual : geo.reach80(pick).all
  if (f.slackHours <= 0) return "C"
  let tier: Tier
  if (option.kind === "same_day") {
    const s = cfg.gate.sameDay
    tier = f.drive <= s.maxDriveMin && f.slackHours >= s.slackHours && r30p >= s.reach30Pickup ? "A" : "C"
  } else {
    const a = cfg.gate.tierA
    const b = cfg.gate.tierB
    if (f.slackHours >= a.slackHours && (r30p >= a.reach30Pickup || r30d >= a.reach30Delivery)) tier = "A"
    else if (f.slackHours >= b.slackHours && (r30p >= b.reach30Pickup || r80p >= b.reach80Pickup || r30d >= b.reach30Delivery)) tier = "B"
    else tier = "C"
  }
  const downgrades = ["private_pickup", "trade_in", "unparsed_note", "weekend_crossing"].filter((x) => f.flags.includes(x)).length
  for (let i = 0; i < downgrades; i++) tier = tier === "A" ? "B" : "C"
  return tier
}

export const planDayOf = (t: number): number => dayOf(t)
export { minuteOfDay }
