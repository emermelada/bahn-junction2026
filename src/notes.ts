/** 6.8 Note reader (fi/sv/en). Rules: docs/RULES.md, "Notes and changes of plan".
 *
 * readNote(note, request) → the facts a dealer note states, or null when it states none.
 *   readyFrom     absolute world minute: the car cannot be collected before it ("valmis huomenna klo 11.30").
 *                 Can be earlier than the stated pickup window: use max(window.from, readyFrom).
 *   afterPayment  absolute world minute: handed over only after payment, not before it (the world sends
 *                 `release` then). Not folded into readyFrom: use max(window.from, readyFrom, afterPayment).
 *   pickupHours / deliveryHours  opens/closes in minutes of day, to merge over the stated hours (weekdays and
 *                 Saturday are never set: notes in the data only move the opening/closing minute).
 *   deadline      absolute world minute: latest delivery ("perillä huomenna klo 15 mennessä"). Not cut to the
 *                 option deadline: use min(option deadline, deadline). The world ignores a note deadline that
 *                 is not tighter than the order's deadline.
 *   plates / manual / summerTyres  the driver must bring transfer plates / needs a manual licence / the car
 *                 still runs on summer tyres (not "summer tyres in the trunk").
 *   unparsed      the note has a clock time or a day word that no rule could place.
 * All absolute times are world minutes from Monday 00:00 (day d starts at d*1440). Days count from the day the
 * request arrives (request.arrivedAt). The text is folded (lower case, ä/å→a, ö→o) and spell-corrected against
 * the keyword lexicon below (dealer notes carry typos: "smumer", "jäleken", "befre"), then read clause by clause.
 */
import type { Note, OpeningHours, PriceRequest } from "./client/types.ts"

export type NoteFacts = {
  readyFrom: number | null
  afterPayment: number | null
  pickupHours: Partial<OpeningHours> | null
  deliveryHours: Partial<OpeningHours> | null
  deadline: number | null
  plates: boolean
  manual: boolean
  summerTyres: boolean
  unparsed: boolean
}

const DAY = 1440

// ───────────────────────────── 1. Folding and spelling ─────────────────────────────

function fold(text: string): string {
  return text
    .toLowerCase()
    .replace(/[äåáà]/g, "a")
    .replace(/[öó]/g, "o")
    .replace(/[éè]/g, "e")
    .replace(/ü/g, "u")
    .replace(/[–—−]/g, "-")
    .replace(/\ba\.m\.?/g, "am")
    .replace(/\bp\.m\.?/g, "pm")
    .replace(/\s+/g, " ")
    .trim()
}

/** Finnish clock-hour words in all the cases notes use: "kolme", "kolmelta" (at), "kolmesta" (from),
 * "kolmeen" (until/by), "kolmen" (genitive, "kolmen jälkeen"). Checked in this order (9 before 1, 11 before 1). */
const FI_NUM: [RegExp, number][] = [
  [/^yhdeksa(n|lta|sta|an)$/, 9],
  [/^kahdeksa(n|lta|sta|an)$/, 8],
  [/^(yksi|yhde(n|lta|sta)|yhteen)toista$/, 11],
  [/^(kaksi|kahde(n|lta|sta)|kahteen)toista$/, 12],
  [/^(yksi|yhde(n|lta|sta)|yhteen)$/, 1],
  [/^(kaksi|kahde(n|lta|sta)|kahteen)$/, 2],
  [/^kolme(n|lta|sta|en)?$/, 3],
  [/^nelja(n|lta|sta|an)?$/, 4],
  [/^(viisi|viide(n|lta|sta)|viiteen)$/, 5],
  [/^(kuusi|kuude(n|lta|sta)|kuuteen)$/, 6],
  [/^seitsema(n|lta|sta|an)$/, 7],
  [/^kymmene(n|lta|sta|en)$/, 10],
]
const SV_NUM: Record<string, number> = { ett: 1, tva: 2, tre: 3, fyra: 4, fem: 5, sex: 6, sju: 7, atta: 8, nio: 9, tio: 10, elva: 11, tolv: 12 }
const EN_NUM: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 }

function fiNumber(word: string): number | null {
  for (const [re, n] of FI_NUM) if (re.test(word)) return n
  return null
}

/** Keywords the rules below look for. A word of 5+ letters that is not one of them but is one edit
 * (insert, delete, substitute, swap two neighbours) away from exactly one of them is read as that keyword. */
