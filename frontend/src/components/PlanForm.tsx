import { useState } from 'react'
import { localTzName, toLocalInput } from '../lib/format'
import type { Place, PlanRequest } from '../lib/types'
import { PlaceInput } from './PlaceInput'

export interface FormValues {
  origin: Place | null
  destination: Place | null
  loadLbs: number
}

interface Props {
  initial: FormValues
  loading: boolean
  onSubmit: (req: PlanRequest) => void
  onPlacesChange: (origin: Place | null, destination: Place | null) => void
}

const MAX_LOAD = 80_000
const LOAD_PRESETS = [
  { label: 'Empty', lbs: 0 },
  { label: '20k', lbs: 20_000 },
  { label: '35k', lbs: 35_000 },
  { label: '45k', lbs: 45_000 },
]

function nextHour(offsetHours = 1): Date {
  const d = new Date(Date.now() + offsetHours * 3600_000)
  d.setMinutes(0, 0, 0)
  return d
}

function tomorrowAt(hour: number): Date {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(hour, 0, 0, 0)
  return d
}

/** What the load-weight rules mean for this load, in words. */
function loadRuleNote(lbs: number): { tone: 'ok' | 'warn' | 'alert'; text: string } {
  if (lbs > 40_000) return { tone: 'alert', text: 'Heavy: 35–44 mph wind is Severe, 45+ mph is No Travel' }
  if (lbs > 30_000) return { tone: 'warn', text: 'Wind of 45 mph or more is No Travel for this load' }
  return { tone: 'ok', text: 'Standard wind limits: only 55+ mph is No Travel' }
}

export function PlanForm({ initial, loading, onSubmit, onPlacesChange }: Props) {
  const [origin, setOrigin] = useState<Place | null>(initial.origin)
  const [destination, setDestination] = useState<Place | null>(initial.destination)
  const [departure, setDeparture] = useState(toLocalInput(nextHour()))
  const [load, setLoad] = useState(String(initial.loadLbs))
  const [hos, setHos] = useState(true)

  const now = new Date()
  const min = toLocalInput(now)
  const max = toLocalInput(new Date(now.getTime() + 10 * 24 * 3600_000))
  const loadNum = Number(load)
  const loadValid = load !== '' && loadNum >= 0 && loadNum <= MAX_LOAD
  const canSubmit = !!origin && !!destination && !!departure && loadValid && !loading
  const note = loadRuleNote(loadValid ? loadNum : 0)
  const quickTimes = [
    { label: 'Next hour', value: toLocalInput(nextHour()) },
    { label: '+6 h', value: toLocalInput(nextHour(6)) },
    { label: 'Tomorrow 6 AM', value: toLocalInput(tomorrowAt(6)) },
  ]

  const swap = () => {
    setOrigin(destination)
    setDestination(origin)
    onPlacesChange(destination, origin)
  }

  return (
    <form
      className="plan-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (!canSubmit) return
        onSubmit({
          origin: origin!,
          destination: destination!,
          departure: new Date(departure).toISOString(),
          load_lbs: loadNum,
          include_hos: hos,
        })
      }}
    >
      <div className="trip-card">
        <div className="trip-rail" aria-hidden>
          <span className="rail-dot start" />
          <span className="rail-line" />
          <span className="rail-dot end" />
        </div>
        <div className="trip-fields">
          <PlaceInput
            label="From"
            value={origin}
            placeholder="Origin city or address"
            onChange={(p) => {
              setOrigin(p)
              onPlacesChange(p, destination)
            }}
          />
          <PlaceInput
            label="To"
            value={destination}
            placeholder="Destination city or address"
            onChange={(p) => {
              setDestination(p)
              onPlacesChange(origin, p)
            }}
          />
        </div>
        <button type="button" className="swap" onClick={swap} aria-label="Swap origin and destination" title="Swap">
          ⇅
        </button>
      </div>

      <div className="field">
        <label htmlFor="departure">
          Departure <span className="label-hint">{localTzName()}</span>
        </label>
        <input
          id="departure"
          type="datetime-local"
          value={departure}
          min={min}
          max={max}
          onChange={(e) => setDeparture(e.target.value)}
        />
        <div className="chips">
          {quickTimes.map((q) => (
            <button
              key={q.label}
              type="button"
              className={`chip-btn${departure === q.value ? ' on' : ''}`}
              onClick={() => setDeparture(q.value)}
            >
              {q.label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="load">
          Load weight <span className="label-hint">lb</span>
        </label>
        <div className="load-row">
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD}
            step={500}
            value={load}
            aria-invalid={!loadValid}
            onChange={(e) => setLoad(e.target.value)}
          />
          <div className="chips">
            {LOAD_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className={`chip-btn${loadNum === p.lbs ? ' on' : ''}`}
                onClick={() => setLoad(String(p.lbs))}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="load-meter" aria-hidden>
          <span className="load-fill" style={{ width: `${(Math.min(loadValid ? loadNum : 0, MAX_LOAD) / MAX_LOAD) * 100}%` }} />
          <span className="load-tick" style={{ left: '37.5%' }} title="30,000 lb" />
          <span className="load-tick" style={{ left: '50%' }} title="40,000 lb" />
        </div>
        <div className={`load-note ${note.tone}`}>{loadValid ? note.text : 'Load must be between 0 and 80,000 lb.'}</div>
      </div>

      <label className="toggle">
        <input type="checkbox" checked={hos} onChange={(e) => setHos(e.target.checked)} />
        <span className="toggle-track" aria-hidden>
          <span className="toggle-thumb" />
        </span>
        <span>
          Hours-of-service stops
          <small>30 min break after 8 h, 10 h rest after 11 h driving</small>
        </span>
      </label>

      <button type="submit" className={`cta${loading ? ' busy' : ''}`} disabled={!canSubmit}>
        {loading ? 'Scanning the forecast…' : 'Find the safest route'}
        <span className="cta-arrow" aria-hidden>
          →
        </span>
      </button>
      {(!origin || !destination) && <p className="form-hint">Pick both places from the suggestions.</p>}
    </form>
  )
}
