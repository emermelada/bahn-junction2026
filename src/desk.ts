/** The desk: books + decisions. With every flag off it is a faithful port of the kit's starter (the regression
 * test reproduces the starter's score to the cent). Each flag swaps one decision for a module of PLAN.md §6. */
import type { Action, ActionResult, DeskEvent, DeskSnapshot, FeeStep, Note, Order, PostAction, PriceRequest, StopRef, TimeWindow } from "./client/types.ts"
import type { Cfg } from "./config.ts"
import type { Desk, DeskContext } from "./desk-api.ts"
import { DAY, HOUR } from "./desk-api.ts"
import { Geo } from "./geo.ts"
import { Books } from "./books.ts"
import { Capacity } from "./capacity.ts"
import { Governor } from "./governor.ts"
import { Quoter } from "./quote.ts"
import { Fees } from "./fees.ts"
import { Pricing } from "./pricing.ts"
import { Offers } from "./offers.ts"
import type { OfferNeed } from "./offers.ts"
import { readNote } from "./notes.ts"
import type { NoteFacts } from "./notes.ts"

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
  readonly books: Books
  readonly capacity: Capacity
  readonly governor: Governor
  readonly quoter: Quoter
  readonly toQuote: PriceRequest[] = [] // requests waiting for the one-pass quote decision (v2 quote path)
  readonly v2Quote: boolean
  readonly fees: Fees
  readonly pricing: Pricing
  readonly offers: Offers
  readonly offerQueue = new Map<string, string>() // gigId -> reason, fired at the next tick
  readonly bundleGigs = new Map<string, string[]>() // gigId -> the orders a multi-car gig carries (bundles)
  readonly bundlePosts = new Map<PostAction, string[]>() // bundle posts in flight -> their orders (fallback on refusal)
  readonly dropRaised = new Set<string>() // orders whose gig got the one +15% after a drop
  readonly doomedGigs = new Set<string>() // gigs repriced to the doomed schedule
  readonly cliffSeen = new Set<string>() // gigs counted as reaching the cliff (fee learner)
  nextSweep = 0

  constructor(cfg: Cfg, ctx: DeskContext) {
    this.cfg = cfg
    this.ctx = ctx
    this.level = ctx.level
    this.geo = new Geo(ctx.map, ctx.roster)
    this.books = new Books(this.geo)
    this.capacity = new Capacity(cfg, this.geo, this.books)
    this.governor = new Governor(cfg, this.books)
    this.quoter = new Quoter(cfg, this.geo, this.books, this.capacity, this.governor)
    const f = cfg.flags
    this.v2Quote = f.gate || f.capacity || f.governor || f.ladder || f.pricing
    this.fees = new Fees(cfg, this.geo, ctx.log)
    this.pricing = new Pricing(cfg, this.geo, this.books)
    this.offers = new Offers(cfg, this.geo, this.books)
    if (f.pricing) this.quoter.ratio = (request, option) => this.pricing.quoteRatio(request, option, this.now, f.capacity ? this.capacity.dealerPenalty(request.dealerId, this.now) : 0)
  }

  // ------------------------------------------------------------------ lifecycle

  async rejoin(snapshot: DeskSnapshot, history: DeskEvent[]): Promise<void> {
    this.now = snapshot.now
    // v2 books: replay the whole history (pure bookkeeping), then the snapshot's gigs and positions.
    for (const event of history) {
      this.books.track(event)
      if (event.kind === "order_won") (this.quoter.onWon(event.order), this.pricing.outcome(event.order.id, true, event.at))
      else if (event.kind === "order_lost") (this.quoter.onLost(event.requestId), this.pricing.outcome(event.requestId, false, event.at))
      else if (event.kind === "order_cancelled") this.quoter.onCancelled(event.orderId)
      else if (event.kind === "gig_dropped" || event.kind === "no_show") {
        const orderId = snapshot.gigs.find((g) => g.id === event.gigId)?.stops[0]?.orderId
        if (orderId) this.dropRaised.add(orderId)
      }
    }
    this.books.seed(snapshot)
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
    this.books.track(event)
    if (event.kind === "order_won") (this.quoter.onWon(event.order), this.pricing.outcome(event.order.id, true, event.at))
    else if (event.kind === "order_lost") (this.quoter.onLost(event.requestId), this.pricing.outcome(event.requestId, false, event.at))
    else if (event.kind === "order_cancelled") this.quoter.onCancelled(event.orderId)
    if (this.cfg.flags.fees) this.feeEvent(event)
    if (event.kind === "offer_answered") {
      this.offers.answered(event.gigId, event.driverId, event.answer)
      if (event.answer === "accepted") this.booked.add(event.gigId)
      this.ctx.log?.({ at: event.at, kind: "offer_answer", gig: event.gigId, driver: event.driverId, answer: event.answer })
    }
    if (event.kind === "price_request") this.quote(event.request)
    else if (event.kind === "order_won") await this.win(event.order)
    else if (event.kind === "order_changed") await this.change(event.order)
    else if (event.kind === "order_cancelled") {
      for (const books of [this.orders, this.legGigs]) books.delete(event.orderId)
      for (const g of event.gigs) if (g.outcome === "withdrawn") this.unmapGig(g.gigId) // its other cars get posted again by the sweep
    }
    else if (event.kind === "visit_failed") await this.retry(event.orderId, event.leg, event.reason)
    else if (event.kind === "gig_expired") this.repost(event.gigId)
    else if (event.kind === "deadline_close") await this.raise(event.orderId)
    else if (event.kind === "gig_booked") this.booked.add(event.gigId)
    else if (event.kind === "gig_dropped" || event.kind === "no_show") this.booked.delete(event.gigId)
    else if (event.kind === "delivered") this.delivered(event.orderId, event.leg, event.at)
  }

  setClock(now: number): void {
    this.now = Math.max(this.now, now)
  }

  async tick(now: number): Promise<void> {
    this.now = Math.max(this.now, now)
    if (this.v2Quote) this.markMissed()
    if (this.cfg.flags.triage && this.now >= this.nextSweep) {
      this.nextSweep = this.now - (this.now % this.cfg.triage.sweepEveryMin) + this.cfg.triage.sweepEveryMin
      await this.sweep()
    }
    if (this.cfg.flags.offers) this.fireOffers()
  }

  /** One offer round for each queued gig that is still open. */
  fireOffers(): void {
    for (const [gigId, reason] of this.offerQueue) {
      this.offerQueue.delete(gigId)
      if (this.booked.has(gigId)) continue
      const need = this.offerNeed(gigId, reason)
      if (need) this.outbox.push(...this.offers.round(need, this.now, this.ctx.log))
    }
  }

  offerNeed(gigId: string, reason: string): OfferNeed | null {
    const action = this.posts.get(gigId)
    const orderId = action?.stops[0]?.orderId
    const order = orderId ? this.orders.get(orderId) : undefined
    if (!action || !order || !action.stops.some(({ orderId, leg }) => this.legGigs.get(orderId)?.get(leg) === gigId)) return null
    const first = action.stops.find((s) => s.kind === "pickup")!
    const last = action.stops.at(-1)!
    const steps = action.schedule.filter((st) => st.at <= this.now)
    const fee = (steps.at(-1) ?? action.schedule[0]!).feeCents * (reason === "thin" || reason === "stale" ? this.cfg.offers.feeMult : 1)
    return {
      gigId, reason, fee, lastPickup: order.lastPickupAt,
      pickup: this.books.placeOf(first.orderId, first.leg, "pickup"),
      delivery: this.books.placeOf(last.orderId, last.leg, "delivery"),
      premium: !!action.audience.experienced, manual: !!action.audience.manualLicence,
    }
  }

  /** A reprice that also updates the remembered schedule (offers read the current fee from it). */
  pushReprice(gigId: string, schedule: FeeStep[]): void {
    const post = this.posts.get(gigId)
    if (post) this.posts.set(gigId, { ...post, schedule })
    this.outbox.push({ type: "reprice", gigId, schedule })
  }

  /** Fee learner inputs and the one raise after a drop. */
  feeEvent(event: DeskEvent): void {
    if (event.kind === "gig_booked") {
      const gig = this.books.gigs.get(event.gigId)
      const pickup = gig ? this.books.placeOf(gig.orderIds[0]!, 0, "pickup") : ""
      if (gig && pickup && !this.cliffSeen.has(gig.id)) this.fees.booked(pickup, event.feeCents <= gig.firstFee && event.at - gig.postedAt <= 60)
    } else if (event.kind === "gig_dropped" || event.kind === "no_show") {
      const action = this.posts.get(event.gigId)
      const orderId = action?.stops[0]?.orderId
      const order = orderId ? this.orders.get(orderId) : undefined
      if (!order || !action) return
      this.fees.dropped(order.legs[0]!.pickup.placeId)
      if (this.dropRaised.has(order.id) || this.urgent.has(order.id)) return
      this.dropRaised.add(order.id)
      this.pushReprice(event.gigId, this.feesFor(order, pickups(action)))
    }
  }

  /** The 30-minute sweep: a car without any live gig gets one; an unbooked car past its last pickup goes doomed;
   * gigs past their cliff feed the fee learner. */
  async sweep(): Promise<void> {
    for (const order of this.orders.values()) {
      if (order.status === "cancelled") continue
      const missing = undelivered(order).filter((leg) => !this.legGigs.get(order.id)?.has(leg))
      const pendingPost = this.outbox.some((a) => a.type === "post" && a.stops.some((s) => s.orderId === order.id))
      if (missing.length > 0 && !pendingPost && this.requests.has(order.id)) {
        this.ctx.log?.({ at: this.now, kind: "sweep_post", order: order.id, legs: missing })
        await this.post(order, missing)
        continue
      }
      for (const gigId of this.gigsOf(order.id)) {
        if (this.booked.has(gigId)) continue
        if (!this.cliffSeen.has(gigId) && this.now >= order.lastPickupAt - 300) {
          this.cliffSeen.add(gigId)
          this.fees.cliff(order.legs[0]!.pickup.placeId)
        }
        if (this.bundleGigs.has(gigId) && this.now > order.lastPickupAt - this.cfg.fees.rescue.warnMinBefore) { this.splitBundle(gigId, "late"); continue }
        if (this.now > order.lastPickupAt && !this.doomedGigs.has(gigId) && this.posts.has(gigId)) {
          this.doomedGigs.add(gigId)
          this.ctx.log?.({ at: this.now, kind: "doomed", order: order.id, gig: gigId })
          this.pushReprice(gigId, this.feesFor(order, pickups(this.posts.get(gigId)!)))
        }
        if (this.cfg.flags.offers && !this.offers.quiet(this.now)) {
          const last = this.offers.lastRound.get(gigId) ?? -1e9
          const toGo = order.lastPickupAt - this.now
          const posted = this.books.gigs.get(gigId)?.postedAt ?? this.now
          if (toGo > 0 && toGo < this.cfg.offers.warnMinBefore && this.now - last >= 30) this.offerQueue.set(gigId, "risk")
          else if (toGo > 0 && toGo < 12 * 60 && this.now - posted >= this.cfg.offers.openMinTrigger && this.now - last >= 60) this.offerQueue.set(gigId, "stale")
        }
      }
    }
  }

  drain(): Action[] {
    this.flushQuotes()
    return this.outbox.splice(0)
  }

  /** Decides every waiting request in one pass (v2 quote path). Quotes go to the front of the outbox. */
  flushQuotes(): void {
    if (this.toQuote.length === 0) return
    const requests = this.toQuote.splice(0)
    const quotes = this.quoter.decide(requests, this.now, this.atRisk(), this.ctx.log)
    this.outbox.unshift(...quotes)
  }

  /** Orders without a driver whose last pickup is within atRiskMin minutes (for the governor). */
  atRisk(): number {
    return this.governor.atRisk(this.now, (orderId) => {
      const gigs = this.gigsOf(orderId)
      if (gigs.length === 0) return "none"
      return gigs.every((g) => this.booked.has(g)) ? "booked" : "open"
    })
  }

  /** Sticky lateness: an order whose last pickup minute has passed with no driver holding its gig counts as late. */
  markMissed(): void {
    for (const book of this.books.orders.values()) {
      if (book.late || book.deliveredAll) continue
      if (this.now <= book.order.lastPickupAt) continue
      const gigs = this.gigsOf(book.order.id)
      if (gigs.length > 0 && gigs.every((g) => this.booked.has(g))) continue
      this.books.markLate(book, "missed_last_pickup")
    }
  }

  onResults(actions: Action[], results: ActionResult[]): void {
    this.readResults(actions, results)
  }

  nextWake(): number | null {
    if (!this.cfg.flags.triage) return null
    // No sweep wakes at night: drivers do not read then, and fee steps there move to 07:00.
    const mod = this.nextSweep % DAY
    if (mod >= 23 * 60) return Math.floor(this.nextSweep / DAY) * DAY + DAY + 7 * 60
    if (mod < 7 * 60) return Math.floor(this.nextSweep / DAY) * DAY + 7 * 60
    return this.nextSweep
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
    if (this.v2Quote) {
      if (!this.books.requests.has(request.id)) this.books.requests.set(request.id, request)
      this.toQuote.push(request)
      return
    }
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
    if (this.bundleGigs.has(gigId)) {
      for (const id of this.bundleGigs.get(gigId)!) { const o = this.orders.get(id); if (o) this.postSingle(o, Infinity) }
      return
    }
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
      if (!this.booked.has(gigId) && this.bundleGigs.has(gigId)) { this.splitBundle(gigId, "warning"); continue }
      if (!this.booked.has(gigId)) {
        this.pushReprice(gigId, this.feesFor(order, pickups(this.posts.get(gigId)!)))
        if (this.cfg.flags.offers) this.offerQueue.set(gigId, "rescue")
      }
    }
  }

  feesFor(order: Order, cars: number): FeeStep[] {
    if (this.cfg.flags.fees) return this.v2Fees(order, cars)
    const fee = (this.requests.get(order.id)!.referenceFeeCents * cars) / order.legs.length
    return this.urgent.has(order.id) ? steep(this.now, fee, this.level) : rising(this.now, fee, this.level)
  }

  /** 6.4: flat-then-cliff before the warning; the on-time cap after it; the doomed schedule once the last pickup passed. */
  v2Fees(order: Order, cars: number): FeeStep[] {
    const request = this.requests.get(order.id)!
    let base = this.fees.open(order, request, cars)
    if (this.dropRaised.has(order.id)) base *= this.cfg.fees.dropRaise
    const ref = (request.referenceFeeCents * cars) / order.legs.length
    const price = (order.priceCents * cars) / order.legs.length
    const amber = this.cfg.flags.governor && this.governor.mode !== "GREEN"
    let schedule: FeeStep[]
    let stage: string
    if (this.now > order.lastPickupAt) (schedule = this.fees.doomed(this.now, base, price, this.ctx.endsAt)), (stage = "doomed")
    else if (this.urgent.has(order.id)) (schedule = this.fees.rescue(this.now, base, price, ref, amber)), (stage = "rescue")
    else (schedule = this.fees.schedule(this.now, base, order.lastPickupAt)), (stage = "open")
    this.ctx.log?.({ at: this.now, kind: "fee", order: order.id, stage, cars, ref: Math.round(ref), price: Math.round(price), base: Math.round(base), lastPickup: order.lastPickupAt, schedule })
    return schedule
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
    if (this.cfg.flags.bundles && retry === FIRST_TRY && legs.length === 1 && order.legs.length === 1 && this.tryBundle(order)) return
    const facts = this.factsOf(order)
    const audience = { experienced: order.legs.some((leg) => leg.car.premium), manualLicence: retry.manualLicence || !!facts?.manual }
    const stops = withoutWindows(stopsFor(order, legs, this.requests.get(order.id)!.note, retry, facts), this.now)
    this.outbox.push({ type: "post", stops, audience, schedule: this.feesFor(order, legs.length) })
    if (legs.length === 1) return
    // A trade-in over the 12-hour limit for a gig with two cars goes as one gig per car.
    await this.send()
    if (this.gigsOf(order.id).length === 0) for (const leg of legs) await this.post(order, [leg], retry)
  }

  /** The note facts of an order's request when the notes flag is on (null = no facts), else undefined (starter reader). */
  factsOf(order: Order): NoteFacts | null | undefined {
    if (!this.cfg.flags.notes) return undefined
    const request = this.requests.get(order.id)
    return request ? readNote(request.note, request) : null
  }

  /** One car alone, at its own fees (no bundle attempt). */
  postSingle(order: Order, windowsBefore: number): void {
    const facts = this.factsOf(order)
    const audience = { experienced: order.legs.some((leg) => leg.car.premium), manualLicence: !!facts?.manual }
    const stops = withoutWindows(stopsFor(order, [0], this.requests.get(order.id)!.note, FIRST_TRY, facts), windowsBefore)
    this.outbox.push({ type: "post", stops, audience, schedule: this.feesFor(order, 1) })
  }

  unmapGig(gigId: string): void {
    for (const legs of this.legGigs.values()) for (const [leg, g] of legs) if (g === gigId) legs.delete(leg)
  }

  remapGig(gigId: string): void {
    const action = this.posts.get(gigId)
    if (action) for (const { orderId, leg } of action.stops) if (this.orders.has(orderId)) this.legGigs.set(orderId, (this.legGigs.get(orderId) ?? new Map()).set(leg, gigId))
  }

  /** A bundle about to miss: take it off the app and post each car alone (the urgent one gets rescue fees). */
  splitBundle(gigId: string, why: string): void {
    const ids = this.bundleGigs.get(gigId) ?? []
    this.bundleGigs.delete(gigId)
    this.unmapGig(gigId)
    this.outbox.push({ type: "withdraw", gigId })
    this.ctx.log?.({ at: this.now, kind: "bundle_split", gig: gigId, orders: ids, why })
    for (const id of ids) {
      const o = this.orders.get(id)
      if (o) this.postSingle(o, this.now)
    }
  }

  /** 6.8 out-and-back bundle: the new car A->B with an open single car B'->A' already posted (B' near B, A' near A),
   * or the other way round, when one driver can do both on time within maxDriveMin. Fee = (both opening fees) x feeMult. */
  tryBundle(order: Order): boolean {
    if (this.urgent.has(order.id) || this.now >= order.lastPickupAt) return false
    const B = this.cfg.bundles
    const note = this.requests.get(order.id)?.note ?? null
    const mine = withoutWindows(stopsFor(order, [0], note, FIRST_TRY, this.factsOf(order)), this.now)
    if (mine.some((st) => st.window)) return false
    const a = order.legs[0]!
    let best: { gigId: string; partner: Order; first: Order; second: Order; drive: number } | null = null
    for (const [gigId, action] of this.posts) {
      if (this.booked.has(gigId) || this.bundleGigs.has(gigId) || this.doomedGigs.has(gigId)) continue
      if (action.stops.length !== 2 || action.stops.some((st) => st.window || st.withPlates)) continue
      const pid = action.stops[0]!.orderId
      if (pid === order.id || this.legGigs.get(pid)?.get(0) !== gigId) continue
      const partner = this.orders.get(pid)
      if (!partner || partner.legs.length !== 1 || this.urgent.has(pid) || this.now >= partner.lastPickupAt) continue
      const b = partner.legs[0]!
      if (this.geo.road(a.delivery.placeId, b.pickup.placeId) > B.pairRoadMin || this.geo.road(b.delivery.placeId, a.pickup.placeId) > B.pairRoadMin) continue
      for (const [first, second] of [[order, partner], [partner, order]] as const) {
        const drive = this.pairDrive(first, second)
        if (drive === null) continue
        if (!best || drive < best.drive) best = { gigId, partner, first, second, drive }
      }
    }
    if (!best) return false
    const { gigId, partner, first, second } = best
    this.legGigs.get(partner.id)?.delete(0)
    this.outbox.push({ type: "withdraw", gigId })
    const stopsOf = (o: Order) => withoutWindows(stopsFor(o, [0], this.requests.get(o.id)!.note, FIRST_TRY, this.factsOf(o)), this.now)
    const base = (this.fees.open(first, this.requests.get(first.id)!, 1) + this.fees.open(second, this.requests.get(second.id)!, 1)) * B.feeMult
    const f = first.legs[0]!
    const cliffAt = Math.min(first.lastPickupAt, second.lastPickupAt - this.geo.road(f.pickup.placeId, f.delivery.placeId) - this.geo.road(f.delivery.placeId, second.legs[0]!.pickup.placeId) - 30)
    const schedule = this.fees.schedule(this.now, base, cliffAt)
    const action: PostAction = {
      type: "post",
      stops: [...stopsOf(first), ...stopsOf(second)],
      audience: { experienced: [first, second].some((o) => o.legs.some((l) => l.car.premium)), manualLicence: false },
      schedule,
    }
    this.bundlePosts.set(action, [first.id, second.id])
    this.outbox.push(action)
    this.ctx.log?.({ at: this.now, kind: "bundle", orders: [first.id, second.id], drive: best.drive, base: Math.round(base), cliffAt })
    return true
  }

  /** Driving minutes of first then second, or null when one driver cannot collect both on time or it is too long. */
  pairDrive(first: Order, second: Order): number | null {
    const f = first.legs[0]!
    const s = second.legs[0]!
    const leg1 = this.geo.road(f.pickup.placeId, f.delivery.placeId)
    const hop = this.geo.road(f.delivery.placeId, s.pickup.placeId)
    const leg2 = this.geo.road(s.pickup.placeId, s.delivery.placeId)
    const drive = leg1 + hop + leg2
    if (drive > this.cfg.bundles.maxDriveMin) return null
    const t1 = Math.max(this.now + this.cfg.gate.reachMarginMin, f.pickup.window.from)
    if (t1 > first.lastPickupAt - 60) return null
    const t2 = Math.max(t1 + leg1 + hop + 15, s.pickup.window.from)
    if (t2 > second.lastPickupAt - 60) return null
    if (t2 - t1 > 10 * 60) return null
    return drive
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
    for (const gigId of gigs) {
      this.outbox.push({ type: "withdraw", gigId })
      for (const id of this.bundleGigs.get(gigId) ?? []) {
        if (id === orderId) continue
        this.legGigs.get(id)?.delete(0)
        const o = this.orders.get(id)
        if (o) this.postSingle(o, this.now)
      }
    }
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
      if (action.type === "withdraw" && results[i] && !results[i]!.ok) this.remapGig(action.gigId) // a driver booked it meanwhile: it still carries its cars
      if (action.type === "post" && this.bundlePosts.has(action)) {
        const ids = this.bundlePosts.get(action)!
        this.bundlePosts.delete(action)
        if (results[i]?.ok) this.bundleGigs.set((results[i] as { ok: true; id: string }).id, ids)
        else {
          this.ctx.log?.({ at: this.now, kind: "bundle_refused", orders: ids, reason: (results[i] as { reason?: string } | undefined)?.reason })
          for (const id of ids) { const o = this.orders.get(id); if (o && !this.legGigs.get(id)?.has(0)) this.postSingle(o, this.now) }
          return
        }
      }
      if (action.type === "post" && results[i]?.ok) {
        const id = (results[i] as { ok: true; id: string }).id
        this.carry(action, id)
        const last = action.stops.at(-1)!
        this.books.posted(id, [...new Set(action.stops.map((s) => s.orderId))], pickups(action), this.now, action.schedule[0]?.feeCents ?? 0, this.books.placeOf(last.orderId, last.leg, last.kind), "")
        const pickup = this.books.placeOf(action.stops[0]!.orderId, action.stops[0]!.leg, "pickup")
        if (this.cfg.flags.offers && pickup && this.geo.reach30(pickup).all < this.cfg.offers.reach30Trigger) this.offerQueue.set(id, "thin")
      }
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

export function stopsFor(order: Order, legs: number[], note: Note | null, retry: Retry, facts?: NoteFacts | null): StopRef[] {
  if (facts !== undefined) return stopsFromFacts(order, legs, facts, retry)
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

/** 6.8 notes: the pickup not before the note's ready / after-payment time, the delivery by the note's deadline,
 * plates fetched on the way when the note says the car has none. */
export function stopsFromFacts(order: Order, legs: number[], facts: NoteFacts | null, retry: Retry): StopRef[] {
  return legs.flatMap((leg): StopRef[] => {
    const { car, pickup, delivery } = order.legs[leg]!
    const start = Math.max(pickup.window.from, facts?.readyFrom ?? 0, facts?.afterPayment ?? 0, retry.pickupFrom)
    const pickupWindow = { from: start, to: Math.max(pickup.window.to, start) }
    const deliveryBase = { from: delivery.window.from, to: Math.max(delivery.window.from, order.deadline) }
    const due = Math.min(deliveryBase.to, facts?.deadline ?? Infinity)
    const deliveryWindow = { from: deliveryBase.from, to: Math.max(due, deliveryBase.from) }
    const lowBattery = car.electric && car.chargePercent !== null && car.chargePercent < 30
    const first: StopRef = { orderId: order.id, leg, kind: "pickup", withPlates: retry.plates || !!facts?.plates, withCharging: lowBattery }
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
