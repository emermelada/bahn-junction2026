/** Lists our open worlds and whether their clock moves (2 reads 6 s apart); --delete removes the frozen ones. */
import { readFileSync } from "node:fs"
import { Client } from "../client/spread.ts"
process.loadEnvFile(new URL("../../.env", import.meta.url))
const c = new Client()
const ours = new Set(readFileSync(new URL("../../runs/worlds.jsonl", import.meta.url), "utf8").trim().split("\n").map((l) => JSON.parse(l).worldId))
const open = (await c.worlds()).filter((w) => !w.ended && ours.has(w.worldId))
const a = await Promise.all(open.map((w) => c.world(w.worldId).snapshot().then((s) => s.now)))
await new Promise((d) => setTimeout(d, 6000))
const b = await Promise.all(open.map((w) => c.world(w.worldId).snapshot().then((s) => s.now)))
for (const [i, w] of open.entries()) {
  const frozen = a[i] === b[i]
  console.log(w.worldId, a[i], b[i], frozen ? "FROZEN" : "moving")
  if (frozen && process.argv.includes("--delete")) (await c.world(w.worldId).delete(), console.log("  deleted"))
}
