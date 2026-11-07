const timeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
})
const tzFmt = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })

export const fmtTime = (iso: string | Date) => timeFmt.format(new Date(iso))

export const localTzName = () =>
  tzFmt.formatToParts(new Date()).find((p) => p.type === 'timeZoneName')?.value ?? ''

export function fmtDuration(seconds: number): string {
  const mins = Math.round(seconds / 60)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h >= 24) return `${Math.floor(h / 24)} d ${h % 24} h ${m.toString().padStart(2, '0')} m`
  return h ? `${h} h ${m.toString().padStart(2, '0')} m` : `${m} min`
}

export const fmtMiles = (mi: number) => `${Math.round(mi).toLocaleString()} mi`

/** Value for <input type="datetime-local"> in the browser's timezone. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// WMO weather codes (Open-Meteo) → short text
const WMO: Record<number, string> = {
  0: 'Clear', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast', 45: 'Fog', 48: 'Rime fog',
  51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle',
  61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain', 67: 'Freezing rain',
  71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains', 80: 'Rain showers',
  81: 'Rain showers', 82: 'Violent showers', 85: 'Snow showers', 86: 'Heavy snow showers',
  95: 'Thunderstorm', 96: 'Thunderstorm, hail', 99: 'Thunderstorm, hail',
}
export const weatherText = (code: number | null) => (code == null ? '' : (WMO[code] ?? ''))
