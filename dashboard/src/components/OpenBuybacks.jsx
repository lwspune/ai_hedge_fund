import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import useEdgeRefresh, { describeBuybackRefresh } from '../lib/useEdgeRefresh'
import { latestScan } from '../lib/queries'
import { fmtDate, fmtDateTime, fmtInr, fmtPct, fmtRelative } from '../lib/format'
import { signalHeadline } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import Button from './ui/Button'
import { StatusBadge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const GOOD = 0.02

// chittorgarh titles read "Nectar Lifesciences Buyback 2025"; the year suffix is noise here.
const companyName = (s) => (s || '').replace(/\s+buyback(\s+\d{4})?$/i, '')

// Open = payload.is_open from the latest buyback_arb scan (not buybacks.status, which is the
// user's lifecycle field). Company + status come from the buybacks table.
async function loadOpenBuybacks() {
  const { runAt, rows } = await latestScan('buyback_arb')
  const open = rows.filter((r) => r.payload?.is_open === true)
  if (!open.length) return { runAt, rows: [] }
  const bb = await supabase.from('buybacks').select('symbol,company,status,record_date')
    .in('symbol', [...new Set(open.map((r) => r.symbol))])
    .order('record_date', { ascending: false, nullsFirst: false })
  if (bb.error) throw bb.error
  const bySym = {}
  for (const b of bb.data || []) bySym[b.symbol] ??= b
  return { runAt, rows: open.map((r) => ({ ...r, buyback: bySym[r.symbol] })) }
}

const p = (r) => r.payload

const COLUMNS = [
  { key: 'symbol', header: 'Company', render: (r) => <SymbolLink symbol={r.symbol} name={companyName(r.buyback?.company)} /> },
  { key: 'cur_price', header: 'Price', align: 'right', render: (r) => fmtInr(p(r).cur_price) },
  { key: 'buyback_price', header: 'Buyback', align: 'right', render: (r) => fmtInr(p(r).buyback_price) },
  { key: 'premium', header: 'Premium', align: 'right', sortable: true, sortValue: (r) => p(r).premium, render: (r) => fmtPct(p(r).premium) },
  {
    key: 'entitlement', header: 'Entitlement', align: 'right', title: '~ = estimated from the small-holder float; the letter of offer is not out yet',
    render: (r) => p(r).entitlement_small != null ? fmtPct(p(r).entitlement_small, 0)
      : p(r).est_entitlement != null ? `${fmtPct(p(r).est_entitlement, 0)}~` : fmtPct(null),
  },
  { key: 'acceptance', header: 'Est. acceptance', align: 'right', render: (r) => fmtPct(p(r).est_acceptance, 0) },
  {
    key: 'exp_return', header: 'After-tax est.', align: 'right', sortable: true, title: 'At the 30% slab; see Signals',
    sortValue: (r) => p(r).exp_return,
    render: (r) => <span className={p(r).exp_return > GOOD ? 'tone-pos' : undefined}>{fmtPct(p(r).exp_return)}</span>,
  },
  {
    key: 'last_buy_date', header: 'Buy by', nowrap: true, sortable: true, sortValue: (r) => p(r).last_buy_date,
    title: 'Last trading day before the record date; the record date itself is ex-entitlement',
    render: (r) => <>{fmtDate(p(r).last_buy_date)} <span className="rel">{fmtRelative(p(r).last_buy_date)}</span></>,
  },
  {
    key: 'record_date', header: 'Record date', nowrap: true, sortable: true, sortValue: (r) => p(r).record_date,
    render: (r) => fmtDate(p(r).record_date),
  },
  { key: 'close_date', header: 'Closes', nowrap: true, render: (r) => fmtDate(p(r).close_date) },
  { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.buyback?.status} /> },
]

export default function OpenBuybacks() {
  const { loading, error, data, reload } = useLoad(loadOpenBuybacks, [])
  const r = useEdgeRefresh('refresh-buybacks', describeBuybackRefresh, reload)
  return (
    <Section id="open-buybacks" title="Open buybacks" level={3}
             meta={data?.runAt ? `as of ${fmtDateTime(data.runAt)}` : null}
             info={`${signalHeadline('buyback_arb')}. After-tax estimate shown at the 30% slab.`}
             infoHref="#/signals" status={r.status}
             action={<Button busy={r.busy} onClick={r.refresh}
                             aria-label="Refresh buybacks from chittorgarh">Refresh</Button>}>
      {r.error && <ErrorNote what="new buybacks" message={r.error} />}
      {loading && !data ? <Loading label="Loading open buybacks"><SkeletonTable rows={3} cols={10} /></Loading>
        : error ? <ErrorNote what="open buybacks" message={error} />
        : <DataTable dense caption="Open buybacks" columns={COLUMNS} rows={data.rows} rowKey={(x) => x.id}
                     emptyText="No open tender buybacks."
                     emptyHint={<>Run <code>python -m scanner.run buyback_arb --save</code></>} />}
    </Section>
  )
}
