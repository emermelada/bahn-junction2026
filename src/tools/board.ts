/** Practice board, level 8: per team margin sum / on-time / weekly runs. node src/tools/board.ts */
import { Client } from "../client/spread.ts"
process.loadEnvFile(new URL("../../.env", import.meta.url))
const b: any = await new Client().board(8)
for (const key of ["current", "previous"]) {
  const r = b[key]
  if (!r) continue
  console.log(`== ${key} round ${r.season ?? ""} ${r.startsAt ?? ""}`)
  for (const t of (r.teams ?? []).slice(0, 12)) {
    const runs = (t.runs ?? []).map((x: any) => `${(x.marginCents / 100).toFixed(0)}/${(100 * x.onTimeShare).toFixed(0)}%/${x.wonOrders}`).join(" ")
    console.log(`${String(t.rank ?? "-").padStart(3)} ${String(t.name ?? t.team).slice(0, 22).padEnd(22)} €${((t.marginCents ?? 0) / 100).toFixed(0).padStart(7)} played ${t.played}  ${runs}`)
  }
}