const LEXICON = [
  // days (fi / sv / en)
  "huomenna", "ylihuomenna", "tanaan", "maanantai", "maanantaina", "tiistai", "tiistaina", "keskiviikko",
  "keskiviikkona", "torstai", "torstaina", "perjantai", "perjantaina", "lauantai", "lauantaina", "imorgon",
  "morgon", "overmorgon", "iovermorgon", "mandag", "tisdag", "onsdag", "torsdag", "fredag", "lordag", "sondag",
  "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
  // clock words
  "alkaen", "jalkeen", "aikaisintaan", "viimeistaan", "mennessa", "saakka", "kello", "klockan", "framat",
  "tidigast", "senast", "before", "after", "until", "latest", "earliest", "o'clock", "korjaus", "rattelse",
  "kymmenen", "kymmenelta", "kymmenesta", "kymmeneen", "kahdeksan", "kahdeksalta", "kahdeksasta", "yhdeksan",
  "yhdeksalta", "yhdeksasta", "yhdeksaan", "kahdeksaan", "seitseman", "kolmelta", "kolmesta", "kolmeen", "kolmen",
  "neljalta", "neljasta", "neljaan", "neljan", "viidelta", "viidesta", "viiteen", "viiden", "kuudelta", "kuudesta",
  "kuuteen", "kahdelta", "kahdesta", "kahteen", "kahden", "yhdelta", "yhdesta", "yhteen", "yhden", "yhdeltatoista",
  "yhdestatoista", "yhdentoista", "kahdeltatoista", "kahdestatoista", "kahdentoista", "yksitoista", "kaksitoista",
  // ready / release
  "valmis", "valmiina", "valmistuu", "noudettavissa", "noudettavaksi", "haettavissa", "noutaa", "hakea", "vasta",
  "ready", "collect", "collected", "pickup", "available", "hamtas", "hamta", "hamtning", "forst",
  "maksun", "maksu", "maksaa", "maksettu", "maksetaan", "ensin", "luovutus", "luovutetaan", "rahoitus",
  "payment", "released", "release", "betalning", "betalat", "betalar", "betald",
  // deadline
  "perilla", "perille", "toimitus", "oltava", "destination", "arrival", "arrive", "framme", "levereras",
  // opening hours
  "vastaanotto", "vastaanottava", "vastaanottaja", "toimitusosoite", "kohde", "liike", "auki", "kiinni",
  "aukioloajat", "arkisin", "arkipaivisin", "ennen", "haettava", "nouto", "receiving", "closes", "close",
  "weekdays", "oppet", "stanger", "sulkee", "suljetaan", "sulkeutuu", "avoinna", "nobody", "later", "kotona", "paikalla", "tavattavissa", "mottagaren", "mottagning", "vardagar", "ollaan", "taalla",
  // plates / gearbox / tyres
  "kilpia", "kilvet", "siirtokilvet", "koekilvet", "rekkareita", "puuttuu", "puuttuvat", "poistettu", "plates",
  "trade", "removed", "without", "skyltar", "provskyltar", "manuaali", "manuaalivaihteinen", "automaatti", "manual",
  "automatic", "manuell", "manuellt", "licence", "license", "kesarenkailla", "kesarenkaat", "kesarengasta",
  "kesarenkaita", "summer", "tyres", "tires", "winters", "sommardack", "sommardacken", "takakontissa",
  "tavaratilassa", "kontissa", "vanteineen", "trunk", "bakluckan", "bagaget", "lisaksi",
]
const LEXICON_SET = new Set(LEXICON)

/** True when a and b are at most one edit apart (optimal string alignment distance ≤ 1). */
function oneEdit(a: string, b: string): boolean {
  if (a === b) return true
  const la = a.length
  const lb = b.length
  if (Math.abs(la - lb) > 1) return false
  if (la === lb) {
    let i = 0
    while (i < la && a[i] === b[i]) i++
    if (a.slice(i + 1) === b.slice(i + 1)) return true // one substitution
    return a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2) // one swap
  }
  const [s, l] = la < lb ? [a, b] : [b, a]
  let i = 0
  while (i < s.length && s[i] === l[i]) i++
  return s.slice(i) === l.slice(i + 1) // one insertion
}

const spellCache = new Map<string, string>()
function correct(word: string): string {
  if (word.length < 5 || LEXICON_SET.has(word) || fiNumber(word) !== null) return word
  const hit = spellCache.get(word)
  if (hit !== undefined) return hit
  let found = word
  for (const k of LEXICON) {
    if (k.length >= 5 && oneEdit(word, k)) {
      found = k
      break
    }
  }
  spellCache.set(word, found)
  return found
}

function normalise(text: string): string {
  return fold(text).replace(/[a-z]+/g, (w) => correct(w))
}

// ───────────────────────────── 2. Clauses ─────────────────────────────

/** Words that end in a full stop without ending the sentence: "viim. klo 17", "to. klo 10.30", "pe. klo 20". */
const ABBREV = new Set([
  "viim", "oik", "n", "t", "ma", "ti", "ke", "to", "pe", "la", "su", "klo", "kl", "mon", "tue", "tues", "wed", "thu",
  "thur", "thurs", "fri", "sat", "sun", "man", "tis", "ons", "tors", "fre", "lor", "son", "nro", "esim", "ns", "ca",
])

