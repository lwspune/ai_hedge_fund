import { describe, expect, it } from 'vitest'
import { filterDeals, toggle } from './filters'

const D = [
  { id: 1, symbol: 'TCS', side: 'BUY', kind: 'bulk' },
  { id: 2, symbol: 'TATASTEEL', side: 'SELL', kind: 'block' },
  { id: 3, symbol: 'INFY', side: 'buy', kind: 'block' },
  { id: 4, symbol: 'M&M', side: 'SELL', kind: 'bulk' },
]
const ids = (rows) => rows.map((r) => r.id)

describe('filterDeals', () => {
  it('returns everything with no filters', () => {
    expect(ids(filterDeals(D, {}))).toEqual([1, 2, 3, 4])
    expect(ids(filterDeals(D, { sides: new Set(), kinds: new Set(), symbol: '' }))).toEqual([1, 2, 3, 4])
  })
  it('filters by side, case-insensitively', () => {
    expect(ids(filterDeals(D, { sides: new Set(['BUY']) }))).toEqual([1, 3])
  })
  it('filters by kind', () => {
    expect(ids(filterDeals(D, { kinds: new Set(['block']) }))).toEqual([2, 3])
  })
  it('filters by symbol prefix, case-insensitive and trimmed', () => {
    expect(ids(filterDeals(D, { symbol: ' ta ' }))).toEqual([2])
    expect(ids(filterDeals(D, { symbol: 'm&' }))).toEqual([4])
  })
  it('combines filters with AND', () => {
    expect(ids(filterDeals(D, { sides: new Set(['SELL']), kinds: new Set(['bulk']) }))).toEqual([4])
  })
})

describe('toggle', () => {
  it('adds and removes without mutating', () => {
    const a = new Set(['x'])
    const b = toggle(a, 'y')
    expect([...b]).toEqual(['x', 'y'])
    expect([...toggle(b, 'x')]).toEqual(['y'])
    expect([...a]).toEqual(['x'])
  })
})
