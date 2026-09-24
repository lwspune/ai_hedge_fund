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
