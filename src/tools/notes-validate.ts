/** Validates the note reader (src/notes.ts) against revealed truth.
 *
 *   node src/tools/notes-validate.ts                      data/reveal-spread1-L8-starter (requests.csv + legs.csv)
 *   node src/tools/notes-validate.ts <dir-with-csvs>      another CSV reveal
 *   node src/tools/notes-validate.ts --json <reveal.json>…
 *   node src/tools/notes-validate.ts --all                every runs/<run>/reveal.json, one copy per seed (a run's
 *                                                         won orders give truth; runs of one seed are pooled)
 *   flags: --quiet (table only), --unparsed (list every note the reader flags unparsed, won or not)
 *
 * Per fact: TP (truth changed, reader exact), FP (reader changed what truth did not), FN (truth changed, reader
 * silent), WRONG (both changed, values differ). Compared on leg 0 (no trade-in leg carries a note fact).
 *   ready     max(stated pickup from, readyFrom) vs truth.readyAt (a change = truth differs from stated from)
 *   payment   afterPayment vs truth.releasedAt
 *   deadline  deadline vs truth.noteDeadline; a reader deadline at or after the order's deadline while truth is
 *             null counts as LOOSE (harmless: the world ignores a deadline that is not tighter)
 *   pHours / dHours  stated hours merged with the reader's opens/closes vs truth hours
 *   plates / manual / summer  vs the truth booleans
 */
import { readFileSync, readdirSync, existsSync } from "node:fs"
import { join } from "node:path"
import type { LegTruth, OpeningHours, PriceRequest, RevealedRequest } from "../client/types.ts"
import { readCsv } from "./csv.ts"
import { readNote, debugNote, type NoteFacts } from "../notes.ts"

type Case = { key: string; request: PriceRequest; option: string | null; truth: LegTruth[] | null }

const args = process.argv.slice(2)
const flag = (name: string) => args.includes(name)
const paths = args.filter((a) => !a.startsWith("--"))

// ───────── loading ─────────

const num = (v: unknown): number | null => (v === "" || v === undefined || v === null ? null : Number(v))
const bool = (v: unknown) => v === "true"

function hoursFromCsv(row: Record<string, unknown>, prefix: string): OpeningHours | null {
  if (row[`${prefix}.opens`] === "" || row[`${prefix}.opens`] === undefined) return null
  const satOpens = num(row[`${prefix}.saturday.opens`])
  return {
    opens: Number(row[`${prefix}.opens`]),
    closes: Number(row[`${prefix}.closes`]),
    weekdays: JSON.parse(String(row[`${prefix}.weekdays`] || "[]")),
    saturday: satOpens === null ? null : { opens: satOpens, closes: Number(row[`${prefix}.saturday.closes`]) },
  }
}

function loadCsvDir(dir: string): Case[] {
  const requests = readCsv(join(dir, "requests.csv"))
  const legs = readCsv(join(dir, "legs.csv"))
  const legsBy = new Map<string, Record<string, unknown>[]>()
  for (const l of legs) {
    const id = String(l.requestId)
    if (!legsBy.has(id)) legsBy.set(id, [])
    legsBy.get(id)!.push(l)
  }
  const cases: Case[] = []
  for (const r of requests) {
    const id = String(r.id)
    const rows = (legsBy.get(id) ?? []).sort((a, b) => Number(a.leg) - Number(b.leg))
    const options = (["same_day", "next_day", "within_3_days"] as const)
      .filter((k) => r[`${k}.deadline`] !== "")
      .map((k) => ({ kind: k, deadline: Number(r[`${k}.deadline`]), listPriceCents: Number(r[`${k}.listPriceCents`]) }))
    const request = {
      id,
      dealerId: String(r.dealerId),
      batchId: r.batchId ? String(r.batchId) : null,
      arrivedAt: Number(r.arrivedAt),
      respondBy: Number(r.respondBy),
      referenceFeeCents: Number(r.referenceFeeCents),
      options,
      note: r.note ? { text: String(r.note), language: String(r.language) as "fi" | "sv" | "en" } : null,
      legs: rows.map((l) => ({
        car: { premium: bool(l["car.premium"]), electric: bool(l["car.electric"]), chargePercent: num(l["car.chargePercent"]) },
        pickup: { placeId: String(l["pickup.placeId"]), privateAddress: bool(l["pickup.privateAddress"]), window: { from: Number(l["pickup.window.from"]), to: Number(l["pickup.window.to"]) }, hours: hoursFromCsv(l, "pickup.hours") },
        delivery: { placeId: String(l["delivery.placeId"]), privateAddress: bool(l["delivery.privateAddress"]), window: { from: Number(l["delivery.window.from"]), to: Number(l["delivery.window.to"]) }, hours: hoursFromCsv(l, "delivery.hours") },
      })),
    } as PriceRequest
    const won = rows.length > 0 && rows[0]!["truth.readyAt"] !== ""
    const truth: LegTruth[] | null = won
      ? rows.map((l) => ({
          readyAt: Number(l["truth.readyAt"]),
          releasedAt: num(l["truth.releasedAt"]),
          pickupHours: hoursFromCsv(l, "truth.pickupHours"),
          deliveryHours: hoursFromCsv(l, "truth.deliveryHours"),
          manualGearbox: bool(l["truth.manualGearbox"]),
          needsPlates: bool(l["truth.needsPlates"]),
          summerTyres: bool(l["truth.summerTyres"]),
          noteDeadline: num(l["truth.noteDeadline"]),
          pickedUpAt: num(l["truth.pickedUpAt"]),
          deliveredAt: num(l["truth.deliveredAt"]),
        }))
      : null
    cases.push({ key: id, request, option: r.option ? String(r.option) : null, truth })
  }
  return cases
}

