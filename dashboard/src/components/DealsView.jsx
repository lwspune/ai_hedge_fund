import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import useEdgeRefresh, { describeDealsRefresh } from '../lib/useEdgeRefresh'
import { fmtCr, fmtDate, fmtInr, fmtQty } from '../lib/format'
import { signalHeadline } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import Button from './ui/Button'
import { SideBadge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const COLUMNS = [
  { key: 'deal_date', header: 'Date', nowrap: true, sortable: true, render: (d) => fmtDate(d.deal_date) },
  { key: 'symbol', header: 'Company', render: (d) => <SymbolLink symbol={d.symbol} /> },
  { key: 'client', header: 'Client', render: (d) => <span className="cell-clip" title={d.client}>{d.client}</span> },
  { key: 'side', header: 'Side', render: (d) => <SideBadge side={d.side} /> },
  { key: 'qty', header: 'Qty', align: 'right', sortable: true, render: (d) => fmtQty(d.qty) },
  { key: 'price', header: 'Price', align: 'right', render: (d) => fmtInr(d.price) },
  { key: 'value', header: 'Value', align: 'right', sortable: true, render: (d) => fmtCr(d.value) },
  { key: 'kind', header: 'Kind', render: (d) => (d.kind ? d.kind[0].toUpperCase() + d.kind.slice(1) : null) },
]

export default function DealsView() {
  const { loading, error, data, reload } = useLoad(() => supabase.from('market_deals').select('*')
    .order('deal_date', { ascending: false }).order('value', { ascending: false, nullsFirst: false })
    .limit(60), [])
  const r = useEdgeRefresh('refresh-deals', describeDealsRefresh, reload)

  return (
    <Section id="deals" title="Bulk and block deals" status={r.status}
             info={`Informational: ${signalHeadline('smart_money_deals').toLowerCase()}.`} infoHref="#/signals"
             action={<Button busy={r.busy} onClick={r.refresh} aria-label="Refresh deals from NSE">Refresh</Button>}>
      {r.error && <ErrorNote what="today’s deals" message={r.error} />}
      {loading && !data ? <Loading label="Loading deals"><SkeletonTable rows={8} cols={8} /></Loading>
        : error ? <ErrorNote what="deals" message={error} />
        : <DataTable dense caption="Bulk and block deals" columns={COLUMNS} rows={data}
                     rowKey={(d) => d.id} emptyText="No deals stored." />}
    </Section>
  )
}
