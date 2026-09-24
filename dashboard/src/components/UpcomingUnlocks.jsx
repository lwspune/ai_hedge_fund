import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import { addDaysIso, fmtDate, fmtQty, fmtRelative, todayIso } from '../lib/format'
import { signalHeadline } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import SymbolLink from './ui/SymbolLink'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const DAYS = 14

const COLUMNS = [
  {
    key: 'event_date', header: 'Date', nowrap: true,
    render: (r) => <>{fmtDate(r.event_date)} <span className="rel">{fmtRelative(r.event_date)}</span></>,
  },
  { key: 'symbol', header: 'Company', render: (r) => <SymbolLink symbol={r.symbol} /> },
  { key: 'event_type', header: 'Unlock', nowrap: true, render: (r) => (r.event_type === 'anchor_lockin_90' ? 'Rest at 90 d' : '50% at 30 d') },
  { key: 'board', header: 'Board', render: (r) => (r.details?.board === 'sme' ? 'SME' : r.details?.board ? 'Mainboard' : null) },
  { key: 'anchor_shares', header: 'Anchor shares', align: 'right', render: (r) => fmtQty(r.details?.anchor_shares) },
]

// lockin_expiry lens: anchor lock-in expiries coming up. The dip is real but not shortable, so
// this is an avoid / exit list.
export default function UpcomingUnlocks() {
  const { loading, error, data } = useLoad(() => {
    const today = todayIso()
    return supabase.from('corporate_events')
      .select('id,symbol,event_type,event_date,details')
      .in('event_type', ['anchor_lockin_30', 'anchor_lockin_90'])
      .gte('event_date', today).lte('event_date', addDaysIso(today, DAYS))
      .order('event_date').order('symbol')
  }, [])

  return (
    <Section id="unlocks" title={`Anchor unlocks, next ${DAYS} days`} level={3}
             info={`${signalHeadline('lockin_expiry')}. Avoid buying into it; consider exiting a recent IPO before T−1.`}
             infoHref="#/signals">
      {loading ? <Loading label="Loading anchor unlocks"><SkeletonTable rows={3} cols={5} /></Loading>
        : error ? <ErrorNote what="anchor unlocks" message={error} />
        : <DataTable dense maxHeight="22rem" caption="Anchor unlocks" columns={COLUMNS} rows={data} rowKey={(r) => r.id}
                     emptyText={`No anchor lock-in expiries in the next ${DAYS} days.`} />}
    </Section>
  )
}