/** A clause that starts like this corrects the one before it ("korjaus: klo 20", "ei kun klo 9", "sorry, i mean 8pm"). */
const CORRECTION_START = /^(korjaus|rattelse|correction|sorry|i mean|ei kun|eikun|eiku|tarkoitan|siis|or rather|eller nej|nej|jag menar|menar|vaan|utan|(not|ei|inte) (klo |kl |kello |at |on |pa )?(\d|tomorrow|tmrw|huomenna|ylihuomenna|i morgon|imorgon|today|tanaan|idag))/

function sentences(text: string): string[] {
  const out: string[] = []
  let start = 0
  const boundary = /[.!?;]+\s+|\s\/\s|[!?]+$/g
  for (let m = boundary.exec(text); m; m = boundary.exec(text)) {
    if (m[0].startsWith(".") && !m[0].startsWith("..")) {
      const before = /([a-z]+)$/.exec(text.slice(start, m.index))
      if (before && ABBREV.has(before[1]!)) continue
    }
    out.push(text.slice(start, m.index))
    start = m.index + m[0].length
  }
  out.push(text.slice(start))
  const merged: string[] = []
  for (const raw of out) {
    const s = raw.replace(/[.!?]+$/, "").trim()
    if (!s) continue
    if (merged.length && CORRECTION_START.test(s)) merged[merged.length - 1] += " " + s
    else merged.push(s)
  }
  return merged
}

// ───────────────────────────── 3. Rule sets (on folded, corrected text) ─────────────────────────────

/** Rule: the delivery must arrive by the time ("perillä … mennessä", "by", "senast"). */
const DEADLINE = [
  // fi: "perillä huomenna klo 15 mennessä", "oltava perillä viimeistään", "perillä viim. klo 17.30",
  //     "toimitus perille viim. huomenna klo 14", "viimeistään huomenna viideltä perillä", "auton oltava silloin perillä"
  /\bperill?[ae]\b.*\b(mennessa|viim|viimeistaan)\b/,
  /\b(mennessa|viim|viimeistaan)\b.*\bperill?[ae]\b/,
  /\boltava\b.*\bperill?[ae]\b/,
  /\btoimitus\b.*\b(mennessa|viim|viimeistaan)\b/,
  // en: "at destination tomorrow 15:00 latest", "must be at destination by", "latest arrival", "must arrive by"
  /\bat (the )?destination\b/,
  /\blatest arrival\b/,
  /\b(arrive|arrival|delivered|deliver|delivery)\b.*\b(by|latest|no later)\b/,
  // en: "customer picks it up tomorrow 7pm, must be there by then"
  /\bmust be there\b|\bbe there by\b/,
  // sv: "framme senast i morgon kl 16", "levereras senast"
  /\bframme\b/,
  /\b(levereras|leverans|leverera)\b.*\bsenast\b/,
]

