// Every date and number in the UI goes through here. Source rows store dates as 'YYYY-MM-DD'
// and timestamps in UTC; the user reads IST, so timestamps are converted to Asia/Kolkata
// explicitly rather than trusting the browser's zone. All formatters return '—' for no value.

const TZ = 'Asia/Kolkata'
const DASH = '—'
const MINUS = '−'
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const missing = (v) => v == null || (typeof v === 'number' && Number.isNaN(v)) || v === ''

export const dash = (v, fn) => (missing(v) ? DASH : fn(v))

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

const istParts = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})

// -> { y, m, d, hh, mm } in IST. Date-only strings are calendar dates and are not shifted.
function parts(v) {
  if (typeof v === 'string' && DATE_ONLY.test(v)) {
    const [y, m, d] = v.split('-').map(Number)
    return { y, m, d, hh: 0, mm: 0 }
  }
  const t = v instanceof Date ? v : new Date(v)
  if (Number.isNaN(t.getTime())) return null
  const p = Object.fromEntries(istParts.formatToParts(t).map((x) => [x.type, x.value]))
  return { y: +p.year, m: +p.month, d: +p.day, hh: +p.hour, mm: +p.minute }
}

const dayNumber = ({ y, m, d }) => Date.UTC(y, m - 1, d) / 864e5

const todayParts = (today) => parts(today ?? new Date())

export const todayIso = (now = new Date()) => {
  const p = parts(now)
  return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`
}

export function addDaysIso(iso, n) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10)
}

function dayMonth(p, today) {
  const base = `${p.d} ${MONTHS[p.m - 1]}`
  return p.y === todayParts(today).y ? base : `${base} ${p.y}`
}

export function fmtDate(v, today) {
  if (missing(v)) return DASH
  const p = parts(v)
  return p ? dayMonth(p, today) : DASH
}

export function fmtDateTime(v, today) {
  if (missing(v)) return DASH
  const p = parts(v)
  if (!p) return DASH
  return `${dayMonth(p, today)}, ${String(p.hh).padStart(2, '0')}:${String(p.mm).padStart(2, '0')} IST`
}

export function daysFrom(v, today) {
  const p = parts(v)
  return p ? dayNumber(p) - dayNumber(todayParts(today)) : null
}

export function fmtRelative(v, today) {
  if (missing(v)) return DASH
  const n = daysFrom(v, today)
  if (n == null) return DASH
  if (n === 0) return 'today'
  if (n === 1) return 'tomorrow'
  if (n === -1) return 'yesterday'
  const a = Math.abs(n)
  const unit = a > 21 ? `${Math.round(a / 7)} wk` : `${a} d`
  return n > 0 ? `in ${unit}` : `${unit} ago`
}

// Elapsed time for a timestamp (scan runs): minutes and hours inside a day, days beyond.
export function fmtAgo(v, now = new Date()) {
  if (missing(v)) return DASH
  const t = new Date(v)
  if (Number.isNaN(t.getTime())) return DASH
  const mins = Math.floor((now.getTime() - t.getTime()) / 6e4)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (mins < 24 * 60) return `${Math.floor(mins / 60)} h ago`
  return fmtRelative(v, now)
}

const nf = {}
function group(v, min, max) {
  const k = `${min}-${max}`
  nf[k] ??= new Intl.NumberFormat('en-IN', { minimumFractionDigits: min, maximumFractionDigits: max })
  return nf[k].format(Math.abs(v))
}
const sign = (v) => (v < 0 && Math.abs(v) > 0 ? MINUS : '')

const num = (v) => (typeof v === 'number' ? v : Number(v))

export const fmtNum = (v, dp = 0) => dash(v, (x) => {
  const n = num(x)
  if (Number.isNaN(n)) return DASH
  const s = group(n, 0, dp)
  return (s === '0' ? '' : sign(n)) + s
})

export const fmtPctPts = (v, dp = 1) => dash(v, (x) => {
  const n = num(x)
  if (Number.isNaN(n)) return DASH
  const s = Math.abs(n).toFixed(dp)
  return (Number(s) === 0 ? '' : sign(n)) + s + '%'
})

export const fmtPct = (v, dp = 1) => dash(v, (x) => fmtPctPts(num(x) * 100, dp))

export const fmtInr = (v, dp = 2) => dash(v, (x) => {
  const n = num(x)
  if (Number.isNaN(n)) return DASH
  return `${sign(n)}₹${group(n, dp, dp)}`
})

export const fmtCrValue = (v) => dash(v, (x) => {
  const n = num(x)
  if (Number.isNaN(n)) return DASH
  const dp = Math.abs(n) >= 100 ? 0 : 2
  return `${sign(n)}₹${group(n, 0, dp)} cr`
})

export const fmtCr = (v) => dash(v, (x) => fmtCrValue(num(x) / 1e7))

export const fmtLakh = (v) => dash(v, (x) => {
  const n = num(x)
  if (Number.isNaN(n)) return DASH
  return `${sign(n)}${(Math.abs(n) / 1e5).toFixed(1)} L`
})

export const fmtQty = (v) => fmtNum(v, 0)
