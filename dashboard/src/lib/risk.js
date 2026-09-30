// Risk lens (risk_metrics, written daily by scripts/refresh_risk.py). Measurements, not a signal:
// no verdict and no score — the chips and the Risk tab only describe the security.
import { supabase } from '../supabaseClient'
import { fmtNum, fmtPct } from './format'

// Every flag scanner/risk.py can write (FLAGS there). tests/test_risk.py checks the two lists match.
const FLAG_LABEL = {
  short_history: 'Short history (under 120 sessions)',
  sparse: 'Sparse trading (printed on under 80% of sessions)',
  action_unverified: 'Corporate action not confirmed by prices',
  price_break: 'Price break with no recorded action',
  illiquid: 'Illiquid (under ₹1 cr/day)',
  sme: 'SME board',
  asm: 'On ASM surveillance',
  gsm: 'On GSM surveillance',
}
export const RISK_FLAGS = Object.keys(FLAG_LABEL)

const WARN = new Set(['asm', 'gsm', 'illiquid'])
const BLANKING = new Set(['action_unverified', 'price_break'])

export const flagLabel = (f) => FLAG_LABEL[f] || f

export const blanksPriceMetrics = (flags) => (flags || []).some((f) => BLANKING.has(f))

export const fmtDaysToExit = (n) => (n == null ? '—' : `${fmtNum(n)} ${n === 1 ? 'day' : 'days'}`)

function ordinal(n) {
  const t = n % 100
  if (t >= 11 && t <= 13) return `${n}th`
  return `${n}${{ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'}`
}

export const fmtRank = (r) => (r == null ? undefined : `${ordinal(Math.round(r))} pct of market`)

// The Desk chip: short visible text, a full sentence for screen readers, flags in the tooltip.
export function riskChip(symbol, r) {
  if (!r) return null
  const flags = r.flags || []
  const vol = fmtPct(r.vol_1y, 0)
  const exit = r.days_to_exit_5l == null ? '—' : `${r.days_to_exit_5l} d`
  const labels = flags.map(flagLabel)
  return {
    text: `vol ${vol} · exit ${exit}`,
    label: `${symbol} risk: 1-year volatility ${vol}, ${fmtDaysToExit(r.days_to_exit_5l)} to exit ₹5 lakh`
      + (labels.length ? `. ${labels.join('; ')}` : ''),
    title: labels.length ? labels.join('; ') : undefined,
    tone: flags.some((f) => WARN.has(f)) ? 'warn' : 'neutral',
  }
}

export async function loadRisk(symbol) {
  const { data, error } = await supabase.from('risk_metrics').select('*').eq('symbol', symbol).maybeSingle()
  if (error) throw error
  return data
}

const CHIP_COLS = 'symbol,vol_1y,days_to_exit_5l,flags'

// { symbol: row } for a Desk list — one query per list.
export async function loadRiskFor(symbols) {
  const syms = [...new Set((symbols || []).filter(Boolean))]
  if (!syms.length) return {}
  const { data, error } = await supabase.from('risk_metrics').select(CHIP_COLS).in('symbol', syms)
  if (error) throw error
  return Object.fromEntries((data || []).map((r) => [r.symbol, r]))
}

// Attach `risk` to each row. A failed risk read never hides the list itself: the chips go blank.
export async function withRisk(rows) {
  try {
    const bySym = await loadRiskFor(rows.map((r) => r.symbol))
    return rows.map((r) => ({ ...r, risk: bySym[r.symbol] || null }))
  } catch (e) {
    console.error('risk_metrics load failed', e)
    return rows
  }
}
