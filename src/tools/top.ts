import { Client } from "../client/spread.ts"
process.loadEnvFile(new URL("../../.env", import.meta.url))
const c = new Client()
const b: any = await c.board(8)
const r = b.current
const teams = r.teams.filter((t: any) => t.ranked).sort((a: any, z: any) => a.rank - z.rank)
for (const t of teams.slice(0, 25)) {
  const runs = t.runs.map((x: any) => `${(x.marginCents / 100).toFixed(0)}/${x.wonOrders}/${(x.onTimeShare * 100).toFixed(0)}`).join("  ")
  const won = t.runs.reduce((s: number, x: any) => s + x.wonOrders, 0)
  console.log(String(t.rank).padStart(3), String(t.name).slice(0, 22).padEnd(22), (t.marginCents / 100).toFixed(0).padStart(7), "won/run", (won / t.runs.length).toFixed(0), "€/order", (t.marginCents / 100 / won).toFixed(1), "|", runs)
}
console.log(Object.keys(r), JSON.stringify(r).slice(0, 300))
