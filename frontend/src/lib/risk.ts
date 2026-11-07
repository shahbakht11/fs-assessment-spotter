import type { HeatVariable, LevelLabel } from './types'

export const LEVELS: LevelLabel[] = ['Low', 'Moderate', 'High', 'Severe', 'No Travel']
// Ordinal severity scale, validated against the dark surface (#0d1524) for CVD and
// normal-vision separation of adjacent levels. Always shown with a text label.
export const LEVEL_COLORS = ['#34b864', '#f2cf3d', '#f57c1f', '#d61f69', '#8b7dff']
export const UNKNOWN_COLOR = '#6b7a90'

export const levelLabel = (level: number | null) => (level == null ? 'No forecast' : LEVELS[level])
export const levelColor = (level: number | null) => (level == null ? UNKNOWN_COLOR : LEVEL_COLORS[level])

// --- Heatmap colour scale -------------------------------------------------------------------
// Every variable is mapped onto the same 0–4 "risk-equivalent" scale using the brief's
// thresholds, so a given colour means the same risk band whichever variable is shown.
// (Only the Risk view applies the load-weight rules — the raw variables can't know the load.)

const BANDS: Record<Exclude<HeatVariable, 'risk'>, number[]> = {
  wind: [0, 25, 35, 45, 55], // mph
  rain: [0, 0.1, 0.25, 0.5, 1.0], // in/hr
  snow: [0, 0.5, 1.0, 2.0, 3.0], // in/hr
}

export function toScale(variable: HeatVariable, v: number): number {
  if (variable === 'risk') return v
  const b = BANDS[variable]
  if (v >= b[4]) return 4
  for (let k = 3; k >= 0; k--) {
    if (v >= b[k]) return k + (v - b[k]) / (b[k + 1] - b[k])
  }
  return 0
}

export const HEAT_LEGEND: Record<HeatVariable, { title: string; ticks: string[] }> = {
  risk: { title: 'Risk (incl. load rules)', ticks: LEVELS },
  wind: { title: 'Wind, mph', ticks: ['0', '25', '35', '45', '55+'] },
  rain: { title: 'Rain, in/hr', ticks: ['0', '0.10', '0.25', '0.50', '1.00+'] },
  snow: { title: 'Snow, in/hr', ticks: ['0', '0.5', '1.0', '2.0', '3.0+'] },
}

// Colour stops on the 0–4 scale: [r, g, b, alpha]. Low is nearly transparent so the
// base map stays readable; danger ramps to opaque.
const STOPS: [number, number, number, number, number][] = [
  [0, 52, 184, 100, 0.06],
  [0.6, 52, 184, 100, 0.22],
  [1, 242, 207, 61, 0.45],
  [2, 245, 124, 31, 0.6],
  [3, 214, 31, 105, 0.72],
  [4, 139, 125, 255, 0.82],
]

/** 256-entry RGBA lookup table over the 0–4 scale. */
export const COLOR_LUT: Uint8ClampedArray = (() => {
  const lut = new Uint8ClampedArray(256 * 4)
  for (let i = 0; i < 256; i++) {
    const s = (i / 255) * 4
    let k = 0
    while (k < STOPS.length - 2 && s > STOPS[k + 1][0]) k++
    const [s0, r0, g0, b0, a0] = STOPS[k]
    const [s1, r1, g1, b1, a1] = STOPS[k + 1]
    const t = Math.min(1, Math.max(0, (s - s0) / (s1 - s0)))
    lut.set([r0 + t * (r1 - r0), g0 + t * (g1 - g0), b0 + t * (b1 - b0), 255 * (a0 + t * (a1 - a0))], i * 4)
  }
  return lut
})()

export const LEGEND_GRADIENT = `linear-gradient(to right, ${STOPS.map(
  ([s, r, g, b]) => `rgb(${r},${g},${b}) ${(s / 4) * 100}%`,
).join(', ')})`
