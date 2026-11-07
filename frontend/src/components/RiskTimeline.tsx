import { useMemo, useRef, useState } from 'react'
import { fmtTime } from '../lib/format'
import { levelColor, levelLabel } from '../lib/risk'
import type { Checkpoint, RouteOption } from '../lib/types'

interface Props {
  route: RouteOption
  checkpoints: Checkpoint[]
  onFocus: (cp: Checkpoint) => void
}

interface Run {
  level: number | null
  from: number
  to: number
}

/** Merge checkpoints into runs of equal level; each owns half-way to its neighbours. */
function toRuns(cps: Checkpoint[], total: number): Run[] {
  const runs: Run[] = []
  cps.forEach((cp, k) => {
    const from = k === 0 ? 0 : (cps[k - 1].mi + cp.mi) / 2
    const to = k === cps.length - 1 ? total : (cp.mi + cps[k + 1].mi) / 2
    const last = runs[runs.length - 1]
    if (last && last.level === cp.level) last.to = to
    else runs.push({ level: cp.level, from, to })
  })
  return runs
}

/**
 * The trip as one strip: distance on x, risk as colour, rest stops as markers.
 * Hover for the checkpoint under the cursor; click to fly the map there.
 */
export function RiskTimeline({ route, checkpoints, onFocus }: Props) {
  const total = route.distance_mi || 1
  const runs = useMemo(() => toRuns(checkpoints, total), [checkpoints, total])
  const ref = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ x: number; cp: Checkpoint } | null>(null)

  const pick = (clientX: number) => {
    const box = ref.current!.getBoundingClientRect()
    const x = Math.min(Math.max(clientX - box.left, 0), box.width)
    const mi = (x / box.width) * total
    let best = checkpoints[0]
    for (const cp of checkpoints) if (Math.abs(cp.mi - mi) < Math.abs(best.mi - mi)) best = cp
    return { x, cp: best }
  }

  const tipLeft = hover ? Math.min(Math.max(hover.x, 90), (ref.current?.clientWidth ?? 0) - 90) : 0

  return (
    <div className="timeline">
      <div
        className="tl-track"
        ref={ref}
        onMouseMove={(e) => setHover(pick(e.clientX))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => onFocus(pick(e.clientX).cp)}
        role="img"
        aria-label={`Risk along ${route.name}: ${runs
          .map((r) => `${levelLabel(r.level)} from mile ${Math.round(r.from)} to ${Math.round(r.to)}`)
          .join('; ')}`}
      >
        {runs.map((r, k) => (
          <span
            key={k}
            className="tl-run"
            style={{
              left: `${(r.from / total) * 100}%`,
              width: `calc(${((r.to - r.from) / total) * 100}% - ${k < runs.length - 1 ? 2 : 0}px)`,
              background: levelColor(r.level),
            }}
          />
        ))}
        {route.stops.map((s) => (
          <span
            key={s.start}
            className={`tl-stop ${s.kind}`}
            style={{ left: `${(s.mi / total) * 100}%` }}
            title={`${s.kind === 'rest' ? '10 h rest' : '30 min break'} · ${fmtTime(s.start)}`}
          >
            {s.kind === 'rest' ? '10h' : '30m'}
          </span>
        ))}
        {hover && <span className="tl-cursor" style={{ left: hover.x }} />}
        {hover && (
          <div className="tl-tip" style={{ left: tipLeft }}>
            <div className="tl-tip-head">
              <span className="dot" style={{ background: levelColor(hover.cp.level) }} />
              <b>{levelLabel(hover.cp.level)}</b>
              <span className="muted">
                mi {Math.round(hover.cp.mi)} · {fmtTime(hover.cp.eta)}
              </span>
            </div>
            {hover.cp.level != null && (
              <div className="tl-tip-vals">
                <span>
                  Wind <b>{hover.cp.wind}</b> mph
                </span>
                <span>
                  Rain <b>{hover.cp.rain?.toFixed(2)}</b>
                </span>
                <span>
                  Snow <b>{hover.cp.snow?.toFixed(1)}</b>
                </span>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="tl-axis">
        <span>
          <b>Depart</b> {fmtTime(route.departure)}
        </span>
        <span>{Math.round(total / 2).toLocaleString()} mi</span>
        <span>
          <b>Arrive</b> {fmtTime(route.arrival)}
        </span>
      </div>
    </div>
  )
}
