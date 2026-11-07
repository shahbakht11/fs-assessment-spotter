import type { HeatmapResponse, LatLng, Place, PlanRequest, PlanResponse } from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init)
  const text = await resp.text()
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(`Server returned an unexpected response (HTTP ${resp.status}).`)
  }
  if (!resp.ok) {
    const msg = (data as { error?: string }).error
    throw new Error(msg ?? `Request failed (HTTP ${resp.status}).`)
  }
  return data as T
}

const postJson = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  signal,
})

export function searchPlaces(q: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }).then(
    (r) => r.results,
  )
}

export function planTrip(body: PlanRequest, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>('/api/plan', postJson(body, signal))
}

/** Keeps the heatmap request small: the corridor only needs a coarse outline of each route. */
function decimate(points: LatLng[], max = 400): LatLng[] {
  if (points.length <= max) return points
  const step = (points.length - 1) / (max - 1)
  return Array.from({ length: max }, (_, k) => points[Math.round(k * step)])
}

export function fetchHeatmap(
  routes: LatLng[][],
  departure: string,
  loadLbs: number,
  signal?: AbortSignal,
): Promise<HeatmapResponse> {
  return request<HeatmapResponse>(
    '/api/heatmap',
    postJson({ routes: routes.map((r) => decimate(r)), departure, load_lbs: loadLbs }, signal),
  )
}
