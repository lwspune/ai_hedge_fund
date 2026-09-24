import { supabase } from '../supabaseClient'

// Latest saved scan of a signal and its candidates, best score first.
export async function latestScan(signal) {
  const run = await supabase.from('scan_runs').select('id,run_at')
    .eq('signal_name', signal).order('run_at', { ascending: false }).limit(1)
  if (run.error) throw run.error
  const latest = (run.data || [])[0]
  if (!latest) return { runAt: null, rows: [] }
  const c = await supabase.from('candidates').select('id,symbol,score,payload')
    .eq('run_id', latest.id).order('score', { ascending: false })
  if (c.error) throw c.error
  return { runAt: latest.run_at, rows: c.data || [] }
}

const newest = (table, col, filter) => {
  let q = supabase.from(table).select(col)
  if (filter) q = q.eq(...filter)
  return q.order(col, { ascending: false }).limit(1)
}

// Newest row per source for the freshness dot and the Desk status strip.
export async function loadFreshness() {
  const res = await Promise.all([
    newest('market_deals', 'deal_date'),
    newest('scan_runs', 'run_at', ['signal_name', 'buyback_arb']),
    newest('scan_runs', 'run_at', ['signal_name', 'rights_re']),
    newest('filings', 'disclosed_at'),
  ])
  const err = res.find((r) => r.error)
  if (err) throw err.error
  const v = (r, col) => r.data?.[0]?.[col] ?? null
  return {
    deals: v(res[0], 'deal_date'),
    buybackScan: v(res[1], 'run_at'),
    rightsScan: v(res[2], 'run_at'),
    filings: v(res[3], 'disclosed_at'),
  }
}
