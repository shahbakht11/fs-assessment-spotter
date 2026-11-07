// Shapes returned by the Django API (see backend/planner/services.py and heatmap.py).

export type LatLng = [number, number]
export type Interval = '10' | '25' | '50'
export type LevelLabel = 'Low' | 'Moderate' | 'High' | 'Severe' | 'No Travel'

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Checkpoint {
  mi: number
  cover_mi: number
  lat: number
  lon: number
  eta: string
  level: number | null // 0 Low … 4 No Travel; null = beyond forecast
  factor: 'wind' | 'rain' | 'snow' | null
  levels?: { wind: number; rain: number; snow: number }
  wind: number | null
  gust: number | null
  rain: number | null
  snow: number | null
  temp: number | null
  code: number | null
}

export interface Summary {
  miles_by_level: Record<LevelLabel, number>
  unknown_miles: number
  avg_risk: number | null
  max_level: number | null
}

export interface Stop {
  kind: 'break' | 'rest'
  mi: number
  lat: number
  lon: number
  start: string
  duration_s: number
}

export interface RouteOption {
  id: string
  name: string
  via: string[]
  geometry: LatLng[]
  vertex_mi: number[]
  distance_mi: number
  drive_s: number
  travel_s: number
  departure: string
  arrival: string
  stops: Stop[]
  checkpoints: Record<Interval, Checkpoint[]>
  summary: Record<Interval, Summary>
}

export interface Recommendation {
  route_id: string
  ranking: string[]
  reason: string
  warning: string | null
}

export interface PlanResponse {
  provider: string
  warnings: string[]
  load_lbs: number
  include_hos: boolean
  intervals: number[]
  forecast_cell_mi: number
  routes: RouteOption[]
  recommendation: Record<Interval, Recommendation>
}

export interface HeatCell {
  i: number
  j: number
  risk: (number | null)[]
  wind: (number | null)[]
  rain: (number | null)[]
  snow: (number | null)[]
}

export interface HeatmapResponse {
  grid: { nx: number; ny: number; bounds: [LatLng, LatLng] }
  spacing_mi: number
  start: string
  hours: string[]
  cells: HeatCell[]
}

export type HeatVariable = 'risk' | 'wind' | 'rain' | 'snow'

export interface PlanRequest {
  origin: Place
  destination: Place
  departure: string
  load_lbs: number
  include_hos: boolean
}
