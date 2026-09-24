import useLoad from '../lib/useLoad'
import { latestScan } from '../lib/queries'
import { fmtDate, fmtDateTime, fmtInr, fmtLakh, fmtPct, fmtRelative } from '../lib/format'
import { signalHeadline } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import { Badge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

function ActionBadge({ action }) {
  const a = action || ''
  if (a.startsWith('BUY')) return <Badge tone="pos" title={a}>Buy RE</Badge>
  if (a.startsWith('RE rich')) return <Badge tone="warn" title={a}>RE rich</Badge>
  if (!a) return '—'
  return <Badge tone="neutral" title={a}>{a.split(':')[0].replace(/^\w/, (c) => c.toUpperCase())}</Badge>
}

const withRelative = (iso) => iso
  ? <>{fmtDate(iso)} <span className="rel">{fmtRelative(iso)}</span></>
  : '—'

const COLUMNS = [
  { key: 'symbol', header: 'Company', render: (r) => <SymbolLink symbol={r.symbol} /> },
  { key: 'ratio', header: 'Ratio', nowrap: true, mono: true, render: (r) => r.payload.ratio },
  { key: 'issue_price', header: 'Issue price', align: 'right', render: (r) => fmtInr(r.payload.issue_price) },
  { key: 'stock', header: 'Stock', align: 'right', render: (r) => fmtInr(r.payload.stock) },
  { key: 're', header: 'RE', align: 'right', render: (r) => fmtInr(r.payload.re) },
  {
    key: 'gap', header: 'Gap', align: 'right', title: 'RE discount to (stock − issue price)',
    render: (r) => <span className={r.payload.action?.startsWith('BUY') ? 'tone-pos' : undefined}>{fmtPct(r.payload.gap, 2)}</span>,
  },
  { key: 'turnover', header: 'Turnover', align: 'right', render: (r) => fmtLakh(r.payload.turnover) },
  { key: 're_last_day', header: 'RE last day', nowrap: true, render: (r) => withRelative(r.payload.re_last_day) },
  { key: 'issue_close', header: 'Apply by', nowrap: true, render: (r) => fmtDate(r.payload.issue_close) },
  { key: 'action', header: 'Action', render: (r) => <ActionBadge action={r.payload.action} /> },
]

// rights_re: entitlements trading now, from the latest daily scan. Positive gap = RE cheaper
// than (stock − issue price).
export default function RightsPanel() {
  const { loading, error, data } = useLoad(() => latestScan('rights_re'), [])
  return (
    <Section id="rights" title="Rights entitlements trading" level={3}
             meta={data?.runAt ? `as of ${fmtDateTime(data.runAt)}` : null}
             info={`${signalHeadline('rights_re')}. Only worth it if you want the stock anyway.`}
             infoHref="#/signals">
      {loading ? <Loading label="Loading rights entitlements"><SkeletonTable rows={3} cols={8} /></Loading>
        : error ? <ErrorNote what="rights entitlements" message={error} />
        : <DataTable dense caption="Rights entitlements trading" columns={COLUMNS} rows={data.rows}
                     rowKey={(r) => r.id} emptyText="No rights entitlements trading right now." />}
    </Section>
  )
}
