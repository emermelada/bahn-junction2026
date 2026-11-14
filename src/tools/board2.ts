import { Client } from "../client/spread.ts"
process.loadEnvFile(new URL("../../.env", import.meta.url))
const c = new Client()
const b: any = await c.board(8)
const me: any = await c.call("GET", "/v1/team").catch(() => null)
console.log("team:", me ? { name: me.name ?? me.team, id: me.id } : "n/a")
for (const key of ["current", "previous"]) {
  const r = b[key]; if (!r) continue
  console.log(key, "round", r.season, r.startsAt ?? "", r.endsAt ?? "", "teams", r.teams?.length)
  const mine = r.teams?.filter((t: any) => /elysa/i.test(String(t.name ?? t.team)))
  console.log(" ours:", JSON.stringify(mine))
}
const worlds = await c.worlds()
console.log("our board runs:", worlds.filter((w: any) => w.boardRun).map((w: any) => `${w.worldId} L${w.level} s${w.season} #${w.boardRun} ${w.ended ? "ended" : "OPEN"}`).join(" | "))
