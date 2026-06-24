import { useEffect, useState } from 'react'
import { supabase, configured } from './supabaseClient'
import signals from './signals.json'
import SignalsOverview from './components/SignalsOverview'
import BuybackTable from './components/BuybackTable'
import TrackedPositions from './components/TrackedPositions'
import ScanHistory from './components/ScanHistory'

export default function App() {
  const [buybacks, setBuybacks] = useState([])
  const [runs, setRuns] = useState([])
  const [positions, setPositions] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!configured) {
      setError('Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY — set them in dashboard/.env')
      setLoading(false)
      return
    }
    ;(async () => {
      try {
        const [bb, sr, td] = await Promise.all([
          supabase.from('buybacks').select('*').order('record_date', { ascending: false }).limit(100),
          supabase.from('scan_runs').select('*').order('run_at', { ascending: false }).limit(25),
          supabase
            .from('tenders')
            .select('*, buybacks(symbol), outcomes(accepted_shares,realized_acceptance,realized_return)')
            .order('decided_on', { ascending: false }),
        ])
        for (const r of [bb, sr, td]) if (r.error) throw r.error
        setBuybacks(bb.data || [])
        setRuns(sr.data || [])
        setPositions(td.data || [])
      } catch (e) {
        setError(e.message || String(e))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Market-Intel <span className="accent">Scanner</span></h1>
        <p className="subtitle">
          Indian equities · validated signals · manual execution. Every signal carries its
          verdict — falsified ones are kept as lenses, never traded as edge.
        </p>
      </header>

      {error && <div className="banner error" role="alert">⚠ {error}</div>}

      <SignalsOverview signals={signals} />

      {loading ? (
        <div className="banner">Loading live data…</div>
      ) : (
        <>
          <BuybackTable rows={buybacks} />
          <TrackedPositions rows={positions} />
          <ScanHistory rows={runs} />
        </>
      )}

      <footer className="app-footer">
        Read-only surfacing · data from Supabase (RLS read-only) · writes via the <code>track</code> CLI
      </footer>
    </div>
  )
}
