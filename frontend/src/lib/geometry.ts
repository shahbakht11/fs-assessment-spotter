import type { Checkpoint, LatLng, RouteOption } from './types'

/** Position on the route polyline at `mi` miles from the origin. */
export function pointAtMile(route: RouteOption, mi: number): LatLng {
  const { geometry: g, vertex_mi: m } = route
  if (mi <= 0) return g[0]
  if (mi >= m[m.length - 1]) return g[g.length - 1]
  let lo = 0
  let hi = m.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (m[mid] <= mi) lo = mid
    else hi = mid
  }
  const t = m[hi] === m[lo] ? 0 : (mi - m[lo]) / (m[hi] - m[lo])
  return [g[lo][0] + t * (g[hi][0] - g[lo][0]), g[lo][1] + t * (g[hi][1] - g[lo][1])]
}

/** Polyline between two mileposts (inclusive of interpolated endpoints). */
export function sliceByMiles(route: RouteOption, fromMi: number, toMi: number): LatLng[] {
  const out: LatLng[] = [pointAtMile(route, fromMi)]
  route.vertex_mi.forEach((m, i) => {
    if (m > fromMi && m < toMi) out.push(route.geometry[i])
  })
  out.push(pointAtMile(route, toMi))
  return out
}

export interface RiskSegment {
  level: number | null
  points: LatLng[]
}

/** Splits the route into runs of equal risk; each checkpoint owns half-way to its neighbours. */
export function riskSegments(route: RouteOption, cps: Checkpoint[]): RiskSegment[] {
  const segs: RiskSegment[] = []
  let runStart = 0
  for (let k = 0; k < cps.length; k++) {
    const isLast = k === cps.length - 1
    const boundary = isLast ? route.distance_mi : (cps[k].mi + cps[k + 1].mi) / 2
    if (isLast || cps[k + 1].level !== cps[k].level) {
      segs.push({ level: cps[k].level, points: sliceByMiles(route, runStart, boundary) })
      runStart = boundary
    }
  }
  return segs
}

/** (time ms, mile) pairs from checkpoint ETAs plus rest stops, where the truck holds still. */
export function progressTable(route: RouteOption, cps: Checkpoint[]): [number, number][] {
  const pts: [number, number][] = cps.map((c) => [Date.parse(c.eta), c.mi])
  for (const s of route.stops) {
    const start = Date.parse(s.start)
    pts.push([start, s.mi], [start + s.duration_s * 1000, s.mi])
  }
  return pts.sort((a, b) => a[0] - b[0] || a[1] - b[1])
}

/** Mile the truck has reached at wall-clock `time` (null before departure). */
export function truckMileAt(table: [number, number][], time: number): number | null {
  if (!table.length || time < table[0][0]) return null
  for (let k = 1; k < table.length; k++) {
    const [tk, mk] = table[k]
    if (time <= tk) {
      const [tp, mp] = table[k - 1]
      const f = tk === tp ? 1 : (time - tp) / (tk - tp)
      return mp + f * (mk - mp)
    }
  }
  return table[table.length - 1][1]
}
