import { useEffect, useRef, useState } from 'react'
import { fmtTime } from '../lib/format'
import { HEAT_LEGEND, LEGEND_GRADIENT, levelColor, levelLabel } from '../lib/risk'
import type { HeatVariable } from '../lib/types'

interface Props {
  startIso: string | null
  hour: number
  onHour: (h: number) => void
  playing: boolean
  onPlaying: (p: boolean) => void
  variable: HeatVariable
  onVariable: (v: HeatVariable) => void
  visible: boolean
  onVisible: (v: boolean) => void
  status: 'idle' | 'loading' | 'ready' | 'error'
  error?: string | null
  /** Worst risk score (0–4) anywhere in the corridor, per forecast hour. */
  worstByHour: (number | null)[] | null
}

const MAX_HOUR = 48
const PLAY_HOURS_PER_SECOND = 4

function Sparkline({
  values,
  hour,
  startIso,
  onHour,
}: {
  values: (number | null)[]
  hour: number
  startIso: string | null
  onHour: (h: number) => void
}) {
  const [hover, setHover] = useState<number | null>(null)
  const n = values.length - 1 || 1
  return (
    <div className="spark" onMouseLeave={() => setHover(null)}>
      {values.map((v, h) => {
        const level = v == null ? null : Math.min(4, Math.floor(v))
        const height = v == null ? 0 : 3 + (v / 4) * 25
        return (
          <button
            key={h}
            type="button"
            className="spark-hit"
            style={{ left: `${(h / n) * 100}%` }}
            onMouseEnter={() => setHover(h)}
            onFocus={() => setHover(h)}
            onClick={() => onHour(h)}
            aria-label={`+${h} h: worst ${levelLabel(level)}`}
          >
            <span className="spark-bar" style={{ height, background: levelColor(level), opacity: h <= hour ? 1 : 0.55 }} />
          </button>
        )
      })}
      <span className="spark-now" style={{ left: `${(hour / n) * 100}%` }} />
      {hover != null && (
        <div className="spark-tip" style={{ left: `${Math.min(Math.max((hover / n) * 100, 12), 88)}%` }}>
          <b>+{hover} h</b> {startIso && fmtTime(new Date(Date.parse(startIso) + hover * 3600_000))} · worst{' '}
          <span className="dot" style={{ background: levelColor(values[hover] == null ? null : Math.floor(values[hover]!)) }} />
          {levelLabel(values[hover] == null ? null : Math.min(4, Math.floor(values[hover]!)))}
        </div>
      )}
    </div>
  )
}

export function ForecastControls(p: Props) {
  const { hour, onHour, playing, onPlaying } = p
  const hourRef = useRef(hour)
  hourRef.current = hour

  // Playback runs on requestAnimationFrame with fractional hours, so frames blend smoothly.
  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const next = hourRef.current + ((now - last) / 1000) * PLAY_HOURS_PER_SECOND
      last = now
      if (next >= MAX_HOUR) {
        onHour(MAX_HOUR)
        onPlaying(false)
        return
      }
      onHour(next)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, onHour, onPlaying])

  const legend = HEAT_LEGEND[p.variable]
  const time = p.startIso ? new Date(Date.parse(p.startIso) + hour * 3600_000) : null
  const disabled = p.status !== 'ready'

  return (
    <div className="dock glass" aria-label="Forecast heatmap controls">
      <div className="dock-top">
        <button
          type="button"
          className="play"
          disabled={disabled}
          onClick={() => {
            if (!playing && hour >= MAX_HOUR) onHour(0)
            onPlaying(!playing)
          }}
          aria-label={playing ? 'Pause' : 'Play forecast'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <div className="dock-time">
          <span className="dock-hour">+{Math.floor(hour).toString().padStart(2, '0')}h</span>
          <span className="dock-clock">{time ? fmtTime(time) : '—'}</span>
        </div>
        <div className="segmented" role="radiogroup" aria-label="Heatmap layer">
          {(Object.keys(HEAT_LEGEND) as HeatVariable[]).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={p.variable === v}
              className={p.variable === v ? 'on' : ''}
              onClick={() => p.onVariable(v)}
            >
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
        <label className="toggle compact" title="Show heatmap">
          <input type="checkbox" checked={p.visible} onChange={(e) => p.onVisible(e.target.checked)} />
          <span className="toggle-track" aria-hidden>
            <span className="toggle-thumb" />
          </span>
          <span className="sr-only">Show heatmap</span>
        </label>
      </div>

      <div className="dock-scrub">
        {p.status === 'ready' && p.worstByHour && (
          <>
            <span className="spark-label">Worst risk in corridor</span>
            <Sparkline
              values={p.worstByHour}
              hour={hour}
              startIso={p.startIso}
              onHour={(h) => {
                onPlaying(false)
                onHour(h)
              }}
            />
          </>
        )}
        {p.status === 'loading' && (
          <div className="dock-status">
            <span className="spinner" /> Loading the 48-hour corridor forecast…
          </div>
        )}
        {p.status === 'error' && <div className="dock-status error">{p.error}</div>}
        <input
          type="range"
          className="slider"
          min={0}
          max={MAX_HOUR}
          step={0.25}
          value={hour}
          disabled={disabled}
          aria-label="Hours after departure"
          style={{ ['--pct' as string]: `${(hour / MAX_HOUR) * 100}%` }}
          onChange={(e) => {
            onPlaying(false)
            onHour(Number(e.target.value))
          }}
        />
        <div className="slider-ticks" aria-hidden>
          {[0, 12, 24, 36, 48].map((h) => (
            <span key={h}>{h}h</span>
          ))}
        </div>
      </div>

      <div className="legend">
        <span className="legend-title">{legend.title}</span>
        <div>
          <div className="legend-bar" style={{ background: LEGEND_GRADIENT }} />
          <div className="legend-ticks">
            {legend.ticks.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
