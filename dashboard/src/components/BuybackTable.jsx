import { useState } from 'react'
import { supabase } from '../supabaseClient'

const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')
const num = (v) =>
  v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })

export default function BuybackTable({ rows, onRefresh }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  async function refresh() {
    setBusy(true)
    setMsg(null)
    try {
      const { data, error } = await supabase.functions.invoke('refresh-buybacks', { method: 'POST' })
      if (error) throw error
      if (data?.ok === false) throw new Error(data.error || 'refresh failed')
      setMsg(`Scanned ${data.scanned} ids, upserted ${data.upserted} (${(data.found || []).join(', ') || '—'}).`)
      if (onRefresh) await onRefresh()
    } catch (e) {
      setMsg('Refresh failed: ' + (e.message || String(e)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="bb-h">
      <div className="panel-head">
        <h2 id="bb-h">Buyback candidates <span className="muted">· primary edge</span></h2>
        <button className="btn" onClick={refresh} disabled={busy} aria-busy={busy}
                aria-label="Discover current buybacks from chittorgarh">
          {busy ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}
      {rows.length === 0 ? (
        <p className="empty">No buybacks stored. Hit Refresh, or run <code>python -m scanner.run buyback_arb --save</code>.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Company</th>
                <th className="r">Buyback ₹</th>
                <th className="r">Entitlement</th>
                <th className="r">Issue ₹cr</th>
                <th className="r">Est. floor</th>
                <th>Record date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td><code>{b.symbol}</code></td>
                  <td className="dim">{b.company}</td>
                  <td className="r">{num(b.buyback_price)}</td>
                  <td className="r">{pct(b.entitlement_small)}</td>
                  <td className="r">{num(b.issue_size_cr)}</td>
                  <td className="r">{pct(b.est_return)}</td>
                  <td className="dim">{b.record_date || '—'}</td>
                  <td><span className={`status status-${b.status}`}>{b.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
