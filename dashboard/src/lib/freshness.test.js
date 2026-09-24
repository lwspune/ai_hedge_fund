import { describe, expect, it } from 'vitest'
import { FRESHNESS_RULES, ageDays, freshnessItems, isStale } from './freshness'

const NOW = new Date('2026-09-24T12:00:00Z') // 17:30 IST, 24 Sep

describe('freshness rules mirror scripts/check_freshness.py', () => {
  it('uses the same max ages', () => {
    expect(FRESHNESS_RULES).toEqual({ deals: 6, filings: 5, buybackScan: 2, rightsScan: 2 })
  })
})

describe('ageDays', () => {
  it('counts IST calendar days', () => {
    expect(ageDays('2026-09-24', NOW)).toBe(0)
    expect(ageDays('2026-09-18', NOW)).toBe(6)
    // 20:00 UTC on 23 Sep is already 24 Sep in IST
    expect(ageDays('2026-09-23T20:00:00Z', NOW)).toBe(0)
  })
})

describe('isStale', () => {
  it('is fresh at exactly the max age (check_freshness uses >)', () => {
    expect(isStale('deals', '2026-09-18', NOW)).toBe(false)
    expect(isStale('filings', '2026-09-19T10:00:00Z', NOW)).toBe(false)
    expect(isStale('buybackScan', '2026-09-22T10:00:00Z', NOW)).toBe(false)
  })
  it('is stale one day past the max age', () => {
    expect(isStale('deals', '2026-09-17', NOW)).toBe(true)
    expect(isStale('filings', '2026-09-18T10:00:00Z', NOW)).toBe(true)
    expect(isStale('rightsScan', '2026-09-21T10:00:00Z', NOW)).toBe(true)
  })
  it('treats a missing row as stale', () => {
    expect(isStale('deals', null, NOW)).toBe(true)
  })
})

describe('freshnessItems', () => {
  const latest = {
    deals: '2026-09-24',
    buybackScan: '2026-09-24T10:00:00Z',
    rightsScan: '2026-09-20T10:00:00Z',
    filings: null,
  }
  it('builds the status strip in order, flagging stale sources', () => {
    expect(freshnessItems(latest, NOW)).toEqual([
      { key: 'deals', label: 'Deals', text: '24 Sep', stale: false },
      { key: 'buybackScan', label: 'Buyback scan', text: '2 h ago', stale: false },
      { key: 'rightsScan', label: 'Rights scan', text: '4 d ago', stale: true },
      { key: 'filings', label: 'Filings', text: 'none', stale: true },
    ])
  })
})
