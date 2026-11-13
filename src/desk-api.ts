/** The contract between the desk (decision logic) and the runners (practice loop, final loop, bench).
 * The desk never talks to the server: it ingests events, keeps books, and leaves actions in an outbox. */
import type { Action, ActionResult, DeskEvent, DeskEventKind, DeskSnapshot, DriverProfile, WorldMap } from "./client/types.ts"

export const HOUR = 60
export const DAY = 24 * HOUR
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

/** What a desk gets once per world, before the first event. */
export type DeskContext = {
  level: number
  map: WorldMap
  roster: DriverProfile[]
  endsAt: number
  /** Decision-log sink: one JSON object per decision (quote, fee, offer, mode change). May be undefined. */
  log?: (line: Record<string, unknown>) => void
}

export interface Desk {
  /** The desk's idea of the current world minute (set by rejoin/handle/tick). */
  readonly now: number
  /** Rebuild all books from a snapshot and the full event history, then answer what was missed. */
  rejoin(snapshot: DeskSnapshot, history: DeskEvent[]): void
  /** Ingest one event. The caller has already dropped repeats by seq. */
  handle(event: DeskEvent): void
  /** Time-based work (at-risk sweeps, scheduled offers). Called at every stop of the clock. */
  tick(now: number): void
  /** Take every pending action. The caller sends them with the next advance (practice) or at once (final). */
  drain(): Action[]
  /** Results of a drained batch, in order. The desk records the gig ids of accepted posts. */
  onResults(actions: Action[], results: ActionResult[]): void
  /** The next minute at which the desk wants a tick even if no event comes, or null. */
  nextWake(): number | null
}

/** The event kinds that stop the practice clock. price_request is NOT here: requests are quoted in the very
 * next advance, and the stride guarantees one within 14 minutes (< the 15-minute response deadline). */
export const WAKE_ON: DeskEventKind[] = [
  "order_won", "order_lost", "order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close",
  "gig_dropped", "no_show", "offer_answered", "driver_late", "release",
]

/** The kit starter's own wake list, used only for the to-the-cent regression test against the kit's starter. */
export const WAKE_ON_STARTER: DeskEventKind[] = ["price_request", "order_won", "order_changed", "order_cancelled", "visit_failed", "gig_expired", "deadline_close"]

export type StepPolicy = {
  /** "stride": advance untilEvent WAKE_ON with max = now + strideMin (plus night/Sunday skips); "starter": the kit's one-step-per-request loop. */
  kind: "stride" | "starter"
  strideMin: number
  nightSkip: boolean
}

export const STRIDE_POLICY: StepPolicy = { kind: "stride", strideMin: 14, nightSkip: true }
export const STARTER_POLICY: StepPolicy = { kind: "starter", strideMin: 0, nightSkip: false }

/** Per-run artifacts under runs/<runId>/ (written by the runners, read by analyze.ts):
 *   meta.json        RunMeta
 *   config.json      the Cfg object used
 *   events.jsonl     every DeskEvent as received, one per line, in seq order, no repeats
 *   actions.jsonl    { at, action, result } per action sent, in send order
 *   decisions.jsonl  the desk's decision log (free-form JSON objects with at least { at, kind })
 *   score.json       Score at the end
 *   roster.json      DriverProfile[] read at start
 *   reveal.json      Reveal (practice worlds only, after the end; absent for ranking runs)
 *   snapshot.json    DeskSnapshot at the end
 * runs/index.jsonl: one line per run = RunMeta + { marginCents, revenueCents, wonOrders, onTimeShare, undeliveredShare, ranked }
 * data/results.csv: the same summary as CSV for slides (append-only). */
export type RunMeta = {
  runId: string
  worldId: string
  seed: string | null
  level: number
  cfgName: string
  cfgHash: string
  policy: StepPolicy
  gitSha: string
  startedAt: string
  endedAt: string | null
  steps: number
  wallMs: number
  msPerStep: number
  exceptions: number
}
