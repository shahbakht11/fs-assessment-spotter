import { describe, expect, it } from 'vitest'
import { pointAtMile, progressTable, riskSegments, truckMileAt } from './geometry'
import { toScale } from './risk'
import type { Checkpoint, RouteOption } from './types'

const cp = (mi: number, level: number | null, eta: string): Checkpoint => ({
  mi, cover_mi: 0, lat: 0, lon: mi, eta, level, factor: null,
  wind: 0, gust: 0, rain: 0, snow: 0, temp: 0, code: 0,
})

const route = (stops: RouteOption['stops'] = []): RouteOption => ({
  id: 'A', name: 'Route A', via: [],
  geometry: [[0, 0], [0, 10], [0, 20], [0, 30]],
  vertex_mi: [0, 10, 20, 30],
  distance_mi: 30, drive_s: 0, travel_s: 0, departure: '', arrival: '',
  stops, checkpoints: { '10': [], '25': [], '50': [] }, summary: {} as RouteOption['summary'],
})

describe('geometry', () => {
  it('interpolates a point by milepost', () => {
    expect(pointAtMile(route(), 15)).toEqual([0, 15])
    expect(pointAtMile(route(), 99)).toEqual([0, 30])
  })

  it('merges equal-risk checkpoints and splits halfway between differing ones', () => {
    const cps = [cp(0, 0, ''), cp(10, 0, ''), cp(20, 2, ''), cp(30, 2, '')]
    const segs = riskSegments(route(), cps)
    expect(segs.map((s) => s.level)).toEqual([0, 2])
    expect(segs[0].points[segs[0].points.length - 1]).toEqual([0, 15])
    expect(segs[1].points[0]).toEqual([0, 15])
  })

  it('holds the truck in place during a rest stop', () => {
    const r = route([{ kind: 'rest', mi: 10, lat: 0, lon: 10, start: '2026-01-01T01:00:00Z', duration_s: 36000 }])
    const cps = [cp(0, 0, '2026-01-01T00:00:00Z'), cp(20, 0, '2026-01-01T12:00:00Z')]
    const table = progressTable(r, cps)
    expect(truckMileAt(table, Date.parse('2025-12-31T23:00:00Z'))).toBeNull()
    expect(truckMileAt(table, Date.parse('2026-01-01T00:30:00Z'))).toBeCloseTo(5)
    expect(truckMileAt(table, Date.parse('2026-01-01T06:00:00Z'))).toBe(10)
    expect(truckMileAt(table, Date.parse('2026-01-01T11:30:00Z'))).toBeCloseTo(15)
  })
})

describe('heatmap scale', () => {
  it('maps raw variables onto the risk bands', () => {
    expect(toScale('wind', 25)).toBe(1)
    expect(toScale('wind', 40)).toBeCloseTo(2.5)
    expect(toScale('rain', 0.25)).toBe(2)
    expect(toScale('snow', 5)).toBe(4)
    expect(toScale('risk', 3.2)).toBe(3.2)
  })
})
