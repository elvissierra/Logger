// Shared time/date helpers used across the Logger frontend

export const pad = (n) => String(n).padStart(2, '0')

export function startOfWeek (d = new Date()) {
  const day = d.getDay() || 7 // Sun=0 -> 7
  const monday = new Date(d)
  monday.setHours(0, 0, 0, 0)
  monday.setDate(d.getDate() - (day - 1))
  return monday
}
export const addDays = (d, n) => { const z = new Date(d); z.setDate(z.getDate() + n); return z }
export const dateKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const labelFor = (d) => d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
export const isSameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

export function timeHMFromISO (iso) { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}` }
export function composeISOFromLaneAndTime (laneKey, hm) {
  const local = new Date(`${laneKey}T${hm}`) // local time
  return local.toISOString() // store UTC
}
export function laneKeyFromISO (iso) { if (!iso) return null; return dateKey(new Date(iso)) }

export function roundToQuarterHours (h) {
  return Math.round((Number(h) || 0) / 0.25) * 0.25
}
export function hoursBetween (isoA, isoB) {
  if (!isoA || !isoB) return 0
  const a = new Date(isoA).getTime()
  const b = new Date(isoB).getTime()
  return Math.max(0, (b - a) / 3600000)
}
export const hoursBetweenRounded = (isoA, isoB) => roundToQuarterHours(hoursBetween(isoA, isoB))

export function roundHMToQuarter (hm) {
  const parts = (hm || '00:00').split(':')
  const h = parseInt(parts[0] || '0', 10)
  const m = parseInt(parts[1] || '0', 10)
  const total = h * 60 + m
  const rounded = Math.round(total / 15) * 15
  const rh = Math.floor(rounded / 60)
  const rm = rounded % 60
  return `${pad(rh)}:${pad(rm)}`
}
export function roundDateToQuarter (d) {
  const ms = 15 * 60 * 1000
  return new Date(Math.round(d.getTime() / ms) * ms)
}

// ISO <-> input[type=datetime-local] converters (local time based)
export function toLocalInput (iso) {
  if (!iso) return ''
  const d = new Date(iso)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16) // YYYY-MM-DDTHH:mm
}
export function fromLocalInput (localStr) {
  if (!localStr) return ''
  const d = new Date(localStr) // local time
  const ms = 15 * 60 * 1000
  const roundedLocal = new Date(Math.round(d.getTime() / ms) * ms)
  return new Date(roundedLocal.getTime() - roundedLocal.getTimezoneOffset() * 60000).toISOString()
}

// Safe hours formatter
export function fmtH (n, d = 1) {
  const x = Number(n)
  return Number.isFinite(x) ? x.toFixed(d) : (0).toFixed(d)
}