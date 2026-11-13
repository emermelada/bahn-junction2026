/** The desk: books + decisions. With every flag off it is a faithful port of the kit's starter (the regression
 * test reproduces the starter's score to the cent). Each flag swaps one decision for a module of PLAN.md §6. */
import type { Action, ActionResult, DeskEvent, DeskSnapshot, FeeStep, Note, Order, PostAction, PriceRequest, StopRef, TimeWindow } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import type { Desk, DeskContext } from "./desk-api.ts"
import { DAY, HOUR } from "./desk-api.ts"
import { Geo } from "./geo.ts"

/** How to post a leg again after a failed visit. */
export type Retry = { pickupFrom: number; manualLicence: boolean; plates: boolean }
const FIRST_TRY: Retry = { pickupFrom: 0, manualLicence: false, plates: false }

export function createDesk(cfg: Cfg, ctx: DeskContext): Desk {
  return new V2Desk(cfg, ctx)
}

export class V2Desk implements Desk {
  readonly cfg: Cfg
  readonly ctx: DeskContext
  readonly geo: Geo
  readonly level: number
  now = 0
  readonly outbox: Action[] = []
  // --- books (the starter's) ---
  readonly requests = new Map<string, PriceRequest>()
  readonly orders = new Map<string, Order>() // won and not cancelled
  readonly legGigs = new Map<string, Map<number, string>>() // order id -> leg -> gig that carries it
  readonly booked = new Set<string>() // gigs a driver holds now
  readonly posts = new Map<string, PostAction>() // gig id -> the post that made it
  readonly urgent = new Set<string>() // orders whose deadline warning has come
  // --- books (v2) ---
  readonly quoted = new Set<string>() // requests answered (so rejoin does not quote twice)

  constructor(cfg: Cfg, ctx: DeskContext) {
    this.cfg = cfg
    this.ctx = ctx
    this.level = ctx.level
    this.geo = new Geo(ctx.map, ctx.roster)
  }

  // ------------------------------------------------------------------ lifecycle

  async rejoin(snapshot: DeskSnapshot, history: DeskEvent[]): Promise<void> {
    this.now = snapshot.now
    const posted = Map.groupBy(snapshot.gigs, (gig) => gig.stops[0]!.orderId)
    for (const gig of snapshot.gigs) if (["booked", "working", "done"].includes(gig.status)) this.booked.add(gig.id)
    for (const gig of snapshot.gigs) if (["open", "booked", "working"].includes(gig.status)) this.carry({ type: "post", stops: gig.stops, audience: gig.audience, schedule: gig.schedule }, gig.id)
    for (const event of history) if (event.kind === "price_request") this.requests.set(event.request.id, event.request)
    for (const event of history) if (event.kind === "deadline_close") this.urgent.add(event.orderId)
    for (const order of snapshot.orders) if (this.requests.has(order.id) && order.status !== "cancelled") this.orders.set(order.id, order)
    for (const order of this.orders.values()) if (order.status === "waiting" && this.gigsOf(order.id).length === 0) await this.post(order, undelivered(order))
    for (const event of history) {
      const order = "orderId" in event ? this.orders.get(event.orderId) : undefined
      if (!order) continue
      if (event.kind === "visit_failed" && order.deliveredAt[event.leg] === null) {
        const later = (posted.get(order.id) ?? []).filter((gig) => gig.postedAt >= event.at && gig.id !== event.gigId)
        if (!later.some((gig) => gig.stops.some((stop) => stop.leg === event.leg))) await this.retry(order.id, event.leg, event.reason)
      }
    }
    for (const request of snapshot.openRequests) this.quote(request)
  }

  async handle(event: DeskEvent): Promise<void> {
    this.now = Math.max(this.now, event.at)
    if (event.kind === "price_request") this.quote(event.request)
    else if (event.kind === "order_won") await this.win(event.order)
    else if (event.kind === "order_changed") await this.change(event.order)
    else if (event.kind === "order_cancelled") for (const books of [this.orders, this.legGigs]) books.delete(event.orderId)
    else if (event.kind === "visit_failed") await this.retry(event.orderId, event.leg, event.reason)
    else if (event.kind === "gig_expired") this.repost(event.gigId)
    else if (event.kind === "deadline_close") await this.raise(event.orderId)
    else if (event.kind === "gig_booked") this.booked.add(event.gigId)
    else if (event.kind === "gig_dropped" || event.kind === "no_show") this.booked.delete(event.gigId)
    else if (event.kind === "delivered") this.delivered(event.orderId, event.leg, event.at)
  }

  async tick(now: number): Promise<void> {
    this.now = Math.max(this.now, now)
  }

  drain(): Action[] {
    return this.outbox.splice(0)
  }

  onResults(actions: Action[], results: ActionResult[]): void {
    this.readResults(actions, results)
  }

  nextWake(): number | null {
    return null
  }

