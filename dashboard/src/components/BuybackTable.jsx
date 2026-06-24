const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')
const num = (v) =>
  v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })

export default function BuybackTable({ rows }) {
  return (
    <section className="panel" aria-labelledby="bb-h">
      <h2 id="bb-h">Buyback candidates <span className="muted">· primary edge</span></h2>
      {rows.length === 0 ? (
        <p className="empty">
          No buybacks stored. Run <code>python -m scanner.run buyback_arb --save</code>.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Company</th>
                <th className="r">Buyback ₹</th>
                <th className="r">Entitlement</th>
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
