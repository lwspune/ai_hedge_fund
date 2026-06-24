import { useState } from 'react'
import { supabase } from '../supabaseClient'

const cr = (v) => (v == null ? '—' : '₹' + (v / 1e7).toFixed(2) + ' cr')
const qty = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

export default function DealsView({ rows, onRefresh }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  async function refresh() {
    setBusy(true)
    setMsg(null)
    try {
      const { data, error } = await supabase.functions.invoke('refresh-deals', { method: 'POST' })
      if (error) throw error
      if (data?.ok === false) throw new Error(data.error || 'refresh failed')
      setMsg(`Refreshed ${data.inserted} deals for ${(data.dates || []).join(', ') || '—'}.`)
      if (onRefresh) await onRefresh()
    } catch (e) {
      setMsg('Refresh failed: ' + (e.message || String(e)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="deals-h">
      <div className="panel-head">
        <h2 id="deals-h">Bulk/Block deals <span className="muted">· institutional activity</span></h2>
        <button className="btn" onClick={refresh} disabled={busy} aria-busy={busy}
                aria-label="Refresh deals from NSE">
          {busy ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}
      {rows.length === 0 ? (
        <p className="empty">No deals stored. Hit Refresh to pull today's from NSE.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th><th>Symbol</th><th>Client</th><th>Side</th>
                <th className="r">Qty</th><th className="r">Value</th><th>Kind</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td className="dim">{d.deal_date}</td>
                  <td><code>{d.symbol}</code></td>
                  <td className="dim" title={d.client}>{(d.client || '').slice(0, 30)}</td>
                  <td><span className={`side side-${(d.side || '').toLowerCase()}`}>{d.side}</span></td>
                  <td className="r">{qty(d.qty)}</td>
                  <td className="r">{cr(d.value)}</td>
                  <td className="dim">{d.kind}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
