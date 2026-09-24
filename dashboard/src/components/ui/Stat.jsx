export function Stat({ label, value, sub, tone, title }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd className={tone ? `tone-${tone}` : undefined} title={title}>
        {value}
        {sub && <span className="stat-sub">{sub}</span>}
      </dd>
    </div>
  )
}

export function StatGrid({ label, children }) {
  return <dl className="stat-grid" aria-label={label}>{children}</dl>
}
