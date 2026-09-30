import { riskChip } from '../../lib/risk'
import { companyHref } from '../../useHashRoute'

// Desk risk chip: "vol 34% · exit 3 d", linking to the company Risk tab. Warn tone on ASM / GSM /
// illiquid. Measurements only — it never ranks a row.
export default function RiskChip({ symbol, risk }) {
  const c = riskChip(symbol, risk)
  if (!c) return '—'
  return (
    <a className={`badge badge-${c.tone} risk-chip`} href={companyHref(symbol, 'risk')}
       aria-label={c.label} title={c.title}>
      {c.text}
    </a>
  )
}