  // ------------------------------------------------------------------ the starter's decisions

  delivered(orderId: string, leg: number, at: number): void {
    this.legGigs.get(orderId)?.delete(leg)
    const order = this.orders.get(orderId)
    if (order) order.deliveredAt[leg] = at
  }

  quote(request: PriceRequest): void {
    this.requests.set(request.id, request)
    if (this.quoted.has(request.id)) return
    this.quoted.add(request.id)
    const first = request.options[0]!
    this.outbox.push({ type: "quote", requestId: request.id, prices: { [first.kind]: first.listPriceCents } })
  }

  async win(order: Order): Promise<void> {
    if (!this.requests.has(order.id) || this.orders.has(order.id)) return
    this.orders.set(order.id, order)
    await this.post(order, undelivered(order))
  }

  async change(order: Order): Promise<void> {
    if (!this.orders.has(order.id)) return
    this.orders.set(order.id, order)
    if (await this.withdraw(order.id)) await this.post(order, undelivered(order))
  }

  /** Posts a gig again when one of its windows ended before a driver booked it. */
  repost(gigId: string): void {
    const action = this.posts.get(gigId)
    if (!action || !action.stops.some(({ orderId, leg }) => this.legGigs.get(orderId)?.get(leg) === gigId)) return
    for (const { orderId, leg } of action.stops) this.legGigs.get(orderId)?.delete(leg)
    const order = this.orders.get(action.stops[0]!.orderId)
    if (!order) return
    this.outbox.push({ ...action, stops: withoutWindows(action.stops, Infinity), schedule: this.feesFor(order, pickups(action)) })
  }

  /** From the order's deadline warning on, its gigs that no driver holds go at the steep fees. */
  async raise(orderId: string): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.urgent.add(orderId)
    await this.sendPostOf(orderId)
    for (const gigId of this.gigsOf(orderId)) {
      if (!this.booked.has(gigId)) this.outbox.push({ type: "reprice", gigId, schedule: this.feesFor(order, pickups(this.posts.get(gigId)!)) })
    }
  }

  feesFor(order: Order, cars: number): FeeStep[] {
    const fee = (this.requests.get(order.id)!.referenceFeeCents * cars) / order.legs.length
    return this.urgent.has(order.id) ? steep(this.now, fee, this.level) : rising(this.now, fee, this.level)
  }

  async retry(orderId: string, leg: number, reason: string): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.legGigs.get(orderId)?.delete(leg)
    const carNotThere = reason === "not_ready" || reason === "closed"
    const pickupFrom = carNotThere ? retryFrom(order, this.requests.get(orderId)!, leg, this.now) : 0
    await this.post(order, [leg], { pickupFrom, manualLicence: reason === "licence", plates: reason === "no_plates" })
  }

  async post(order: Order, legs: number[], retry = FIRST_TRY): Promise<void> {
    const audience = { experienced: order.legs.some((leg) => leg.car.premium), manualLicence: retry.manualLicence }
    const stops = withoutWindows(stopsFor(order, legs, this.requests.get(order.id)!.note, retry), this.now)
    this.outbox.push({ type: "post", stops, audience, schedule: this.feesFor(order, legs.length) })
    if (legs.length === 1) return
    // A trade-in over the 12-hour limit for a gig with two cars goes as one gig per car.
    await this.send()
    if (this.gigsOf(order.id).length === 0) for (const leg of legs) await this.post(order, [leg], retry)
  }

  gigsOf(orderId: string): string[] {
    return [...new Set(this.legGigs.get(orderId)?.values())]
  }

  carry(action: PostAction, gigId: string): void {
    for (const { orderId, leg } of action.stops) this.legGigs.set(orderId, (this.legGigs.get(orderId) ?? new Map()).set(leg, gigId))
    this.posts.set(gigId, action)
  }

  async withdraw(orderId: string): Promise<boolean> {
    await this.sendPostOf(orderId)
    const gigs = this.gigsOf(orderId)
    if (gigs.some((gigId) => this.booked.has(gigId))) return false
    this.legGigs.delete(orderId)
    for (const gigId of gigs) this.outbox.push({ type: "withdraw", gigId })
    return true
  }

  async sendPostOf(orderId: string): Promise<void> {
    if (this.outbox.some((action) => action.type === "post" && action.stops[0]!.orderId === orderId)) await this.send()
  }

  /** Sends the outbox now, through the runner (the starter's send()). */
  async send(): Promise<void> {
    const actions = this.outbox.splice(0)
    if (actions.length > 0) this.readResults(actions, await this.ctx.act(actions))
  }

  readResults(actions: Action[], results: ActionResult[]): void {
    actions.forEach((action, i) => {
      if (action.type === "post" && results[i]?.ok) this.carry(action, (results[i] as { ok: true; id: string }).id)
    })
  }
}

// ------------------------------------------------------------------ the starter's helpers (verbatim semantics)

