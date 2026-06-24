const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')
const inr = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

export default function TrackedPositions({ rows }) {
  return (
    <section className="panel" aria-labelledby="pos-h">
      <h2 id="pos-h">Tracked positions <span className="muted">· feedback loop</span></h2>
      {rows.length === 0 ? (
        <p className="empty">
          No tenders yet. Record one with <code>python -m scanner.track tender …</code>,
          then <code>… outcome …</code> — realized acceptance vs the floor calibrates selection.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Decided</th>
                <th className="r">Shares</th>
                <th className="r">Capital ₹</th>
                <th className="r">Accepted</th>
                <th className="r">Realized accept.</th>
                <th className="r">Return</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const o = (t.outcomes && t.outcomes[0]) || {}
                return (
                  <tr key={t.id}>
                    <td><code>{t.buybacks?.symbol || '—'}</code></td>
                    <td className="dim">{t.decided_on}</td>
                    <td className="r">{t.shares_bought ?? '—'}</td>
                    <td className="r">{inr(t.capital)}</td>
                    <td className="r">{o.accepted_shares ?? '—'}</td>
                    <td className="r accent">{pct(o.realized_acceptance)}</td>
                    <td className="r">{pct(o.realized_return)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
