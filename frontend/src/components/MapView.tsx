import L from 'leaflet'
import { memo, useEffect, useMemo } from 'react'
import { CircleMarker, MapContainer, Marker, Pane, Polyline, TileLayer, Tooltip, ZoomControl, useMap } from 'react-leaflet'
import { fmtDuration, fmtTime, weatherText } from '../lib/format'
import { pointAtMile, progressTable, riskSegments, truckMileAt } from '../lib/geometry'
import { levelColor, levelLabel } from '../lib/risk'
import type { Checkpoint, HeatVariable, HeatmapResponse, Interval, LatLng, Place, RouteOption } from '../lib/types'
import { HeatmapLayer } from './HeatmapLayer'

interface Props {
  routes: RouteOption[]
  interval: Interval
  selectedId: string | null
  recommendedId: string | null
  onSelect: (id: string) => void
  origin: Place | null
  destination: Place | null
  focus: Checkpoint | null
  heatmap: HeatmapResponse | null
  heatVariable: HeatVariable
  heatHour: number
  heatVisible: boolean
  sliderTime: number | null
}

const US_CENTER: LatLng = [39.5, -98.35]

const endpointIcon = (label: string, cls: string) =>
  L.divIcon({ className: '', html: `<div class="pin ${cls}">${label}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] })
const ORIGIN_ICON = endpointIcon('A', 'pin-origin')
const DEST_ICON = endpointIcon('B', 'pin-dest')
const stopIcon = (kind: string) =>
  L.divIcon({
    className: '',
    html: `<div class="stop-pin">${kind === 'rest' ? '10h' : '30m'}</div>`,
    iconSize: [30, 16],
    iconAnchor: [15, 8],
  })
const truckIcon = (id: string, selected: boolean) =>
  L.divIcon({
    className: '',
    html: `<div class="truck-pin${selected ? ' sel' : ''}">🚚<span>${id}</span></div>`,
    iconSize: [34, 22],
    iconAnchor: [17, 11],
  })

function FitToRoutes({ routes, places }: { routes: RouteOption[]; places: LatLng[] }) {
  const map = useMap()
  const placeKey = places.map((p) => p.join()).join('|')
  useEffect(() => {
    const pts = routes.length ? routes.flatMap((r) => r.geometry) : places
    if (pts.length < 2) return
    const bounds = L.latLngBounds(pts)
    const wide = map.getSize().x > 860
    map.fitBounds(bounds, {
      paddingTopLeft: [wide ? 480 : 30, 40],
      paddingBottomRight: [wide ? 60 : 30, wide ? 230 : 40],
      animate: true,
      duration: 0.8,
    })
    // places are compared by value via placeKey
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, routes, placeKey])
  return null
}

function FlyToCheckpoint({ cp }: { cp: Checkpoint | null }) {
  const map = useMap()
  useEffect(() => {
    if (cp) map.flyTo([cp.lat, cp.lon], Math.max(map.getZoom(), 8), { duration: 0.6 })
  }, [map, cp])
  return null
}

function CheckpointTooltip({ cp }: { cp: Checkpoint }) {
  return (
    <div className="cp-tip">
      <div className="cp-tip-head">
        <span className="chip" style={{ background: levelColor(cp.level) }}>
          {levelLabel(cp.level)}
        </span>
        <span>
          Mile {Math.round(cp.mi)} · {fmtTime(cp.eta)}
        </span>
      </div>
      {cp.level == null ? (
        <div className="muted">Beyond the forecast horizon</div>
      ) : (
        <table>
          <tbody>
            <tr>
              <th>Wind</th>
              <td>
                {cp.wind} mph <span className="muted">(gust {cp.gust})</span>
              </td>
            </tr>
            <tr>
              <th>Rain</th>
              <td>{cp.rain?.toFixed(2)} in/hr</td>
            </tr>
            <tr>
              <th>Snow</th>
              <td>{cp.snow?.toFixed(2)} in/hr</td>
            </tr>
            <tr>
              <th>Temp</th>
              <td>
                {cp.temp}°F <span className="muted">{weatherText(cp.code)}</span>
              </td>
            </tr>
          </tbody>
        </table>
      )}
      {cp.factor && <div className="cp-tip-factor">Driven by {cp.factor}</div>}
    </div>
  )
}

const RouteLayer = memo(function RouteLayer({
  route,
  checkpoints,
  selected,
  recommended,
  onSelect,
}: {
  route: RouteOption
  checkpoints: Checkpoint[]
  selected: boolean
  recommended: boolean
  onSelect: (id: string) => void
}) {
  const segments = useMemo(() => (selected ? riskSegments(route, checkpoints) : []), [route, checkpoints, selected])
  const label = `${route.name}${recommended ? ' · Recommended' : ''} — click to select`

  if (!selected) {
    return (
      <Polyline
        positions={route.geometry}
        pathOptions={{ color: '#9fb3c8', weight: 4, opacity: 0.55, dashArray: recommended ? undefined : '2 9', lineCap: 'round' }}
        eventHandlers={{ click: () => onSelect(route.id) }}
      >
        <Tooltip sticky>{label}</Tooltip>
      </Polyline>
    )
  }
  return (
    <>
      {segments.map((s, k) => (
        <Polyline key={`g${k}`} positions={s.points} pathOptions={{ color: levelColor(s.level), weight: 16, opacity: 0.18 }} />
      ))}
      <Polyline positions={route.geometry} pathOptions={{ color: '#05080f', weight: 8, opacity: 0.9 }} />
      {segments.map((s, k) => (
        <Polyline key={k} positions={s.points} pathOptions={{ color: levelColor(s.level), weight: 4.5, opacity: 1 }} />
      ))}
      {checkpoints.map((cp) => (
        <CircleMarker
          key={cp.mi}
          center={[cp.lat, cp.lon]}
          radius={4.5}
          pathOptions={{ color: '#05080f', weight: 2, fillColor: levelColor(cp.level), fillOpacity: 1 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <CheckpointTooltip cp={cp} />
          </Tooltip>
        </CircleMarker>
      ))}
      {route.stops.map((s) => (
        <Marker key={s.start} position={[s.lat, s.lon]} icon={stopIcon(s.kind)}>
          <Tooltip direction="top">
            {s.kind === 'rest' ? '10-hour rest (HOS)' : '30-minute break (HOS)'} · {fmtTime(s.start)} for{' '}
            {fmtDuration(s.duration_s)}
          </Tooltip>
        </Marker>
      ))}
    </>
  )
})

function TruckMarkers({
  routes,
  interval,
  selectedId,
  time,
}: {
  routes: RouteOption[]
  interval: Interval
  selectedId: string | null
  time: number
}) {
  const tables = useMemo(
    () => routes.map((r) => progressTable(r, r.checkpoints[interval])),
    [routes, interval],
  )
  return (
    <>
      {routes.map((r, k) => {
        const mi = truckMileAt(tables[k], time)
        if (mi == null) return null
        const sel = r.id === selectedId
        return (
          <Marker
            key={r.id}
            position={pointAtMile(r, mi)}
            icon={truckIcon(r.id, sel)}
            zIndexOffset={sel ? 1000 : 500}
            interactive={false}
          />
        )
      })}
    </>
  )
}

export function MapView(props: Props) {
  const { routes, interval, selectedId, recommendedId, onSelect, heatmap, sliderTime } = props
  // Draw the selected route last so it sits on top.
  const ordered = useMemo(
    () => [...routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId)),
    [routes, selectedId],
  )
  return (
    <MapContainer center={US_CENTER} zoom={4} preferCanvas className="map" zoomControl={false} minZoom={3}>
      <TileLayer
        attribution='Basemap &copy; Esri · Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Weather <a href="https://open-meteo.com/">Open-Meteo</a> · Routing Valhalla / OSRM'
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        maxZoom={16}
      />
      {/* Place names sit above the heatmap so they stay readable through it */}
      <Pane name="labels" style={{ zIndex: 380, pointerEvents: 'none' }}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />
      </Pane>
      <ZoomControl position="bottomright" />
      {heatmap && (
        <HeatmapLayer data={heatmap} variable={props.heatVariable} hour={props.heatHour} visible={props.heatVisible} />
      )}
      <Pane name="routes" style={{ zIndex: 420 }}>
        {ordered.map((r) => (
          <RouteLayer
            key={r.id}
            route={r}
            checkpoints={r.checkpoints[interval]}
            selected={r.id === selectedId}
            recommended={r.id === recommendedId}
            onSelect={onSelect}
          />
        ))}
      </Pane>
      {props.origin && <Marker position={[props.origin.lat, props.origin.lon]} icon={ORIGIN_ICON} />}
      {props.destination && <Marker position={[props.destination.lat, props.destination.lon]} icon={DEST_ICON} />}
      {sliderTime != null && routes.length > 0 && (
        <TruckMarkers routes={routes} interval={interval} selectedId={selectedId} time={sliderTime} />
      )}
      <FitToRoutes
        routes={routes}
        places={[props.origin, props.destination].filter((p): p is Place => !!p).map((p) => [p.lat, p.lon] as LatLng)}
      />
      <FlyToCheckpoint cp={props.focus} />
    </MapContainer>
  )
}