type Reveal = { requests: RevealedRequest[]; orders: { orderId: string; legs: LegTruth[] }[] }

/** Cases from reveal.json files; files of one seed (same requests) are pooled so each request appears once. */
function loadJson(files: string[]): Case[] {
  const bySeed = new Map<string, Map<string, Case>>()
  for (const f of files) {
    const r = JSON.parse(readFileSync(f, "utf8")) as Reveal
    const reqs = r.requests.map((x) => x.request)
    const seed = `${reqs.length}/${reqs.filter((q) => q.note).length}/${reqs[0]?.arrivedAt}/${reqs.find((q) => q.note)?.note?.text}`
    if (!bySeed.has(seed)) bySeed.set(seed, new Map())
    const cases = bySeed.get(seed)!
    const orders = new Map(r.orders.map((o) => [o.orderId, o]))
    for (const x of r.requests) {
      const prev = cases.get(x.request.id)
      const o = orders.get(x.request.id)
      if (prev && (prev.truth || !o)) continue
      cases.set(x.request.id, { key: `s${[...bySeed.keys()].indexOf(seed)}:${x.request.id}`, request: x.request, option: o ? x.option : null, truth: o ? o.legs : null })
    }
  }
  return [...bySeed.values()].flatMap((m) => [...m.values()])
}

function allRevealFiles(): string[] {
  const out: string[] = []
  for (const d of readdirSync("runs")) {
    const p = join("runs", d, "reveal.json")
    if (existsSync(p)) out.push(p)
  }
  return out
}

let cases: Case[]
if (flag("--all")) cases = loadJson(allRevealFiles())
else if (flag("--json")) cases = loadJson(paths)
else cases = loadCsvDir(paths[0] ?? "data/reveal-spread1-L8-starter")

// ───────── scoring ─────────

const DAY = 1440
const fmt = (m: number | null | undefined) => {
  if (m === null || m === undefined) return "-"
  const d = Math.floor(m / DAY)
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon2", "Tue2", "Wed2"]
  const mm = ((m % DAY) + DAY) % DAY
  return `${names[d] ?? `d${d}`} ${String(Math.floor(mm / 60)).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`
}
const fmtH = (h: { opens: number; closes: number } | null | undefined) => (h ? `${fmt(h.opens).slice(-5)}-${fmt(h.closes).slice(-5)}` : "-")

type Score = { tp: number; fp: number; fn: number; wrong: number; loose: number; misses: string[] }
const FACTS = ["ready", "payment", "deadline", "pHours", "dHours", "plates", "manual", "summer"] as const
type FactName = (typeof FACTS)[number]
const score = Object.fromEntries(FACTS.map((f) => [f, { tp: 0, fp: 0, fn: 0, wrong: 0, loose: 0, misses: [] } as Score])) as Record<FactName, Score>

/** One comparison: predicted/truth values are "unchanged" when null. */
function judge(fact: FactName, predicted: string | null, truth: string | null, line: string, loose = false) {
  const s = score[fact]
  if (predicted === truth) {
    if (truth !== null) s.tp++
    return
  }
  if (truth === null) {
    if (loose) {
      s.loose++
      return
    }
    s.fp++
    s.misses.push(`FP    ${line}  reader=${predicted}`)
  } else if (predicted === null) {
    s.fn++
    s.misses.push(`FN    ${line}  truth=${truth}`)
  } else {
    s.wrong++
    s.misses.push(`WRONG ${line}  reader=${predicted} truth=${truth}`)
  }
}

