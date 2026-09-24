import { ROLE_ORDER, roleLabel, signalHeadline, signalLabel, typeLabel } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import { Badge, VerdictBadge } from './ui/Badge'

const COLUMNS = [
  {
    key: 'name', header: 'Signal',
    render: (s) => <>{signalLabel(s.name)}<span className="cell-sub mono">{s.name}</span></>,
  },
  { key: 'verdict', header: 'Verdict', render: (s) => <VerdictBadge verdict={s.verdict} /> },
  { key: 'role', header: 'Role', render: (s) => <Badge tone={s.role === 'primary' ? 'pos' : 'neutral'}>{roleLabel(s.role)}</Badge> },
  { key: 'type', header: 'Type', render: (s) => <span className="t2">{typeLabel(s.type)}</span> },
  { key: 'finding', header: 'Finding', render: (s) => <span className="t2 cell-wrap">{signalHeadline(s.name)}</span> },
]

export default function SignalsOverview({ signals }) {
  const rows = [...signals].sort((a, b) =>
    (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9) || a.name.localeCompare(b.name))
  return (
    <Section id="signals" title="Signals"
             info="Every signal carries the verdict its event study produced. Falsified signals stay as lenses and are never traded.">
      <DataTable caption="Signals" columns={COLUMNS} rows={rows} rowKey={(s) => s.name} />
    </Section>
  )
}
