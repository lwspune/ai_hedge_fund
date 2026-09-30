// Market regime (market_regime, written daily by scripts/refresh_regime.py). Measurements, not a signal:
// no label, no score. The two warn marks below are display conventions, not verdicts.
import { supabase } from '../supabaseClient'
import { fmtNum, fmtOrdinal, fmtPct } from './format'

export const DD_WARN = -0.10        // NIFTY 500 10% off its high: a correction by the usual convention
export const VOL_PCT_WARN = 90      // 20-day volatility at or above its 90th percentile since 2020

const PAGE = 1000                   // PostgREST max rows per request

export function regimeTone(r) {
  return {
    dd: r?.n500_dd != null && r.n500_dd <= DD_WARN ? 'warn' : null,
    vol: r?.n500_vol_pct != null && r.n500_vol_pct >= VOL_PCT_WARN ? 'warn' : null,
  }
}

export const fmtVolPct = (n) => (n == null ? null : `${fmtOrdinal(n)} pct`)

// The Desk strip, one part per question. A warn part also carries a word (`note`), never colour alone.
export function regimeStrip(r) {
  if (!r) return null
  const tone = regimeTone(r)
  const volPct = fmtVolPct(r.n500_vol_pct)
  return [
    { key: 'dd', text: `NIFTY 500 ${fmtPct(r.n500_dd)} from high`, tone: tone.dd, note: tone.dd && 'correction' },
    { key: 'vol', text: `vol ${fmtPct(r.n500_vol_20, 0)}${volPct ? ` (${volPct})` : ''}`, tone: tone.vol,
      note: tone.vol && 'high volatility' },
    { key: 'breadth', text: `${fmtPct(r.pct_above_200, 0)} above 200-DMA`, tone: null },
    { key: 'hl', text: `${fmtNum(r.new_highs)} highs / ${fmtNum(r.new_lows)} lows`, tone: null },
  ]
}

export async function loadLatestRegime() {
  const { data, error } = await supabase.from('market_regime').select('*')
    .order('trade_date', { ascending: false }).limit(1)
  if (error) throw error
  return data?.[0] ?? null
}

const fetchRegimePage = (from, to) => supabase.from('market_regime').select('*')
  .order('trade_date', { ascending: true }).range(from, to)

// The whole history (~1,650 rows), oldest first, paged past the 1,000-row cap.
export async function loadRegimeHistory(fetchPage = fetchRegimePage) {
  const rows = []
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await fetchPage(from, from + PAGE - 1)
    if (error) throw error
    rows.push(...(data || []))
    if (!data || data.length < PAGE) return rows
  }
}
