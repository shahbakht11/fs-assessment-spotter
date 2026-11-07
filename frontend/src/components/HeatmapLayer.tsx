import L from 'leaflet'
import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import { HeatmapRenderer } from '../lib/heatmapRenderer'
import type { HeatVariable, HeatmapResponse } from '../lib/types'

interface Props {
  data: HeatmapResponse
  variable: HeatVariable
  hour: number
  visible: boolean
}

/**
 * The heatmap canvas is handed to L.svgOverlay, which positions an arbitrary element over
 * lat/lng bounds and keeps it aligned through pans and zoom animations. The browser's
 * bilinear upscaling of the small canvas does the final smoothing.
 */
export function HeatmapLayer({ data, variable, hour, visible }: Props) {
  const map = useMap()
  const rendererRef = useRef<HeatmapRenderer | null>(null)
  const frame = useRef(0)

  useEffect(() => {
    if (!map.getPane('heat')) {
      const pane = map.createPane('heat')
      pane.style.zIndex = '350' // under routes (overlayPane = 400)
      pane.style.pointerEvents = 'none'
    }
    const canvas = document.createElement('canvas')
    canvas.className = 'heat-canvas'
    rendererRef.current = new HeatmapRenderer(data, canvas)
    const overlay = L.svgOverlay(canvas as unknown as SVGElement, L.latLngBounds(data.grid.bounds), {
      pane: 'heat',
      interactive: false,
    }).addTo(map)
    return () => {
      overlay.remove()
      rendererRef.current = null
    }
  }, [map, data])

  useEffect(() => {
    // Coalesce rapid slider events into one paint per animation frame.
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => rendererRef.current?.draw(variable, hour))
    return () => cancelAnimationFrame(frame.current)
  }, [data, variable, hour])

  useEffect(() => {
    const pane = map.getPane('heat')
    if (pane) pane.style.display = visible ? '' : 'none'
  }, [map, visible])

  return null
}
