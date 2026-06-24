const STYLE = {
  edge: { label: 'EDGE', cls: 'badge-edge' },
  conditional: { label: 'CONDITIONAL EDGE', cls: 'badge-edge' },
  thin: { label: 'THIN', cls: 'badge-thin' },
  null: { label: 'NO EDGE', cls: 'badge-null' },
}

export default function VerdictBadge({ verdict }) {
  const s = STYLE[verdict] || { label: String(verdict).toUpperCase(), cls: 'badge-null' }
  return (
    <span className={`badge ${s.cls}`} aria-label={`Verdict: ${s.label}`}>
      {s.label}
    </span>
  )
}
