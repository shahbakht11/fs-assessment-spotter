import { useEffect, useId, useRef, useState } from 'react'
import { searchPlaces } from '../lib/api'
import type { Place } from '../lib/types'

interface Props {
  label: string
  value: Place | null
  onChange: (p: Place | null) => void
  placeholder?: string
}

/** Debounced place autocomplete (keyboard: ↑/↓ to move, Enter to pick, Esc to close). */
export function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId()
  const [text, setText] = useState(value?.label ?? '')
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const typed = useRef(false)

  useEffect(() => {
    if (value && value.label !== text) setText(value.label)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  useEffect(() => {
    if (!typed.current || text.trim().length < 3) {
      setResults([])
      return
    }
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      setLoading(true)
      searchPlaces(text, ctrl.signal)
        .then((r) => {
          setResults(r)
          setActive(0)
          setOpen(true)
        })
        .catch(() => {})
        .finally(() => setLoading(false))
    }, 250)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [text])

  const pick = (p: Place) => {
    typed.current = false
    onChange(p)
    setText(p.label)
    setOpen(false)
  }

  return (
    <div className="field place">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={text}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={`${id}-list`}
        onChange={(e) => {
          typed.current = true
          setText(e.target.value)
          onChange(null)
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!open || !results.length) return
          if (e.key === 'ArrowDown') setActive((a) => Math.min(a + 1, results.length - 1))
          else if (e.key === 'ArrowUp') setActive((a) => Math.max(a - 1, 0))
          else if (e.key === 'Enter') {
            e.preventDefault()
            pick(results[active])
          } else if (e.key === 'Escape') setOpen(false)
          else return
          e.preventDefault()
        }}
      />
      {loading && <span className="field-spinner" aria-hidden />}
      {open && results.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {results.map((r, k) => (
            <li
              key={`${r.lat},${r.lon},${k}`}
              role="option"
              aria-selected={k === active}
              className={k === active ? 'active' : ''}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(r)
              }}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
