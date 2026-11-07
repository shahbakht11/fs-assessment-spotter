import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CheckpointTable } from './components/CheckpointTable'
import { ForecastControls } from './components/ForecastControls'
import { MapView } from './components/MapView'
import { PlanForm, type FormValues } from './components/PlanForm'
import { RiskTimeline } from './components/RiskTimeline'
import { RecommendationHero, RouteCards } from './components/RouteCards'
import { fetchHeatmap, planTrip } from './lib/api'
import { LEVELS, LEVEL_COLORS } from './lib/risk'
import type { Checkpoint, HeatVariable, HeatmapResponse, Interval, Place, PlanRequest, PlanResponse } from './lib/types'

type HeatStatus = 'idle' | 'loading' | 'ready' | 'error'

const SAMPLE_TRIPS: { label: string; values: FormValues }[] = [
  {
    label: 'Chicago → Denver',
    values: {
      origin: { label: 'Chicago, Illinois, US', lat: 41.8781, lon: -87.6298 },
      destination: { label: 'Denver, Colorado, US', lat: 39.7392, lon: -104.9903 },
      loadLbs: 42_000,
    },
  },
  {
    label: 'New York → Boston',
    values: {
      origin: { label: 'New York, US', lat: 40.7128, lon: -74.006 },
      destination: { label: 'Boston, Massachusetts, US', lat: 42.3601, lon: -71.0589 },
      loadLbs: 45_000,
    },
  },
  {
    label: 'Seattle → Portland',
    values: {
      origin: { label: 'Seattle, Washington, US', lat: 47.6062, lon: -122.3321 },
      destination: { label: 'Portland, Oregon, US', lat: 45.5152, lon: -122.6784 },
      loadLbs: 32_000,
    },
  },
]

const LOADING_STEPS = ['Finding truck routes', 'Placing checkpoints at ETAs', 'Pulling hourly forecasts', 'Scoring risk & ranking']

const floorHour = (iso: string) => {
  const d = new Date(iso)
  d.setUTCMinutes(0, 0, 0)
  return d.toISOString()
}

function nextHourIso() {
  const d = new Date(Date.now() + 3600_000)
  d.setMinutes(0, 0, 0)
  return d.toISOString()
}

