import { useState } from 'react'
import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import useEdgeRefresh, { describeDealsRefresh } from '../lib/useEdgeRefresh'
import { filterDeals, toggle } from '../lib/filters'
import { fmtCr, fmtDate, fmtInr, fmtQty } from '../lib/format'
import { signalHeadline } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import Button from './ui/Button'
import Chips from './ui/Chips'
import { SideBadge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const LIMIT = 300

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
  const [sides, setSides] = useState(() => new Set())
  const [kinds, setKinds] = useState(() => new Set())
  const [symbol, setSymbol] = useState('')
  const { loading, error, data, reload } = useLoad(() => supabase.from('market_deals').select('*')
    .order('deal_date', { ascending: false }).order('value', { ascending: false, nullsFirst: false })
    .limit(LIMIT), [])
  const r = useEdgeRefresh('refresh-deals', describeDealsRefresh, reload)
  const rows = data ? filterDeals(data, { sides, kinds, symbol }) : []

  return (
    <Section id="deals" title="Bulk and block deals" status={r.status}
             meta={data ? `latest ${data.length}` : null}
             info={`Informational: ${signalHeadline('smart_money_deals').toLowerCase()}.`} infoHref="#/signals"
             action={<Button busy={r.busy} onClick={r.refresh} aria-label="Refresh deals from NSE">Refresh</Button>}>
      {r.error && <ErrorNote what="today’s deals" message={r.error} />}
      <div className="chips">
        <Chips label="Side" options={[['BUY', 'Buy'], ['SELL', 'Sell']]} selected={sides}
               onToggle={(v) => setSides((s) => toggle(s, v))} />
        <span className="chip-sep" aria-hidden="true" />
        <Chips label="Kind" options={[['bulk', 'Bulk'], ['block', 'Block']]} selected={kinds}
               onToggle={(v) => setKinds((s) => toggle(s, v))} />
        <label className="sr-only" htmlFor="deal-sym">Filter by symbol</label>
        <input id="deal-sym" className="filter-input" type="search" placeholder="Symbol starts with…"
               value={symbol} onChange={(e) => setSymbol(e.target.value)} autoComplete="off" spellCheck="false" />
      </div>
      {loading && !data ? <Loading label="Loading deals"><SkeletonTable rows={8} cols={8} /></Loading>
        : error ? <ErrorNote what="deals" message={error} />
        : (
          <>
            <DataTable dense maxHeight="70vh" caption="Bulk and block deals" columns={COLUMNS} rows={rows}
                       rowKey={(d) => d.id} emptyText={data.length ? 'No deals match these filters.' : 'No deals stored.'} />
            <p className="table-foot" aria-live="polite">Showing {fmtQty(rows.length)} of {fmtQty(data.length)}</p>
          </>
        )}
    </Section>
  )
}
