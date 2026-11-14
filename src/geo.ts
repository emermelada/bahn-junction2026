/** The map and the roster, turned into the numbers the modules use: road minutes, straight-line km,
 * drivers within the 30 km notification radius and within 80 km, and the 30 km "pools" that share drivers. */
import type { DriverProfile, WorldMap } from "./client/types.ts"

export const NOTIFY_KM = 30 // RULES, Drivers: a driver hears of a new gig when its first pickup is within 30 km of their home
export const REGION_KM = 80 // RULES, Practice and the final: an outage region is a town and the places within 80 km

export type Reach = { all: number; experienced: number; manual: number }

export class Geo {
  readonly places: string[]
  readonly #road = new Map<string, { minutes: number; km: number }>()
  readonly #dist = new Map<string, number>()
  readonly #reach30 = new Map<string, Reach>()
  readonly #reach80 = new Map<string, Reach>()
  readonly #pool = new Map<string, string[]>()
  readonly #poolId = new Map<string, string>()
  readonly #supply = new Map<string, number>()
  readonly homes = new Map<string, number>() // place -> roster drivers living there
  readonly driverHome = new Map<string, string>()
  readonly drivers = new Map<string, DriverProfile>()

  constructor(map: WorldMap, roster: DriverProfile[]) {
    this.places = map.places.map((p) => p.id)
    for (const r of map.roads) this.#road.set(`${r.from}>${r.to}`, { minutes: r.minutes, km: r.km })
    const byId = new Map(map.places.map((p) => [p.id, p]))
    for (const a of map.places) for (const b of map.places) this.#dist.set(`${a.id}>${b.id}`, haversineKm(a.lat, a.lon, b.lat, b.lon))
    for (const d of roster) {
      this.drivers.set(d.id, d)
      this.driverHome.set(d.id, d.homePlaceId)
      this.homes.set(d.homePlaceId, (this.homes.get(d.homePlaceId) ?? 0) + 1)
    }
    const experienced = (d: DriverProfile) => d.rating >= 4.8 && d.completedGigs >= 50
    for (const p of map.places) {
      const within = (km: number) => map.places.filter((q) => this.dist(p.id, q.id) <= km).map((q) => q.id)
      const count = (ids: string[]): Reach => {
        const set = new Set(ids)
        let all = 0, exp = 0, man = 0
        for (const d of roster) if (set.has(d.homePlaceId)) { all++; if (experienced(d)) exp++; if (d.licence === "manual") man++ }
        return { all, experienced: exp, manual: man }
      }
      const near = within(NOTIFY_KM)
      this.#reach30.set(p.id, count(near))
      this.#reach80.set(p.id, count(within(REGION_KM)))
      this.#pool.set(p.id, near)
      this.#poolId.set(p.id, [...near].sort().join("+"))
      if (!byId.has(p.id)) throw new Error(`map place ${p.id} missing`)
    }
  }

  /** Road minutes between two places (a place to itself has its own road, 25 min on this map). */
  road(from: string, to: string): number {
    return this.#road.get(`${from}>${to}`)?.minutes ?? 10_000
  }

  km(from: string, to: string): number {
    return this.#road.get(`${from}>${to}`)?.km ?? 10_000
  }

  /** Straight-line km, the measure of the notification radius and the outage region. */
  dist(a: string, b: string): number {
    return this.#dist.get(`${a}>${b}`) ?? 10_000
  }

  reach30(place: string): Reach {
    return this.#reach30.get(place) ?? { all: 0, experienced: 0, manual: 0 }
  }

  reach80(place: string): Reach {
    return this.#reach80.get(place) ?? { all: 0, experienced: 0, manual: 0 }
  }

  /** The places within 30 km of a place (itself included): the drivers these places notify are one pool. */
  pool(place: string): string[] {
    return this.#pool.get(place) ?? [place]
  }

  poolId(place: string): string {
    return this.#poolId.get(place) ?? place
  }

  /** Driver supply index of a place: roster drivers weighted by exp(-road minutes from their home / 60) (own town = 1). */
  supply(place: string): number {
    let s = this.#supply.get(place)
    if (s === undefined) {
      s = 0
      for (const [home, n] of this.homes) s += n * Math.exp(-(home === place ? 0 : this.road(home, place)) / 60)
      this.#supply.set(place, s)
    }
    return s
  }

  /** Places within `km` straight-line of a place. */
  within(place: string, km: number): string[] {
    return this.places.filter((q) => this.dist(place, q) <= km)
  }
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const rad = (x: number) => (x * Math.PI) / 180
  const dLat = rad(lat2 - lat1)
  const dLon = rad(lon2 - lon1)
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(s))
}
