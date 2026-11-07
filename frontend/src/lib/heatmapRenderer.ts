import { COLOR_LUT, toScale } from './risk'
import type { HeatVariable, HeatmapResponse } from './types'

const VARIABLES: HeatVariable[] = ['risk', 'wind', 'rain', 'snow']

/**
 * Paints the corridor heatmap into a small canvas that Leaflet stretches over the grid bounds.
 *
 * - The grid is uniform in Web Mercator, so one canvas pixel block per cell lines up exactly.
 * - Each pixel is a bilinear blend of its 4 surrounding cells (weights precomputed once), and
 *   the corridor mask is blended the same way, so edges fade out instead of stair-stepping.
 * - Fractional hours blend linearly between forecast hours, so the slider animates smoothly.
 * A frame is ~25k pixels of arithmetic plus one putImageData: well under a millisecond or two.
 */
export class HeatmapRenderer {
  readonly canvas: HTMLCanvasElement
  readonly hours: number
  private readonly ctx: CanvasRenderingContext2D
  private readonly image: ImageData
  private readonly nCells: number
  private readonly values: Record<HeatVariable, Float32Array> // [hour * nCells + cell], NaN = missing
  private readonly cornerCell: Int32Array // per pixel ×4: cell index or -1
  private readonly cornerWeight: Float32Array // per pixel ×4
  private readonly cellScale: Float32Array

  constructor(data: HeatmapResponse, canvas: HTMLCanvasElement) {
    const { nx, ny } = data.grid
    this.hours = data.hours.length
    this.nCells = data.cells.length
    const scale = Math.max(2, Math.min(10, Math.round(360 / Math.max(nx, ny))))
    const w = nx * scale
    const h = ny * scale
    canvas.width = w
    canvas.height = h
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')!
    this.image = this.ctx.createImageData(w, h)
    this.cellScale = new Float32Array(this.nCells)

    const cellAt = new Int32Array(nx * ny).fill(-1)
    data.cells.forEach((c, k) => (cellAt[c.j * nx + c.i] = k))

    this.values = {} as Record<HeatVariable, Float32Array>
    for (const v of VARIABLES) {
      const arr = new Float32Array(this.hours * this.nCells)
      data.cells.forEach((c, k) => {
        const series = c[v]
        for (let t = 0; t < this.hours; t++) arr[t * this.nCells + k] = series[t] ?? NaN
      })
      this.values[v] = arr
    }

    this.cornerCell = new Int32Array(w * h * 4)
    this.cornerWeight = new Float32Array(w * h * 4)
    for (let py = 0; py < h; py++) {
      const gy = Math.min(ny - 1, Math.max(0, (py + 0.5) / scale - 0.5))
      const j0 = Math.min(ny - 2, Math.floor(gy))
      const fy = gy - j0
      for (let px = 0; px < w; px++) {
        const gx = Math.min(nx - 1, Math.max(0, (px + 0.5) / scale - 0.5))
        const i0 = Math.min(nx - 2, Math.floor(gx))
        const fx = gx - i0
        const o = (py * w + px) * 4
        const corners = [
          [i0, j0, (1 - fx) * (1 - fy)],
          [i0 + 1, j0, fx * (1 - fy)],
          [i0, j0 + 1, (1 - fx) * fy],
          [i0 + 1, j0 + 1, fx * fy],
        ]
        corners.forEach(([i, j, wt], k) => {
          this.cornerCell[o + k] = cellAt[j * nx + i]
          this.cornerWeight[o + k] = wt
        })
      }
    }
  }

  /** Draw `variable` at fractional hour `t` (0 … hours-1). */
  draw(variable: HeatVariable, t: number): void {
    const n = this.nCells
    const vals = this.values[variable]
    const t0 = Math.max(0, Math.min(this.hours - 1, Math.floor(t)))
    const t1 = Math.min(this.hours - 1, t0 + 1)
    const f = Math.max(0, Math.min(1, t - t0))
    for (let k = 0; k < n; k++) {
      const a = vals[t0 * n + k]
      const b = vals[t1 * n + k]
      const v = Number.isNaN(b) ? a : Number.isNaN(a) ? b : a + (b - a) * f
      this.cellScale[k] = Number.isNaN(v) ? NaN : toScale(variable, v)
    }

    const px = this.image.data
    const cells = this.cornerCell
    const weights = this.cornerWeight
    const total = px.length / 4
    for (let p = 0; p < total; p++) {
      const o = p * 4
      let sumW = 0
      let sumV = 0
      for (let k = 0; k < 4; k++) {
        const c = cells[o + k]
        if (c < 0) continue
        const v = this.cellScale[c]
        if (Number.isNaN(v)) continue
        sumW += weights[o + k]
        sumV += weights[o + k] * v
      }
      if (sumW < 0.02) {
        px[o + 3] = 0
        continue
      }
      const lut = Math.round((sumV / sumW / 4) * 255) * 4
      px[o] = COLOR_LUT[lut]
      px[o + 1] = COLOR_LUT[lut + 1]
      px[o + 2] = COLOR_LUT[lut + 2]
      px[o + 3] = COLOR_LUT[lut + 3] * Math.min(1, sumW * 1.4) // soft corridor edge
    }
    this.ctx.putImageData(this.image, 0, 0)
  }
}
