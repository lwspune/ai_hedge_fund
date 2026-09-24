import { useState } from 'react'
import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import useEdgeRefresh, { describeBuybackRefresh } from '../lib/useEdgeRefresh'
import { fmtCrValue, fmtDate, fmtInr, fmtPct } from '../lib/format'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import Button from './ui/Button'
import Chips from './ui/Chips'
import { toggle } from '../lib/filters'
import { StatusBadge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const COLUMNS = [
  { key: 'symbol', header: 'Company', sortable: true, render: (b) => <SymbolLink symbol={b.symbol} name={b.company} /> },
  { key: 'buyback_price', header: 'Buyback price', align: 'right', sortable: true, render: (b) => fmtInr(b.buyback_price) },
  { key: 'entitlement_small', header: 'Entitlement', align: 'right', sortable: true, render: (b) => fmtPct(b.entitlement_small, 0) },
  { key: 'issue_size_cr', header: 'Issue size', align: 'right', sortable: true, render: (b) => fmtCrValue(b.issue_size_cr) },
  { key: 'est_return', header: 'Floor est.', align: 'right', sortable: true, render: (b) => fmtPct(b.est_return) },
  { key: 'record_date', header: 'Record date', nowrap: true, sortable: true, render: (b) => fmtDate(b.record_date) },
  { key: 'close_date', header: 'Close date', nowrap: true, sortable: true, render: (b) => fmtDate(b.close_date) },
  { key: 'status', header: 'Status', render: (b) => <StatusBadge status={b.status} /> },
]

// Every stored buyback (the user's lifecycle table). Status is set by the track CLI.
const STATUSES = [['open', 'Open'], ['tendered', 'Tendered'], ['settled', 'Settled'], ['skipped', 'Skipped']]

export default function BuybackTable() {
  const [statuses, setStatuses] = useState(() => new Set())
  const { loading, error, data, reload } = useLoad(() => supabase.from('buybacks').select('*')
    .order('record_date', { ascending: false, nullsFirst: false }).limit(200), [])
  const r = useEdgeRefresh('refresh-buybacks', describeBuybackRefresh, reload)
  const rows = (data || []).filter((b) => statuses.size === 0 || statuses.has(b.status))

  return (
    <Section id="buybacks" title="Buybacks"
             info="Floor est. = guaranteed-acceptance return before tax; after-tax ranking is on the Desk."
             status={r.status}
             action={<Button busy={r.busy} onClick={r.refresh}
                             aria-label="Refresh buybacks from chittorgarh">Refresh</Button>}>
      {r.error && <ErrorNote what="new buybacks" message={r.error} />}
      <div className="chips">
        <Chips label="Status" options={STATUSES} selected={statuses}
               onToggle={(v) => setStatuses((s) => toggle(s, v))} />
      </div>
      {loading && !data ? <Loading label="Loading buybacks"><SkeletonTable rows={6} cols={8} /></Loading>
        : error ? <ErrorNote what="buybacks" message={error} />
        : <DataTable maxHeight="70vh" caption="Buybacks" columns={COLUMNS} rows={rows} rowKey={(b) => b.id}
                     emptyText={data?.length ? 'No buybacks with this status.' : 'No buybacks stored.'}
                     emptyHint={<>Run <code>python -m scanner.run buyback_arb --save</code></>} />}
    </Section>
  )
}
