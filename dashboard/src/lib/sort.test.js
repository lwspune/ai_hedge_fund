import { describe, expect, it } from 'vitest'
import { compareValues, sortRows } from './sort'

describe('compareValues', () => {
  it('orders numbers numerically, not lexically', () => {
    expect([10, 9, 100].sort((a, b) => compareValues(a, b))).toEqual([9, 10, 100])
  })
  it('orders strings case-insensitively', () => {
    expect(['b', 'A', 'c'].sort((a, b) => compareValues(a, b))).toEqual(['A', 'b', 'c'])
  })
  it('orders ISO dates chronologically', () => {
    expect(['2026-09-01', '2025-12-31', '2026-01-15'].sort((a, b) => compareValues(a, b)))
      .toEqual(['2025-12-31', '2026-01-15', '2026-09-01'])
  })
})

describe('sortRows', () => {
  const rows = [{ v: 3 }, { v: null }, { v: 1 }, { v: undefined }, { v: 2 }]
  it('sorts ascending with nulls last', () => {
    expect(sortRows(rows, (r) => r.v, 'asc').map((r) => r.v)).toEqual([1, 2, 3, null, undefined])
  })
  it('sorts descending with nulls still last', () => {
    expect(sortRows(rows, (r) => r.v, 'desc').map((r) => r.v)).toEqual([3, 2, 1, null, undefined])
  })
  it('does not mutate the input', () => {
    const copy = [...rows]
    sortRows(rows, (r) => r.v, 'asc')
    expect(rows).toEqual(copy)
  })
  it('is stable for equal keys', () => {
    const r = [{ k: 1, id: 'a' }, { k: 1, id: 'b' }, { k: 0, id: 'c' }]
    expect(sortRows(r, (x) => x.k, 'asc').map((x) => x.id)).toEqual(['c', 'a', 'b'])
  })
})