export function retryFrom(order: Order, request: PriceRequest, leg: number, now: number): number {
  const promised = request.options.find((option) => option.kind === order.option)?.deadline ?? order.deadline
  const delay = Math.max(0, order.deadline - promised)
  return Math.max(now + 2 * HOUR, order.legs[leg]!.pickup.window.from + delay)
}

export const undelivered = (order: Order): number[] => order.legs.map((_, leg) => leg).filter((leg) => order.deliveredAt[leg] === null)

export const pickups = (action: PostAction): number => action.stops.filter((stop) => stop.kind === "pickup").length

export const withoutWindows = (stops: StopRef[], before: number): StopRef[] =>
  stops.map((stop) => (stop.window && stop.window.to < before ? { ...stop, window: undefined } : stop))

/** The fee at once, then 10% of it more every hour: six steps, up to 1.5 times. Level 1 takes one fee only. */
export const rising = (now: number, fee: number, level: number): FeeStep[] =>
  (level === 1 ? [0] : [0, 1, 2, 3, 4, 5]).map((k) => ({ at: now + k * HOUR, feeCents: Math.max(1, Math.round(fee * (1 + k / 10))) }))

/** 1.5 times the fee at once, then a quarter of it more every half hour, up to 2.5 times. */
export const steep = (now: number, fee: number, level: number): FeeStep[] =>
  (level === 1 ? [0] : [0, 1, 2, 3, 4]).map((k) => ({ at: now + k * 30, feeCents: Math.max(1, Math.round(fee * (1.5 + k / 4))) }))

export function stopsFor(order: Order, legs: number[], note: Note | null, retry: Retry): StopRef[] {
  return legs.flatMap((leg): StopRef[] => {
    const { car, pickup, delivery } = order.legs[leg]!
    const noted = windowFromNote(note, pickup.window, "pickup")
    const start = Math.max(noted.from, retry.pickupFrom)
    const pickupWindow = { from: start, to: Math.max(noted.to, start) }
    const deliveryBase = { from: delivery.window.from, to: Math.max(delivery.window.from, order.deadline) }
    const deliveryWindow = windowFromNote(note, deliveryBase, "delivery")
    const lowBattery = car.electric && car.chargePercent !== null && car.chargePercent < 30
    const first: StopRef = { orderId: order.id, leg, kind: "pickup", withPlates: retry.plates, withCharging: lowBattery }
    const second: StopRef = { orderId: order.id, leg, kind: "delivery" }
    return [narrower(first, pickupWindow, pickup.window), narrower(second, deliveryWindow, deliveryBase)]
  })
}

export const narrower = (stop: StopRef, window: TimeWindow, base: TimeWindow): StopRef =>
  window.from > base.from || window.to < base.to ? { ...stop, window } : stop

const AFTER = /jälkeen|alkaen|aikaisintaan|\bafter\b|\bfrom\b|earliest|not before|ei ennen|valmis|\bready\b|efter|tidigast|inte före|klar/
const BEFORE = /ennen|mennessä|viim|\bbefore\b|\bby\b|latest|före|senast/
const DELIVERY = /toimit|perillä|perille|vastaanot|kohde|deliver|arrive|destination|receiv|leverera|leverans|framme|mottag/
const CLOCK = /(?:klo|kl\.?)\s*(\d{1,2})(?:[.:](\d{2}))?|\b(\d{1,2})[.:](\d{2})\b/g
const RANGE = /\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?\b/g

/** The starter's note reader: clock times near a few keywords, on the window's own day. */
export function windowFromNote(note: Note | null, window: TimeWindow, stop: "pickup" | "delivery"): TimeWindow {
  if (!note) return window
  let text = note.text.toLowerCase()
  if (DELIVERY.test(text) !== (stop === "delivery")) return window
  const minutes = (hour: number, minute: number): number | null => (hour > 24 || minute > 59 ? null : hour * HOUR + minute)
  const dayStart = (t: number) => Math.floor(t / DAY) * DAY
  let { from, to } = window
  for (const match of text.matchAll(RANGE)) {
    const opens = minutes(Number(match[1]), Number(match[2] ?? 0))
    const closes = minutes(Number(match[3]), Number(match[4] ?? 0))
    if (opens === null || closes === null || opens >= closes) continue
    from = Math.max(from, dayStart(from) + opens)
    to = Math.min(to, dayStart(to) + closes)
  }
  text = text.replace(RANGE, " ")
  for (const match of text.matchAll(CLOCK)) {
    const m = minutes(Number(match[1] ?? match[3]), Number(match[2] ?? match[4] ?? 0))
    if (m === null) continue
    const time = dayStart(window.from) + m
    const around = text.slice(Math.max(0, match.index - 16), match.index + match[0].length + 16)
    if (AFTER.test(around)) from = Math.max(from, time)
    else if (BEFORE.test(around)) to = Math.min(to, time)
  }
  return from <= to ? { from, to } : window
}
