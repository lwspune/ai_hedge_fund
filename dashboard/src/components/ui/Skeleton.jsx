export function Skeleton({ lines = 1, width }) {
  return (
    <span className="sk-lines" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="sk" style={{ width: i === lines - 1 && lines > 1 ? '60%' : width }} />
      ))}
    </span>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="sk-table" aria-hidden="true">
      {Array.from({ length: rows + 1 }, (_, r) => (
        <div key={r} className="sk-row" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {Array.from({ length: cols }, (_, c) => (
            <span key={c} className={r === 0 ? 'sk sk-head' : 'sk'} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonStats({ n = 8 }) {
  return (
    <div className="stat-grid" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <span key={i} className="sk-stat"><span className="sk sk-head" /><span className="sk" /></span>
      ))}
    </div>
  )
}

// Loading placeholder with a text alternative for screen readers.
export function Loading({ label = 'Loading', children }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      {children}
    </div>
  )
}
