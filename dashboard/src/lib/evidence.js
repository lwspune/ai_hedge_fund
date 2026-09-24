// Validation evidence (DATA_INFRA_SPEC WP7): `validation_runs` indexes the artefacts each published
// validation run stored in the private `evidence` bucket. The dashboard shows the latest per signal.

export function latestEvidence(rows) {
  const out = {}
  for (const r of rows || []) {
    const cur = out[r.signal_name]
    if (!cur || r.run_at > cur.run_at) out[r.signal_name] = r
  }
  return out
}

export function evidenceLabel(run) {
  if (!run) return ''
  const sha = run.git_sha ? ` · sha ${run.git_sha.slice(0, 7)}` : ''
  return `evidence/${run.evidence_path}${sha}`
}
