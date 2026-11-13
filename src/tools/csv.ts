/** CSV in and out with no dependencies. RFC 4180: a cell with a comma, a quote or a newline is quoted and its
 * quotes doubled. null/undefined → empty cell; booleans → true/false; arrays and objects → JSON (one column);
 * numbers as JavaScript prints them. The approach follows the kit's reveal-csv.ts (flat() and write()). */
import { readFileSync, writeFileSync } from "node:fs"

export type Row = Record<string, unknown>

/** One row from a nested object: nested objects give dotted column names, arrays give one JSON column. */
export function flat(value: object, prefix = "", row: Row = {}): Row {
  for (const [key, item] of Object.entries(value)) {
    if (item !== null && typeof item === "object" && !Array.isArray(item)) flat(item, `${prefix}${key}.`, row)
    else row[prefix + key] = item
  }
  return row
}

export function cell(value: unknown): string {
  if (value === null || value === undefined) return ""
  const text = typeof value === "object" ? JSON.stringify(value) : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/** The columns of a row set: the given list, else every key in order of first appearance. */
export function columnsOf(rows: Row[], columns?: string[]): string[] {
  if (columns) return columns
  const names = new Set<string>()
  for (const row of rows) for (const key of Object.keys(row)) names.add(key)
  return [...names]
}

export function toCsv(rows: Row[], columns?: string[]): string {
  const cols = columnsOf(rows, columns)
  const lines = [cols.map(cell).join(",")]
  for (const row of rows) lines.push(cols.map((c) => cell(row[c])).join(","))
  return lines.join("\n") + "\n"
}

/** Writes the rows; returns the number of rows. */
export function writeCsv(path: string, rows: Row[], columns?: string[]): number {
  writeFileSync(path, toCsv(rows, columns))
  return rows.length
}

/** Parses CSV text into rows keyed by the header. Every value is a string ("" for an empty cell).
 * Handles quoted cells with commas, doubled quotes and embedded newlines; accepts LF and CRLF. */
export function parseCsv(text: string): Row[] {
  const records: string[][] = []
  let record: string[] = []
  let field = ""
  let quoted = false
  let i = 0
  if (text.charCodeAt(0) === 0xfeff) i = 1 // byte-order mark
  while (i < text.length) {
    const ch = text[i]!
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i += 2
          continue
        }
        quoted = false
        i++
        continue
      }
      field += ch
      i++
      continue
    }
    if (ch === '"') {
      quoted = true
      i++
      continue
    }
    if (ch === ",") {
      record.push(field)
      field = ""
      i++
      continue
    }
    if (ch === "\r" || ch === "\n") {
      record.push(field)
      field = ""
      records.push(record)
      record = []
      i += ch === "\r" && text[i + 1] === "\n" ? 2 : 1
      continue
    }
    field += ch
    i++
  }
  if (field !== "" || record.length > 0) {
    record.push(field)
    records.push(record)
  }
  if (records.length === 0) return []
  const header = records[0]!
  const rows: Row[] = []
  for (const rec of records.slice(1)) {
    if (rec.length === 1 && rec[0] === "") continue // a blank line
    const row: Row = {}
    header.forEach((name, j) => (row[name] = rec[j] ?? ""))
    rows.push(row)
  }
  return rows
}

export function readCsv(path: string): Row[] {
  return parseCsv(readFileSync(path, "utf8"))
}

/** A number rounded to `digits` decimals, or null when it is not finite (so a CSV cell stays empty). */
export function round(value: number | null | undefined, digits = 3): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const f = 10 ** digits
  return Math.round(value * f) / f
}
