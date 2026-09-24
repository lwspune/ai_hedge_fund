import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import { companyHref } from '../useHashRoute'

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(2) + '%')
const px = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }))
const lakh = (v) => (v == null ? '—' : (v / 1e5).toFixed(1) + ' L')

// rights_re: rights entitlements trading now, from the latest daily scan (scan_runs +
// candidates). A positive gap = RE cheaper than (stock - issue price).
export default function RightsPanel() {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    ;(async () => {
      const run = await supabase.from('scan_runs').select('id,run_at')
        .eq('signal_name', 'rights_re').order('run_at', { ascending: false }).limit(1)
      if (run.error) return setState({ error: run.error.message })
      const latest = (run.data || [])[0]
      if (!latest) return setState({ rows: [], runAt: null })
      const c = await supabase.from('candidates').select('id,symbol,score,payload')
        .eq('run_id', latest.id).order('score', { ascending: false })
      if (c.error) return setState({ error: c.error.message })
      setState({ rows: c.data || [], runAt: latest.run_at })
    })()
  }, [])

  const { loading, error, rows, runAt } = state
  return (
    <section className="panel" aria-labelledby="rights-h">
      <h2 id="rights-h">
        Rights entitlements <span className="muted">· rights_re · {runAt ? `as of ${runAt.slice(0, 16).replace('T', ' ')} UTC` : 'no scan yet'}</span>
      </h2>
      <p className="dim small">
        REs trade ~3.5% below fair value (stock − issue price) on average. Only worth it if you want the
        stock anyway: buy the RE and apply before the issue closes — or, if you hold it, switch shares to REs.
      </p>
      {error && <p className="note error" role="alert">Failed to load: {error}</p>}
      {loading ? <p className="empty">Loading…</p> : !error && rows.length === 0 ? (
        <p className="empty">No rights entitlements trading right now.</p>
      ) : !error && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Symbol</th><th scope="col">Ratio</th><th scope="col" className="r">Issue ₹</th>
                <th scope="col" className="r">Stock ₹</th><th scope="col" className="r">RE ₹</th>
                <th scope="col" className="r">Gap</th><th scope="col" className="r">RE turnover</th>
                <th scope="col">RE last day</th><th scope="col">Apply by</th><th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ id, symbol, payload: p }) => (
                <tr key={id}>
                  <td><a href={companyHref(symbol)}><code>{symbol}</code></a></td>
                  <td className="dim">{p.ratio || '—'}</td>
                  <td className="r">{px(p.issue_price)}</td>
                  <td className="r">{px(p.stock)}</td>
                  <td className="r">{px(p.re)}</td>
                  <td className={p.action?.startsWith('BUY') ? 'r accent' : 'r'}>{pct(p.gap)}</td>
                  <td className="r">{lakh(p.turnover)}</td>
                  <td className="dim">{p.re_last_day || '—'}</td>
                  <td className="dim">{p.issue_close || '—'}</td>
                  <td className="dim">{p.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
