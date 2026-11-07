import { fmtDuration, fmtMiles, fmtTime } from '../lib/format'
import { LEVEL_COLORS, LEVELS, UNKNOWN_COLOR, levelColor, levelLabel } from '../lib/risk'
import type { Interval, Recommendation, RouteOption } from '../lib/types'

interface Props {
  routes: RouteOption[]
  interval: Interval
  recommendation: Recommendation
  selectedId: string | null
  onSelect: (id: string) => void
}

/** Share of the route at each risk level; 2px gaps separate segments. */
export function RiskBar({ route, interval, tall = false }: { route: RouteOption; interval: Interval; tall?: boolean }) {
  const s = route.summary[interval]
  const total = route.distance_mi || 1
  const parts = [
    ...LEVELS.map((l, k) => ({ label: l, mi: s.miles_by_level[l], color: LEVEL_COLORS[k] })),
    { label: 'No forecast', mi: s.unknown_miles, color: UNKNOWN_COLOR },
  ].filter((p) => p.mi > 0)
  return (
    <div
      className={`risk-bar${tall ? ' tall' : ''}`}
      role="img"
      aria-label={parts.map((p) => `${p.label} ${Math.round(p.mi)} miles`).join(', ')}
    >
      {parts.map((p) => (
        <span
          key={p.label}
          style={{ flexGrow: p.mi / total, background: p.color }}
          title={`${p.label}: ${fmtMiles(p.mi)}`}
        />
      ))}
    </div>
  )
}

function LevelPill({ level }: { level: number | null }) {
  return (
    <span className="level-pill">
      <span className="dot" style={{ background: levelColor(level) }} />
      {levelLabel(level)}
    </span>
  )
}

export function RecommendationHero({
  route,
  interval,
  recommendation,
  onSelect,
}: {
  route: RouteOption
  interval: Interval
  recommendation: Recommendation
  onSelect: (id: string) => void
}) {
  const m = route.summary[interval].miles_by_level
  const danger = m.Severe + m['No Travel']
  return (
    <button type="button" className="hero" onClick={() => onSelect(route.id)}>
      <div className="hero-top">
        <span className="hero-letter">{route.id}</span>
        <div className="hero-title">
          <span className="eyebrow">★ Safest pick</span>
          <b>{route.name}</b>
          {route.via.length > 0 && <span className="via">via {route.via.join(' · ')}</span>}
        </div>
      </div>
      <div className="hero-stats">
        <div>
          <span className="big">{fmtDuration(route.travel_s)}</span>
          <small>{fmtMiles(route.distance_mi)}</small>
        </div>
        <div>
          <span className="big">{fmtTime(route.arrival)}</span>
          <small>arrival</small>
        </div>
        <div>
          <span className={`big${danger > 0 ? ' danger' : ''}`}>{Math.round(danger)}</span>
          <small>severe+ mi</small>
        </div>
      </div>
      <RiskBar route={route} interval={interval} tall />
      <p className="hero-reason">{recommendation.reason}</p>
      {recommendation.warning && <p className="hero-warning">⚠ {recommendation.warning}</p>}
    </button>
  )
}

export function RouteCards({ routes, interval, recommendation, selectedId, onSelect }: Props) {
  const rank = (id: string) => recommendation.ranking.indexOf(id)
  const sorted = [...routes].sort((a, b) => rank(a.id) - rank(b.id))
  return (
    <div className="route-cards">
      {sorted.map((r, k) => {
        const s = r.summary[interval]
        const m = s.miles_by_level
        const recommended = r.id === recommendation.route_id
        return (
          <button
            key={r.id}
            type="button"
            className={`route-card${r.id === selectedId ? ' selected' : ''}`}
            style={{ animationDelay: `${k * 60}ms` }}
            onClick={() => onSelect(r.id)}
            aria-pressed={r.id === selectedId}
          >
            <span className="route-letter">{r.id}</span>
            <div className="route-main">
              <div className="route-card-head">
                <span className="route-name">{r.name}</span>
                {recommended ? <span className="badge">Best</span> : <span className="rank">#{rank(r.id) + 1}</span>}
                <LevelPill level={s.max_level} />
              </div>
              <div className="route-meta">
                <b>{fmtDuration(r.travel_s)}</b>
                <span>{fmtMiles(r.distance_mi)}</span>
                <span>
                  <b className={m.Severe + m['No Travel'] > 0 ? 'danger' : ''}>{Math.round(m.Severe + m['No Travel'])}</b>{' '}
                  severe+
                </span>
                <span>
                  <b>{Math.round(m.High)}</b> high
                </span>
                <span>
                  avg <b>{s.avg_risk == null ? '—' : s.avg_risk.toFixed(2)}</b>
                </span>
              </div>
              <RiskBar route={r} interval={interval} />
            </div>
          </button>
        )
      })}
    </div>
  )
}