let withNote = 0
let withTruth = 0
let unparsed = 0
const unparsedLines: string[] = []
for (const c of cases) {
  const q = c.request
  if (!q.note) continue
  withNote++
  let facts: NoteFacts | null
  try {
    facts = readNote(q.note, q)
  } catch (e) {
    console.log(`CRASH ${c.key} ${q.note.text}: ${(e as Error).stack}`)
    continue
  }
  const line = `${c.key} ${q.note.language} arr ${fmt(q.arrivedAt)} | ${q.note.text}`
  if (facts?.unparsed) {
    unparsed++
    unparsedLines.push(`${line}   ${JSON.stringify(debugNote(q.note.text))}`)
  }
  if (!c.truth) continue
  withTruth++
  const t = c.truth[0]!
  const leg = q.legs[0]!
  const stated = leg.pickup.window.from

  // ready
  const readyPred = facts?.readyFrom != null ? Math.max(stated, facts.readyFrom) : stated
  judge("ready", readyPred === stated ? null : fmt(readyPred), t.readyAt === stated ? null : fmt(t.readyAt), `${line}  stated=${fmt(stated)}`)
  // payment
  judge("payment", facts?.afterPayment != null ? fmt(facts.afterPayment) : null, t.releasedAt != null ? fmt(t.releasedAt) : null, line)
  // deadline: the order's deadline moves by the days the car is ready late
  const opt = q.options.find((o) => o.kind === c.option) ?? q.options[0]!
  const shift = Math.max(0, Math.floor(t.readyAt / DAY) - Math.floor(stated / DAY)) * DAY
  const orderDeadline = (leg.delivery.privateAddress ? leg.delivery.window.to : opt.deadline) + shift
  const dl = facts?.deadline ?? null
  judge("deadline", dl !== null ? fmt(dl) : null, t.noteDeadline != null ? fmt(t.noteDeadline) : null, `${line}  order=${fmt(orderDeadline)}`, dl !== null && dl >= orderDeadline)
  // hours
  for (const [fact, statedH, truthH, partial] of [
    ["pHours", leg.pickup.hours, t.pickupHours, facts?.pickupHours],
    ["dHours", leg.delivery.hours, t.deliveryHours, facts?.deliveryHours],
  ] as const) {
    const merged = partial && statedH ? { ...statedH, ...partial } : (statedH ?? null)
    const changedTruth = fmtH(truthH) !== fmtH(statedH)
    const changedPred = fmtH(merged) !== fmtH(statedH)
    judge(fact, changedPred ? fmtH(merged) : null, changedTruth ? fmtH(truthH) : null, `${line}  stated=${fmtH(statedH)}`, changedPred && !changedTruth && fmtH(merged) === fmtH(truthH))
  }
  judge("plates", facts?.plates ? "yes" : null, t.needsPlates ? "yes" : null, line)
  judge("manual", facts?.manual ? "yes" : null, t.manualGearbox ? "yes" : null, line)
  judge("summer", facts?.summerTyres ? "yes" : null, t.summerTyres ? "yes" : null, line)
}

console.log(`requests ${cases.length}, with a note ${withNote}, with a note and truth ${withTruth}, flagged unparsed ${unparsed}`)
console.log("fact      TP   FP   FN  WRONG  LOOSE  precision  recall")
for (const f of FACTS) {
  const s = score[f]
  const prec = s.tp + s.fp + s.wrong ? s.tp / (s.tp + s.fp + s.wrong) : 1
  const rec = s.tp + s.fn + s.wrong ? s.tp / (s.tp + s.fn + s.wrong) : 1
  console.log(`${f.padEnd(8)} ${String(s.tp).padStart(4)} ${String(s.fp).padStart(4)} ${String(s.fn).padStart(4)} ${String(s.wrong).padStart(6)} ${String(s.loose).padStart(6)}  ${prec.toFixed(3).padStart(9)}  ${rec.toFixed(3).padStart(6)}`)
}
if (!flag("--quiet")) {
  for (const f of FACTS) {
    if (!score[f].misses.length) continue
    console.log(`\n── ${f} ──`)
    for (const m of score[f].misses) console.log(m)
  }
  if (flag("--unparsed")) {
    console.log(`\n── unparsed (${unparsedLines.length}) ──`)
    for (const l of unparsedLines) console.log(l)
  }
}
