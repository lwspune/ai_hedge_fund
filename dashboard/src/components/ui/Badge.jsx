// One badge for verdicts, statuses, sides and index tags. Tone carries meaning:
// pos = edge / buy / open, warn = thin / watch / stale, neg = sell / error, neutral = no edge / closed.
export function Badge({ tone = 'neutral', title, children }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>
}

const VERDICT = {
  edge: ['pos', 'Edge'],
  conditional: ['pos', 'Conditional edge'],
  thin: ['warn', 'Thin'],
  null: ['neutral', 'No edge'],
}

export function VerdictBadge({ verdict }) {
  const [tone, label] = VERDICT[verdict] || ['neutral', String(verdict)]
  return <Badge tone={tone}>{label}</Badge>
}

const STATUS = { open: 'pos', tendered: 'warn', settled: 'neutral', skipped: 'neutral' }

export function StatusBadge({ status }) {
  if (!status) return '—'
  return <Badge tone={STATUS[status] || 'neutral'}>{status[0].toUpperCase() + status.slice(1)}</Badge>
}

export function SideBadge({ side }) {
  const s = (side || '').toUpperCase()
  if (!s) return '—'
  return <Badge tone={s === 'BUY' ? 'pos' : s === 'SELL' ? 'neg' : 'neutral'}>{s === 'BUY' ? 'Buy' : s === 'SELL' ? 'Sell' : s}</Badge>
}
