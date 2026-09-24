import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import { companyHref } from '../useHashRoute'

const DAYS = 30
const iso = (d) => d.toISOString().slice(0, 10)
const qty = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

// lockin_expiry lens: anchor lock-in expiries in the next 30 days. The validated dip is
// T-1 -> T+2 (strongest at the 90-day unlock); not shortable, so it is an avoid/exit rule.
export default function UpcomingUnlocks() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const today = new Date()
    const until = new Date(today.getTime() + DAYS * 864e5)
    supabase
      .from('corporate_events')
      .select('id,symbol,event_type,event_date,details')
      .in('event_type', ['anchor_lockin_30', 'anchor_lockin_90'])
      .gte('event_date', iso(today))
      .lte('event_date', iso(until))
      .order('event_date')
      .order('symbol')
      .then(({ data, error }) => {
        setError(error ? error.message : null)
        setRows(data || [])
      })
  }, [])

  return (
    <section className="panel" aria-labelledby="unlocks-h">
      <h2 id="unlocks-h">
        Upcoming anchor unlocks <span className="muted">· lockin_expiry lens · next {DAYS} days</span>
      </h2>
      <p className="dim small">
        Validated dip T-1 → T+2 vs NIFTY 500 (−1.25% at the 90-day unlock, placebo ~0). Not shortable —
        avoid buying into it; consider exiting a recent IPO before T-1.
      </p>
      {error && <p className="note error" role="alert">Failed to load: {error}</p>}
      {rows === null ? (
        <p className="empty">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="empty">No anchor lock-in expiries in the next {DAYS} days.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Date</th><th scope="col">Symbol</th><th scope="col">Unlock</th>
                <th scope="col">Board</th><th scope="col" className="r">Anchor shares</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="dim">{r.event_date}</td>
                  <td><a href={companyHref(r.symbol)}><code>{r.symbol}</code></a></td>
                  <td>{r.event_type === 'anchor_lockin_90' ? '90d (rest)' : '30d (50%)'}</td>
                  <td className="dim">{r.details?.board || '—'}</td>
                  <td className="r">{qty(r.details?.anchor_shares)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