/** Advances the progress label while the single plan request is in flight. */
function useLoadingStep(loading: boolean) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    if (!loading) return
    setStep(0)
    const id = window.setInterval(() => setStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1)), 1300)
    return () => window.clearInterval(id)
  }, [loading])
  return step
}

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [interval, setIntervalMi] = useState<Interval>('25')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focus, setFocus] = useState<Checkpoint | null>(null)
  const [places, setPlaces] = useState<[Place | null, Place | null]>([
    SAMPLE_TRIPS[0].values.origin,
    SAMPLE_TRIPS[0].values.destination,
  ])
  const [form, setForm] = useState<{ key: number; values: FormValues }>({ key: 0, values: SAMPLE_TRIPS[0].values })

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)
  const [heatStatus, setHeatStatus] = useState<HeatStatus>('idle')
  const [heatError, setHeatError] = useState<string | null>(null)
  const [heatVariable, setHeatVariable] = useState<HeatVariable>('risk')
  const [heatVisible, setHeatVisible] = useState(true)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const inflight = useRef<AbortController | null>(null)
  const intervalRef = useRef(interval)
  intervalRef.current = interval
  const step = useLoadingStep(loading)

  const submit = useCallback(async (req: PlanRequest) => {
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    setLoading(true)
    setPlanError(null)
    setHeatmap(null)
    setHeatStatus('idle')
    setPlaying(false)
    setHour(0)
    setFocus(null)
    setPlaces([req.origin, req.destination])
    try {
      const result = await planTrip(req, ctrl.signal)
      setPlan(result)
      setSelectedId(result.recommendation[intervalRef.current]?.route_id ?? result.routes[0]?.id ?? null)
      // On phones the map sits above the form: bring it into view to show the routes.
      if (window.matchMedia('(max-width: 860px)').matches) window.scrollTo({ top: 0, behavior: 'smooth' })
      // Routes are on screen; fetch the corridor heatmap in the background.
      setHeatStatus('loading')
      fetchHeatmap(result.routes.map((r) => r.geometry), req.departure, req.load_lbs, ctrl.signal)
        .then((h) => {
          setHeatmap(h)
          setHeatStatus('ready')
        })
        .catch((e: Error) => {
          if (e.name === 'AbortError') return
          setHeatError(e.message)
          setHeatStatus('error')
        })
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        // Don't leave the previous trip's results under the new trip's inputs.
        setPlan(null)
        setSelectedId(null)
        setPlanError((e as Error).message)
      }
    } finally {
      if (inflight.current === ctrl) setLoading(false)
    }
  }, [])

  const runSample = (values: FormValues) => {
    setForm((f) => ({ key: f.key + 1, values }))
    submit({
      origin: values.origin!,
      destination: values.destination!,
      departure: nextHourIso(),
      load_lbs: values.loadLbs,
      include_hos: true,
    })
  }

  const recommendation = plan?.recommendation[interval] ?? null
  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null
  const recommended = plan?.routes.find((r) => r.id === recommendation?.route_id) ?? null
  const startIso = heatmap?.start ?? (plan ? floorHour(plan.routes[0].departure) : null)
  const sliderTime = startIso ? Date.parse(startIso) + hour * 3600_000 : null

  const worstByHour = useMemo(() => {
    if (!heatmap) return null
    return heatmap.hours.map((_, h) => {
      let worst: number | null = null
      for (const c of heatmap.cells) {
        const v = c.risk[h]
        if (v != null && (worst == null || v > worst)) worst = v
      }
      return worst
    })
  }, [heatmap])

  return (
    <div className="app">
      <main className="map-wrap">
        <MapView
          routes={plan?.routes ?? []}
          interval={interval}
          selectedId={selectedId}
          recommendedId={recommendation?.route_id ?? null}
          onSelect={setSelectedId}
          origin={places[0]}
          destination={places[1]}
          focus={focus}
          heatmap={heatmap}
          heatVariable={heatVariable}
          heatHour={hour}
          heatVisible={heatVisible}
          sliderTime={plan ? sliderTime : null}
        />
        {loading && (
          <div className="loader glass" role="status">
            <div className="loader-head">
              <span className="radar" aria-hidden />
              <b>{LOADING_STEPS[step]}…</b>
            </div>
            <ol className="loader-steps">
              {LOADING_STEPS.map((s, k) => (
                <li key={s} className={k < step ? 'done' : k === step ? 'active' : ''}>
                  {s}
                </li>
              ))}
            </ol>
          </div>
        )}
        {plan && (
          <ForecastControls
            startIso={startIso}
            hour={hour}
            onHour={setHour}
            playing={playing}
            onPlaying={setPlaying}
            variable={heatVariable}
            onVariable={setHeatVariable}
            visible={heatVisible}
            onVisible={setHeatVisible}
            status={heatStatus}
            error={heatError}
            worstByHour={worstByHour}
          />
        )}
      </main>

      <aside className="panel glass">
        <header className="brand">
          <img src="/truck.svg" alt="" width={34} height={34} />
          <div>
            <h1>Stormline</h1>
            <p>Weather-aware truck routing</p>
          </div>
          <span className="live-pill">
            <span className="live-dot" /> Live forecast
          </span>
        </header>

        <PlanForm
          key={form.key}
          initial={form.values}
          loading={loading}
          onSubmit={submit}
          onPlacesChange={(o, d) => setPlaces([o, d])}
        />

        {planError && <div className="alert error">{planError}</div>}

        {!plan && !loading && (
          <section className="intro">
            <h2>Plan a weather-safe haul</h2>
            <p>
              We route three options, check the hourly forecast at the exact time your truck reaches every checkpoint,
              and pick the one with the least severe weather.
            </p>
            <div className="samples">
              <span>Try a sample trip</span>
              {SAMPLE_TRIPS.map((t) => (
                <button key={t.label} type="button" className="sample" onClick={() => runSample(t.values)}>
                  {t.label}
                  <small>{(t.values.loadLbs / 1000).toFixed(0)}k lb</small>
                </button>
              ))}
            </div>
          </section>
        )}

        {loading && !plan && (
          <div className="skeletons" aria-hidden>
            <div className="skeleton tall" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}

        {plan && recommendation && recommended && (
          <section className={`results${loading ? ' stale' : ''}`} aria-live="polite">
            <div className="results-head">
              <h2>Your routes</h2>
              <div className="segmented" role="radiogroup" aria-label="Checkpoint spacing">
                {(['10', '25', '50'] as Interval[]).map((i) => (
                  <button
                    key={i}
                    type="button"
                    role="radio"
                    aria-checked={interval === i}
                    className={interval === i ? 'on' : ''}
                    onClick={() => {
                      setIntervalMi(i)
                      setSelectedId(plan.recommendation[i].route_id)
                    }}
                  >
                    {i} mi
                  </button>
                ))}
              </div>
            </div>

            <RecommendationHero
              route={recommended}
              interval={interval}
              recommendation={recommendation}
              onSelect={setSelectedId}
            />

            {plan.warnings.map((w) => (
              <div key={w} className="alert info">
                {w}
              </div>
            ))}

            <RouteCards
              routes={plan.routes}
              interval={interval}
              recommendation={recommendation}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />

            {selected && (
              <div className="section-card">
                <h3>
                  {selected.name} · trip timeline
                  <small>hover for conditions, click to zoom</small>
                </h3>
                <RiskTimeline route={selected} checkpoints={selected.checkpoints[interval]} onFocus={setFocus} />
                <div className="level-key">
                  {LEVELS.map((l, k) => (
                    <span key={l}>
                      <span className="dot" style={{ background: LEVEL_COLORS[k] }} />
                      {l}
                    </span>
                  ))}
                </div>
                <details className="cp-details">
                  <summary>
                    All {selected.checkpoints[interval].length} checkpoints <small>every {interval} mi</small>
                  </summary>
                  <CheckpointTable checkpoints={selected.checkpoints[interval]} onFocus={setFocus} />
                </details>
              </div>
            )}

            <details className="method">
              <summary>How routes are scored</summary>
              <p>
                Weather is read from the hourly forecast at each checkpoint at the truck's estimated arrival time. Each
                checkpoint's level is the worst of wind, rain and snow (load rules applied to wind) and covers the road
                halfway to its neighbours. Routes rank by fewest No Travel miles, then Severe miles, High miles,
                mileage-weighted average risk (Low 0 … No Travel 4), then travel time.
              </p>
              <p>
                Forecasts are fetched on a ~{plan.forecast_cell_mi} mi grid (coarser only on very long trips, to stay
                within the free weather API's 600 locations per minute).
              </p>
            </details>
          </section>
        )}
      </aside>
    </div>
  )
}
