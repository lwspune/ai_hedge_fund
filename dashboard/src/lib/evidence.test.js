import { describe, expect, it } from 'vitest'
import { evidenceLabel, latestEvidence } from './evidence'

describe('latestEvidence', () => {
  it('keeps the newest validation run per signal', () => {
    const rows = [
      { signal_name: 'rights_re', run_at: '2026-09-24T10:00:00Z', evidence_path: 'rights_re/2026-09-24', git_sha: 'abc1234def' },
      { signal_name: 'rights_re', run_at: '2026-09-01T10:00:00Z', evidence_path: 'rights_re/2026-09-01', git_sha: 'old' },
      { signal_name: 'fno_ban', run_at: '2026-09-02T10:00:00Z', evidence_path: 'fno_ban/2026-09-02', git_sha: null },
    ]
    const got = latestEvidence(rows)
    expect(got.rights_re.evidence_path).toBe('rights_re/2026-09-24')
    expect(got.fno_ban.evidence_path).toBe('fno_ban/2026-09-02')
  })

  it('is empty for no rows', () => {
    expect(latestEvidence(null)).toEqual({})
  })
})

describe('evidenceLabel', () => {
  it('shows bucket path and short sha', () => {
    expect(evidenceLabel({ evidence_path: 'rights_re/2026-09-24', git_sha: 'abc1234def' }))
      .toBe('evidence/rights_re/2026-09-24 · sha abc1234')
    expect(evidenceLabel({ evidence_path: 'x/2026-01-01', git_sha: null })).toBe('evidence/x/2026-01-01')
    expect(evidenceLabel(undefined)).toBe('')
  })
})
