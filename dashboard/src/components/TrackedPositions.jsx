import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import { fmtDate, fmtInr, fmtPct, fmtQty } from '../lib/format'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const outcome = (t) => (t.outcomes && t.outcomes[0]) || {}

const COLUMNS = [
  { key: 'symbol', header: 'Company', render: (t) => <SymbolLink symbol={t.buybacks?.symbol} name={t.buybacks?.company} /> },
  { key: 'decided_on', header: 'Decided', nowrap: true, sortable: true, render: (t) => fmtDate(t.decided_on) },
  { key: 'shares_bought', header: 'Shares', align: 'right', render: (t) => fmtQty(t.shares_bought) },
  { key: 'capital', header: 'Capital', align: 'right', sortable: true, render: (t) => fmtInr(t.capital, 0) },
  { key: 'accepted', header: 'Accepted', align: 'right', render: (t) => fmtQty(outcome(t).accepted_shares) },
  { key: 'acc', header: 'Realised acceptance', align: 'right', render: (t) => fmtPct(outcome(t).realized_acceptance) },
  {
    key: 'ret', header: 'Realised return', align: 'right', sortable: true,
    sortValue: (t) => outcome(t).realized_return,
    render: (t) => {
      const v = outcome(t).realized_return
      return <span className={v > 0 ? 'tone-pos' : v < 0 ? 'tone-neg' : undefined}>{fmtPct(v)}</span>
    },
  },
]

export default function TrackedPositions() {
  const { loading, error, data } = useLoad(() => supabase.from('tenders')
    .select('*, buybacks(symbol,company), outcomes(accepted_shares,realized_acceptance,realized_return)')
    .order('decided_on', { ascending: false }), [])
  return (
    <Section id="positions" title="Positions"
             info="Tenders you recorded and their outcomes; realised acceptance vs the floor calibrates the acceptance model.">
      {loading ? <Loading label="Loading positions"><SkeletonTable rows={3} cols={7} /></Loading>
        : error ? <ErrorNote what="positions" message={error} />
        : <DataTable caption="Positions" columns={COLUMNS} rows={data} rowKey={(t) => t.id}
                     emptyText="No tenders recorded."
                     emptyHint={<>Record one with <code>python -m scanner.track tender …</code></>} />}
    </Section>
  )
}
