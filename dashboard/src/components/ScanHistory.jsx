import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import { fmtDateTime, fmtQty } from '../lib/format'
import { signalLabel } from '../lib/signalLabels'
import Section from './ui/Section'
import DataTable from './ui/DataTable'
import { VerdictBadge } from './ui/Badge'
import { ErrorNote } from './ui/States'
import { Loading, SkeletonTable } from './ui/Skeleton'

const COLUMNS = [
  { key: 'signal_name', header: 'Signal', sortable: true, sortValue: (r) => signalLabel(r.signal_name), render: (r) => signalLabel(r.signal_name) },
  { key: 'verdict', header: 'Verdict', render: (r) => <VerdictBadge verdict={r.verdict} /> },
  { key: 'n_candidates', header: 'Candidates', align: 'right', sortable: true, render: (r) => fmtQty(r.n_candidates) },
  { key: 'run_at', header: 'Run at', nowrap: true, sortable: true, render: (r) => fmtDateTime(r.run_at) },
]

export default function ScanHistory() {
  const { loading, error, data } = useLoad(() => supabase.from('scan_runs').select('*')
    .order('run_at', { ascending: false }).limit(100), [])
  return (
    <Section id="scans" title="Scans" info="Every saved scanner run, with the signal's verdict at run time.">
      {loading ? <Loading label="Loading scans"><SkeletonTable rows={6} cols={4} /></Loading>
        : error ? <ErrorNote what="scans" message={error} />
        : <DataTable dense caption="Scans" columns={COLUMNS} rows={data} rowKey={(r) => r.id}
                     emptyText="No scans recorded yet." />}
    </Section>
  )
}