/** Words that put an opening-hours clause on the delivery stop; otherwise it is the pickup stop. */
const DELIVERY_STOP = /\b(vastaanot\w*|vastaanottava|vastaanottaja|kohde|toimitusosoite|perill?[ae]|receiving|destination|recipient|delivery address|drop ?off|mottagare\w*|mottagning\w*|leveransadress\w*|framme)\b/
/** Words that make a clause about the pickup stop's hours or its last pickup. */
const PICKUP_STOP = /\b(nouto|noudettavissa|haettava|haku|hakea|liike|aukioloajat|ollaan taalla|olemme|pickup|pick up|collect|shop|we close|we're|our hours|here|taalla|hamtning|hamtas|hamta|butiken|vi stanger)\b/
/** Opening hours: a time range with a stop or "open" word ("vastaanotto arkisin klo 7-21", "open weekdays 10:00-14:30"). */
const HOURS_WORD = /\b(auki|avoinna|aukioloajat|arkisin|arkipaivisin|ma-pe|open|opening|hours|weekdays|mon-fri|oppet|vardagar|man-fre|onnistuu|only)\b/
/** Closing only: "haettava ennen klo 16", "kiinni klo 16.30 jälkeen", "klo 18 asti", "collect before 16:30",
 * "receiving until 16:30 only", "shop closes 18:00", "vi stänger kl 20", "haku viimeistään klo 18". */
/** Closing words that say by themselves that a site closes ("liike sulkee klo 14.30", "nobody here after 19:00",
 * "klo 19 jälkeen ei enää luovutuksia", "vi stänger kl 20"). */
const SELF_CLOSE = /\b(kiinni|sulkee|suljetaan|sulkeutuu|closes|close|closing|stanger|nobody|no one|ei enaa|ei ketaan|ingen)\b/
/** Any closing word; besides SELF_CLOSE it needs a stop word ("haettava ennen", "pickup by 17:00 at the latest"). */
const CLOSE_WORD = new RegExp(`\\b(asti|saakka|ennen|until|till|before|no later than|latest|by|fore|viimeistaan|senast)\\b|${SELF_CLOSE.source}`)
/** Opening only: "vastaanotto klo 9 alkaen", "receiving from 9:00". */
const OPEN_FROM_WORD = /\b(alkaen|from|fran)\b/

/** Rule: the car is not ready before the time. */
const READY = [
  // fi: "voi noutaa klo 11.30 alkaen", "noudettavissa aikaisintaan huomenna klo 10", "valmis huomenna klo 11.30",
  //     "haettavissa huomenna 8 jälkeen", "saa hakea vasta", "auto valmistuu huomenna"
  /\b(valmis|valmiina|valmistuu|noudettavissa|noudettavaksi|haettavissa|alkaen|aikaisintaan|jalkeen|vasta)\b/,
  /\b(voi|saa) (noutaa|hakea|nouta)\b/,
  /\bei ennen\b/,
  // en: "ready for pickup from 14:00", "not ready before tomorrow 12:45", "won't be ready until tomorrow 4pm"
  /\b(ready|earliest|available|not before|from|after|onwards)\b/,
  // sv: "klar först på fredag kl 9", "kan hämtas i morgon kl 7 och framåt", "tidigast"
  /\b(klar|tidigast|framat|fran|efter|forst|hamtas)\b/,
]

/** Rule: handed over only after payment ("maksun jälkeen", "after payment", "efter betalning"). */
const PAYMENT = /\b(maksu\w*|maksa\w*|maksetaan|maksettu|rahoitus\w*|payment|paid|pays|pay|betal\w*)\b/

/** A private slot (the stated window already holds it): "myyjä paikalla 15.30-18.30", "omistaja kotona klo 14.15 - 17.15". */
const SLOT = /\b(paikalla|kotona|tavattavissa|myyja\w*|omistaja\w*|seller|owner|home|hemma|pa plats|saljare\w*|agare\w*)\b/

/** Rule: plates needed ("ei kilpiä", "no plates", "utan skyltar"). */
const PLATES = [
  /\bei (rekisteri)?kilpia\b|\b(rekisteri)?kilvet\b.*\b(puuttuu|puuttuvat|poistettu|irrotettu|pois)\b|\b(siirto|koe)kilv\w*|\bei rekkareita\b|\brekkarit\b.*\bpuuttu\w*|\bilman (rekisteri)?kilpia\b/,
  /\bno (trade |number |licen[cs]e |registration )?plates\b|\bplates\b.*\b(removed|missing|off)\b|\bwithout plates\b|\btrade plates\b|\btransfer plates\b|\bbring plates\b/,
  /\butan (registrerings)?skyltar\b|\binga skyltar\b|\bskyltar(na)?\b.*\b(saknas|borttagna|avtagna)\b|\b(prov|saluvagns|flytt)skyltar\b/,
]
const PLATES_NOT = /\b(ei tarvita|not needed|no need|behovs inte|kilvet paikallaan|plates on|has plates)\b/

/** Rule: manual gearbox ("manuaali", "manuell", "manual"), unless denied ("automatic, not a manual"). */
const MANUAL = /\b(manu\w*|stick ?shift|kasivaiht\w*)/g
const NEGATOR = /\b(not|ei|inte|no|eika|never|eller)\b\s*(a |an |en )?$/

/** Rule: the car runs on summer tyres; not "summer tyres in the trunk". */
const SUMMER = /\b(summer (tyres|tires|wheels)|kesarenk\w*|kesarengas\w*|sommardack\w*)/
const SUMMER_ON = /\b(on summer|summer (tyres|tires|wheels) on|still on|kesarenkailla|alla|pa sommardack\w*|sommardack\w* pa|har sommardack\w*|sitter|no winters?|no winter (tyres|tires)|viela kesaren\w*|(talvet|talvirenkaat)\b.*\bpuuttu\w*|ei talvirenkaita|inga vinterdack)\b/
const SUMMER_STORED = /\b(trunk|boot|back|seat|takakontissa|kontissa|tavaratilassa|takapenkilla|kyydissa|bakluckan|bagaget|baksatet|lisaksi|vanteineen|vanteilla|mukaan|mukana|go with|take along|extra|spare|ska med|foljer med)\b/

// ───────────────────────────── 4. Days and clock times ─────────────────────────────

type Tok = { t: string; num: boolean }

function tokens(text: string): Tok[] {
  const out: Tok[] = []
  for (const m of text.matchAll(/\d{1,2}[:.]\d{2}|\d+|[a-z]+(?:'[a-z]+)?|[^\sa-z\d]/g)) out.push({ t: m[0], num: /^\d/.test(m[0]) })
  return out
}

type DayItem = { at: number; offset: number; negated: boolean }
type TimeItem = { at: number; minute: number | null; negated: boolean }
type RangeItem = { at: number; opens: number; closes: number }

const NEG = new Set(["not", "ei", "inte", "eika", "nor", "never"])
const SKIP_BACK = new Set(["klo", "kl", "kello", "klockan", "at", "on", "pa", "(", "."])
const PREFIX = new Set([
  "klo", "kl", "kello", "klockan", "at", "by", "from", "until", "till", "before", "after", "ennen", "fran", "efter",
  "fore", "vid", "around", "about", "noin", "ca", "vaan", "kun", "eikun", "eiku", "mean", "korjaus", "rattelse",
  "utan", "rather", "menar", "siis", "past",
])
const POSTFIX = new Set(["jalkeen", "alkaen", "asti", "saakka", "mennessa", "och", "framat", "o'clock", "oclock", "sharp", "latest", "onwards"])
const UNIT = new Set([
  "min", "mins", "minute", "minutes", "minuuttia", "minuutin", "minuutti", "minuter", "minuten", "h", "tuntia",
  "tunnin", "tunti", "hour", "hours", "timme", "timmar", "km", "kpl", "st", "paivaa", "days", "dagar", "sarjaa",
  "rengasta", "%", "eur", "euro", "e", "€", "kg", "x",
])

const WEEKDAY_FULL: [RegExp, number][] = [
  [/^(maanantai\w*|mandag\w*|monday)$/, 0],
  [/^(tiistai\w*|tisdag\w*|tuesday)$/, 1],
  [/^(keskiviikko\w*|onsdag\w*|wednesday)$/, 2],
  [/^(torstai\w*|torsdag\w*|thursday)$/, 3],
  [/^(perjantai\w*|fredag\w*|friday)$/, 4],
  [/^(lauantai\w*|lordag\w*|saturday)$/, 5],
  [/^(sunnuntai\w*|sondag\w*|sunday)$/, 6],
]
/** Short forms that are not ordinary words: always a weekday. */
const WEEKDAY_SHORT_SAFE: Record<string, number> = { tue: 1, tues: 1, thu: 3, thur: 3, thurs: 3, fri: 4, tis: 1, ons: 2, tors: 3, fre: 4 }
/** Short forms that are also ordinary words ("to", "sun"): a weekday only when a period or a clock time follows. */
const WEEKDAY_SHORT_RISKY: Record<string, number> = { ma: 0, ti: 1, ke: 2, to: 3, pe: 4, la: 5, su: 6, mon: 0, wed: 2, sat: 5, sun: 6, man: 0, lor: 5, son: 6 }

function weekdayOf(word: string): number | null {
  for (const [re, w] of WEEKDAY_FULL) if (re.test(word)) return w
  return null
}

/** A weekday name means that weekday 2 to 6 days after the arrival day. */
function weekdayOffset(arrivalDay: number, weekday: number): number {
  for (let k = 2; k <= 6; k++) if ((arrivalDay + k) % 7 === weekday) return k
  for (let k = 1; k <= 7; k++) if ((arrivalDay + k) % 7 === weekday) return k
  return 0
}

/** The working hour that a number word names, 9 to 17 ("two" = 14:00); null for six to eight. */
function workingHour(n: number): number | null {
  if (n >= 9 && n <= 12) return n
  if (n >= 1 && n <= 5) return n + 12
  return null
}

function isClockToken(tok: Tok | undefined): boolean {
  return !!tok && (/^\d{1,2}[:.]\d{2}$/.test(tok.t) || (/^\d{1,2}$/.test(tok.t) && Number(tok.t) <= 24))
}

type Scan = { days: DayItem[]; times: TimeItem[]; ranges: RangeItem[]; weekdayRange: boolean }

function scan(text: string, arrivalDay: number): Scan {
  const tk = tokens(text)
  const days: DayItem[] = []
  const times: TimeItem[] = []
  const ranges: RangeItem[] = []
  let weekdayRange = false
  const used = new Set<number>()
  const word = (i: number) => tk[i]?.t ?? ""

  const negatedAt = (i: number): boolean => {
    let j = i - 1
    while (j >= 0 && (SKIP_BACK.has(word(j)) || dayAt(j) !== null)) j--
    return j >= 0 && NEG.has(word(j))
  }

  /** The day offset a token (or a two-token phrase ending at i) names; null if none. */
  function dayAt(i: number): number | null {
    const w = word(i)
    if (w === "tanaan" || w === "idag" || w === "today" || w === "tonight" || (w === "dag" && word(i - 1) === "i")) return 0
    if (w === "ylihuomenna" || w === "iovermorgon" || (w === "overmorgon" && word(i - 1) === "i")) return 2
    if (w === "tomorrow" && word(i - 1) === "after" && word(i - 2) === "day") return 2
    if (w === "huomenna" || w === "huomiseksi" || w === "imorgon" || w === "tomorrow" || w === "tmrw" || w === "tmr" || w === "tomoz" || (w === "morgon" && word(i - 1) === "i")) return 1
    return null
  }

  for (let i = 0; i < tk.length; i++) {
    const w = word(i)
    // ── day words ──
    const rel = dayAt(i)
    if (rel !== null) {
      days.push({ at: i, offset: rel, negated: negatedAt(i - (w === "morgon" || w === "overmorgon" || w === "dag" ? 1 : 0)) })
      continue
    }
    let wd = weekdayOf(w)
    if (wd === null && w in WEEKDAY_SHORT_SAFE) wd = WEEKDAY_SHORT_SAFE[w]!
    if (wd === null && w in WEEKDAY_SHORT_RISKY) {
      const next = word(i + 1)
      const prevIsClock = isClockToken(tk[i - 1]) || word(i - 1) === "-"
      const nextIsClock =
        next === "." || next === "klo" || next === "kl" || next === "kello" || next === "klockan" || isClockToken(tk[i + 1]) ||
        /^(noon|midday|keskipaivalla|middag)$/.test(next) || /(lta|een|aan)(toista)?$/.test(next) && fiNumber(next) !== null
      if (!prevIsClock && nextIsClock) wd = WEEKDAY_SHORT_RISKY[w]!
    }
    if (wd !== null) {
      const isDayToken = (j: number) => weekdayOf(word(j)) !== null || word(j) in WEEKDAY_SHORT_SAFE || word(j) in WEEKDAY_SHORT_RISKY
      if ((word(i + 1) === "-" && isDayToken(i + 2)) || (word(i - 1) === "-" && isDayToken(i - 2))) {
        weekdayRange = true // "ma-pe", "mon-fri": opening days, not a day
        continue
      }
      days.push({ at: i, offset: weekdayOffset(arrivalDay, wd), negated: negatedAt(i) })
    }
  }

  /** A clock time starting at token i: [minute of day (null = a word hour with no working hour), tokens used]. */
  const clockAt = (i: number, inRange: boolean): [number | null, number] | null => {
    const tok = tk[i]
    if (!tok) return null
    const w = tok.t
    const next = word(i + 1)
    const ampm = next === "am" || next === "pm" ? next : null
    const withAmPm = (h: number) => (ampm === "pm" ? (h % 12) + 12 : ampm === "am" ? h % 12 : h)
    let m = /^(\d{1,2})[:.](\d{2})$/.exec(w)
    if (m) {
      const h = Number(m[1])
      const mm = Number(m[2])
      if (h > 24 || mm > 59) return null
      return [withAmPm(h) * 60 + mm, ampm ? 2 : 1]
    }
    if (/^\d+$/.test(w)) {
      const prev = word(i - 1) === "." ? word(i - 2) : word(i - 1)
      // "kello 1330": four digits after klo/kello
      if (/^\d{3,4}$/.test(w) && (prev === "klo" || prev === "kello" || prev === "kl" || prev === "klockan")) {
        const h = Math.floor(Number(w) / 100)
        const mm = Number(w) % 100
        return h <= 24 && mm <= 59 ? [h * 60 + mm, 1] : null
      }
      if (w.length > 2) return null
      const h = Number(w)
      if (h > 24 || UNIT.has(next)) return null
      if (ampm) return [withAmPm(h) * 60, 2]
      // "8:sta 21:een" (Finnish case endings on a bare hour)
      if (next === ":" && /^(sta|een|aan|lta|ksi|n)$/.test(word(i + 2))) return [h * 60, 3]
      const hasContext = inRange || PREFIX.has(prev) || POSTFIX.has(next) || dayAt(i - 1) !== null || (word(i - 1) === "." && dayAt(i - 2) !== null)
      return hasContext ? [h * 60, 1] : null
    }
    // hours in words
    const prev = word(i - 1)
    const fi = fiNumber(w)
    const sv = SV_NUM[w]
    const en = EN_NUM[w]
    let n: number | null = null
    if (fi !== null) {
      const selfContext = /(lta|sta|een|aan)(toista)?$/.test(w)
      if (selfContext || PREFIX.has(prev) || POSTFIX.has(next) || prev === "puoli" || prev === "yli" || prev === "vaille") n = fi
    } else if (sv !== undefined) {
      if (prev === "halv" || prev === "kl" || prev === "klockan" || prev === "over" || prev === "kvart" || PREFIX.has(prev) || next === "och") n = sv
    } else if (en !== undefined) {
      if (prev === "half" || prev === "past" || prev === "to" || PREFIX.has(prev) || next === "o'clock" || next === "oclock" || ampm) n = en
    } else if (w === "noon" || w === "midday" || w === "keskipaivalla" || w === "middag") {
      return [12 * 60, 1]
    }
    if (n === null) return null
    if (ampm) return [withAmPm(n) * 60, 2]
    const h = workingHour(n)
    if (h === null) return [null, 1]
    // "half three" = 14:30, "puoli kolme", "halv tre"; "half past three" = 15:30; quarters likewise
    const p1 = prev
    const p2 = word(i - 2)
    if (p1 === "puoli" || p1 === "halv" || (p1 === "half" && p2 !== "past")) return [h * 60 - 30, 1]
    if (p1 === "past" && p2 === "half") return [h * 60 + 30, 1]
    if ((p1 === "past" && p2 === "quarter") || (p1 === "yli" && p2 === "varttia") || (p1 === "over" && p2 === "kvart")) return [h * 60 + 15, 1]
    if ((p1 === "to" && p2 === "quarter") || (p1 === "vaille" && p2 === "varttia") || (p1 === "i" && p2 === "kvart")) return [h * 60 - 15, 1]
    return [h * 60, 1]
  }

  for (let i = 0; i < tk.length; i++) {
    if (used.has(i)) continue
    // ranges: "7-21", "7.00-17.00", "9:00 - 15:00", "7am - 8pm", "8:sta 21:een", "7:00 to 16:00"
    const a = isClockToken(tk[i]) ? clockAt(i, true) : null
    if (a && a[0] !== null) {
      const j = i + a[1]
      const sep = word(j)
      const explicitA = /[:.]/.test(word(i)) || a[1] === 2
      let b: [number | null, number] | null = null
      let bAt = -1
      if (sep === "-" && isClockToken(tk[j + 1])) {
        b = clockAt(j + 1, true)
        bAt = j + 1
      } else if ((sep === "to" || sep === "till" || sep === "until") && explicitA && isClockToken(tk[j + 1])) {
        b = clockAt(j + 1, true)
        bAt = j + 1
      } else if (a[1] === 3 && isClockToken(tk[j])) {
        b = clockAt(j, true) // "8:sta 21:een"
        bAt = j
      }
      if (b && b[0] !== null && bAt >= 0 && !UNIT.has(word(bAt + b[1]))) {
        const opens = a[0]
        const closes = b[0]
        if (opens < closes) {
          ranges.push({ at: i, opens, closes })
          for (let k = i; k < bAt + b[1]; k++) used.add(k)
          continue
        }
      }
    }
    const c = clockAt(i, false)
    if (c) {
      times.push({ at: i, minute: c[0], negated: negatedAt(i - (word(i - 1) === "puoli" || word(i - 1) === "half" || word(i - 1) === "halv" ? 1 : 0)) })
      for (let k = i; k < i + c[1]; k++) used.add(k)
    }
  }
  return { days, times, ranges, weekdayRange }
}

// ───────────────────────────── 5. Reading ─────────────────────────────

type Kind = "slot" | "deadline" | "hours" | "ready" | "none"

function hasTrigger(s: string): boolean {
  return (
    SLOT.test(s) ||
    DEADLINE.some((re) => re.test(s)) ||
    HOURS_WORD.test(s) ||
    CLOSE_WORD.test(s) ||
    READY.some((re) => re.test(s)) ||
    PAYMENT.test(s) ||
    DELIVERY_STOP.test(s) ||
    PICKUP_STOP.test(s)
  )
}

/** A sentence cut at commas; a piece with no trigger word, or one that starts as a correction, joins its neighbour. */
function segments(sentence: string): string[] {
  const parts = sentence.split(/,\s*|\s+\(|\)\s*/).map((p) => p.trim()).filter((p) => p)
  const out: string[] = []
  let pending = ""
  for (const p of parts) {
    if (out.length && (CORRECTION_START.test(p) || /^\(?(not|ei|inte)\b/.test(p) || !hasTrigger(p))) {
      out[out.length - 1] += " " + p
    } else if (!out.length && !hasTrigger(p)) {
      pending += (pending ? " " : "") + p
    } else {
      out.push(pending ? pending + " " + p : p)
      pending = ""
    }
  }
  if (pending) out.push(pending)
  return out
}

function classify(seg: string, sc: Scan): Kind {
  if (SLOT.test(seg) && !DEADLINE.some((re) => re.test(seg))) return "slot"
  // "nobody at the destination after 6pm" is a closing time, not a deadline
  const closesOnly = SELF_CLOSE.test(seg) && !/\b(latest|mennessa|viim|viimeistaan|senast|by|must)\b/.test(seg)
  if (DEADLINE.some((re) => re.test(seg)) && !closesOnly) return "deadline"
  const stopWord = DELIVERY_STOP.test(seg) || PICKUP_STOP.test(seg) || HOURS_WORD.test(seg)
  if (sc.ranges.length && stopWord) return "hours"
  if (CLOSE_WORD.test(seg) && (DELIVERY_STOP.test(seg) || PICKUP_STOP.test(seg) || SELF_CLOSE.test(seg) || /\b(auki|avoinna|open|oppet)\b/.test(seg))) {
    // "won't be ready until 4pm" and "ei ennen huomenna" are ready times, not closing times
    if (!/\b(ready|valmis|valmiina|valmistuu|klar|ei ennen|not before|inte fore)\b/.test(seg)) return "hours"
  }
  if (HOURS_WORD.test(seg) && /\b(auki|avoinna|open|oppet|vastaanotto|receiving)\b/.test(seg) && OPEN_FROM_WORD.test(seg)) return "hours"
  if (READY.some((re) => re.test(seg)) || PAYMENT.test(seg)) return "ready"
  return "none"
}

/** The last time the clause does not deny ("klo 8, ei kun klo 9" → 9; "8:30 (not 9:30)" → 8:30). */
function lastTime(sc: Scan): TimeItem | null {
  for (let i = sc.times.length - 1; i >= 0; i--) if (!sc.times[i]!.negated) return sc.times[i]!
  return null
}
function lastDay(sc: Scan): number {
  for (let i = sc.days.length - 1; i >= 0; i--) if (!sc.days[i]!.negated) return sc.days[i]!.offset
  return 0
}

export function readNote(note: Note | null, request: PriceRequest): NoteFacts | null {
  if (!note || !note.text || !note.text.trim()) return null
  const arrivalDay = Math.floor(request.arrivedAt / DAY)
  const text = normalise(note.text)
  const facts: NoteFacts = {
    readyFrom: null,
    afterPayment: null,
    pickupHours: null,
    deliveryHours: null,
    deadline: null,
    plates: false,
    manual: false,
    summerTyres: false,
    unparsed: false,
  }
  const maxOf = (a: number | null, b: number) => (a === null ? b : Math.max(a, b))
  const minOf = (a: number | null, b: number) => (a === null ? b : Math.min(a, b))

  for (const sentence of sentences(text)) {
    // ── yes/no facts, read per sentence ──
    if (PLATES.some((re) => re.test(sentence)) && !PLATES_NOT.test(sentence)) facts.plates = true
    for (const m of sentence.matchAll(MANUAL)) {
      const before = sentence.slice(Math.max(0, m.index - 12), m.index)
      if (!NEGATOR.test(before)) facts.manual = true
    }
    if (SUMMER.test(sentence) && SUMMER_ON.test(sentence) && !SUMMER_STORED.test(sentence)) facts.summerTyres = true

    // ── times, read per clause ──
    const payment = PAYMENT.test(sentence)
    for (const seg of segments(sentence)) {
      const sc = scan(seg, arrivalDay)
      const hasTime = sc.times.length > 0 || sc.ranges.length > 0
      const hasDay = sc.days.length > 0
      if (!hasTime && !hasDay) continue
      if (sc.times.some((t) => t.minute === null && !t.negated)) facts.unparsed = true // "six" has no working hour
      // a clause that only denies a time ("haettava ennen sitä (ei klo 16)") states nothing new
      if (!sc.ranges.length && sc.times.length && sc.times.every((t) => t.negated)) continue
      const kind = classify(seg, sc)
      const t = lastTime(sc)
      const at = t && t.minute !== null ? (arrivalDay + lastDay(sc)) * DAY + t.minute : null
      if (kind === "slot") continue
      if (kind === "deadline") {
        if (at !== null) facts.deadline = minOf(facts.deadline, at)
        else facts.unparsed = true
        continue
      }
      if (kind === "hours") {
        const delivery = DELIVERY_STOP.test(seg)
        const prev = (delivery ? facts.deliveryHours : facts.pickupHours) ?? {}
        const h: Partial<OpeningHours> = { ...prev }
        const range = sc.ranges[sc.ranges.length - 1]
        if (range) {
          h.opens = range.opens
          h.closes = range.closes
        } else if (t && t.minute !== null) {
          if (CLOSE_WORD.test(seg)) h.closes = h.closes === undefined ? t.minute : Math.min(h.closes, t.minute)
          else h.opens = h.opens === undefined ? t.minute : Math.max(h.opens, t.minute)
        } else {
          facts.unparsed = true
          continue
        }
        if (delivery) facts.deliveryHours = h
        else facts.pickupHours = h
        continue
      }
      if (kind === "ready") {
        if (at === null) {
          if (hasTime || hasDay) facts.unparsed = true
          continue
        }
        if (payment) facts.afterPayment = maxOf(facts.afterPayment, at)
        else facts.readyFrom = maxOf(facts.readyFrom, at)
        continue
      }
      facts.unparsed = true
    }
  }

  const any =
    facts.readyFrom !== null ||
    facts.afterPayment !== null ||
    facts.pickupHours !== null ||
    facts.deliveryHours !== null ||
    facts.deadline !== null ||
    facts.plates ||
    facts.manual ||
    facts.summerTyres ||
    facts.unparsed
  return any ? facts : null
}

/** For tools: the folded, spell-corrected text and its clauses, to see how a note was cut. */
export function debugNote(text: string): string[][] {
  return sentences(normalise(text)).map((s) => segments(s))
}
