import VerdictBadge from './VerdictBadge'

const ROLE_ORDER = { primary: 0, watch: 1, lens: 2, documented: 3 }

export default function SignalsOverview({ signals }) {
  const sorted = [...signals].sort(
    (a, b) => (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9)
  )
  return (
    <section className="panel" aria-labelledby="signals-h">
      <h2 id="signals-h">Signals <span className="muted">· the honesty layer</span></h2>
      <div className="cards">
        {sorted.map((s) => (
          <article key={s.name} className={`card role-${s.role}`}>
            <div className="card-top">
              <code className="sig-name">{s.name}</code>
              <VerdictBadge verdict={s.verdict} />
            </div>
            <div className="card-meta">{s.type} · {s.role}</div>
            <p className="card-summary">{s.summary}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
