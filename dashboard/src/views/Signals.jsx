import { useState } from 'react'
import { supabase } from '../supabaseClient'
import signals from '../signals.json'
import useLoad from '../lib/useLoad'
import { fmtAgo, fmtDate, fmtDateTime, fmtQty } from '../lib/format'
import { evidenceLabel, latestEvidence } from '../lib/evidence'
import { ROLE_ORDER, roleLabel, signalHeadline, signalLabel, typeLabel } from '../lib/signalLabels'
import DataTable from '../components/ui/DataTable'
import { Badge, VerdictBadge } from '../components/ui/Badge'
import { ErrorNote } from '../components/ui/States'

const ROWS = [...signals].sort((a, b) =>
  (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9) || a.name.localeCompare(b.name))

const RUN_COLUMNS = [
  { key: 'run_at', header: 'Run at', nowrap: true, render: (r) => fmtDateTime(r.run_at) },
  { key: 'verdict', header: 'Verdict then', render: (r) => <VerdictBadge verdict={r.verdict} /> },
  { key: 'n_candidates', header: 'Candidates', align: 'right', render: (r) => fmtQty(r.n_candidates) },
]

function Chevron() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
      <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function Signals() {
  const [open, setOpen] = useState(() => new Set())
  const runs = useLoad(() => supabase.from('scan_runs').select('id,signal_name,verdict,run_at,n_candidates')
    .order('run_at', { ascending: false }).limit(200), [])
  const validations = useLoad(() => supabase.from('validation_runs').select('signal_name,run_at,git_sha,evidence_path')
    .order('run_at', { ascending: false }).limit(200), [])
  const evidence = latestEvidence(validations.data)

  const bySignal = {}
  for (const r of runs.data || []) (bySignal[r.signal_name] ??= []).push(r)

  const toggle = (name) => setOpen((s) => {
    const next = new Set(s)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    return next
  })

  const columns = [
    {
      key: 'name', header: 'Signal',
      render: (s) => (
        <span className="sig-cell">
          <button type="button" className="rowlink-btn" aria-expanded={open.has(s.name)}
                  aria-controls={open.has(s.name) ? `sig-${s.name}-more` : undefined} aria-label={`Details for ${signalLabel(s.name)}`}
                  onClick={() => toggle(s.name)}>
            <Chevron />
          </button>
          <span>
            <span className="sig-label">{signalLabel(s.name)}</span>
            <span className="cell-sub mono">{s.name}</span>
          </span>
        </span>
      ),
    },
    { key: 'verdict', header: 'Verdict', render: (s) => <VerdictBadge verdict={s.verdict} /> },
    { key: 'role', header: 'Role', render: (s) => <Badge tone={s.role === 'primary' ? 'pos' : 'neutral'}>{roleLabel(s.role)}</Badge> },
    { key: 'type', header: 'Type', render: (s) => <span className="t2">{typeLabel(s.type)}</span> },
    { key: 'finding', header: 'Finding', render: (s) => <span className="t2 cell-wrap">{signalHeadline(s.name)}</span> },
    {
      key: 'last', header: 'Last run', nowrap: true,
      render: (s) => {
        if (runs.loading) return <span className="sk" style={{ width: 80 }} aria-hidden="true" />
        const last = bySignal[s.name]?.[0]
        return last ? <span className="t2">{fmtAgo(last.run_at)} · {fmtQty(last.n_candidates)} found</span> : '—'
      },
    },
  ]

  return (
    <>
      <h1 className="page-title">Signals</h1>
      <p className="page-lede">
        Every signal carries the verdict its event study produced. Falsified signals stay as lenses and are
        never traded.
      </p>
      {runs.error && <ErrorNote what="scan runs" message={runs.error} />}
      {validations.error && <ErrorNote what="validation runs" message={validations.error} />}
      <div className="stack-top">
        <DataTable caption="Signals and their verdicts" columns={columns} rows={ROWS} rowKey={(s) => s.name}
                   expandedRow={(s) => open.has(s.name)}
                   renderExpanded={(s) => (
                     <div id={`sig-${s.name}-more`} className="sig-more">
                       <p className="sig-summary">{s.summary}</p>
                       <h3 className="subhead">Evidence</h3>
                       <p className="t2">
                         {evidence[s.name]
                           ? <><span className="mono">{evidenceLabel(evidence[s.name])}</span> · validated {fmtDate(evidence[s.name].run_at)}</>
                           : 'No published validation run yet (run the validate workflow).'}
                       </p>
                       <h3 className="subhead">Recent runs</h3>
                       <DataTable dense caption={`Recent runs of ${signalLabel(s.name)}`} columns={RUN_COLUMNS}
                                  rows={(bySignal[s.name] || []).slice(0, 10)} rowKey={(r) => r.id}
                                  emptyText="Never run as a saved scan." />
                     </div>
                   )} />
      </div>
    </>
  )
}
