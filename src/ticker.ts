/** Moves a practice world at the final's pace, for the kill-and-restart rehearsal of run-final.ts.
 *   node src/ticker.ts --seed <s> [--level 8] [--speed 1]   (creates the world, prints its id, deletes it on Ctrl-C if not ended)
 *   node src/ticker.ts --world <id>
 * Pace (API.md): 18 s per hour 06-22 on weekdays, 6 s Saturday, 9 s the last Monday, 3 s otherwise. */
import { parseArgs } from "node:util"
import { Client } from "./client/spread.ts"
import { DAY } from "./desk-api.ts"

try {
  process.loadEnvFile(new URL("../.env", import.meta.url))
} catch {}
const { values: args } = parseArgs({ options: { seed: { type: "string" }, world: { type: "string" }, level: { type: "string", default: "8" }, speed: { type: "string", default: "1" } } })
const client = new Client()
const world = args.world ? client.world(args.world) : await client.create(Number(args.level) as 8, { seed: args.seed })
console.log(`ticker world ${world.id}`)
if (!args.world) process.once("SIGINT", async () => (await world.delete().catch(() => {}), process.exit(130)))
const speed = Number(args.speed)
/** Real seconds per world hour at minute t. */
function secPerHour(t: number): number {
  const day = Math.floor(t / DAY)
  const mod = (t % DAY) / 60
  const day06to22 = mod >= 6 && mod < 22
  if (!day06to22) return 3
  if (day < 5) return 18
  if (day === 5) return 6
  if (day === 7) return 9
  return 3
}
let { now, endsAt } = await world.snapshot()
let debt = 0
let last = Date.now()
while (now < endsAt) {
  await new Promise((done) => setTimeout(done, 250))
  const elapsed = (Date.now() - last) / 1000
  last = Date.now()
  debt += (elapsed * speed * 60) / secPerHour(now)
  const by = Math.floor(debt)
  if (by < 1) continue
  debt -= by
  try {
    now = (await world.advance({ by: Math.min(by, endsAt - now) })).now
  } catch (error) {
    console.error(`ticker: ${(error as Error).message}; retrying`)
    await new Promise((done) => setTimeout(done, 1000))
  }
}
console.log(`ticker: world ${world.id} ended`)
