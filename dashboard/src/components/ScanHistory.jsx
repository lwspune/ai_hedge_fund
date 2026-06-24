import VerdictBadge from './VerdictBadge'

export default function ScanHistory({ rows }) {
  return (
    <section className="panel" aria-labelledby="sh-h">
      <h2 id="sh-h">Scan history</h2>
      {rows.length === 0 ? (
        <p className="empty">No scans recorded yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Verdict</th>
                <th className="r">Candidates</th>
                <th>Run at</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><code>{r.signal_name}</code></td>
                  <td><VerdictBadge verdict={r.verdict} /></td>
                  <td className="r">{r.n_candidates}</td>
                  <td className="dim">{new Date(r.run_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
