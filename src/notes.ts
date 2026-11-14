/** 6.8 Note reader (fi/sv/en). Stub until M5: returns null (no facts), so feasibility uses the stated windows. */
import type { Note, PriceRequest } from "./client/types.ts"
import type { OpeningHours } from "./client/types.ts"

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

export function readNote(_note: Note | null, _request: PriceRequest): NoteFacts | null {
  return null
}
