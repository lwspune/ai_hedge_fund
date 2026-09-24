import { describe, expect, it } from 'vitest'
import {
  dash, fmtAgo, fmtCr, fmtCrValue, fmtDate, fmtDateTime, fmtInr, fmtLakh, fmtNum, fmtPct,
  fmtPctPts, fmtQty, fmtRelative,
} from './format'

const TODAY = '2026-09-24'

describe('null handling', () => {
  it.each([
    ['fmtDate', fmtDate], ['fmtDateTime', fmtDateTime], ['fmtRelative', fmtRelative],
    ['fmtPct', fmtPct], ['fmtPctPts', fmtPctPts], ['fmtInr', fmtInr], ['fmtCr', fmtCr],
    ['fmtCrValue', fmtCrValue], ['fmtLakh', fmtLakh], ['fmtQty', fmtQty], ['fmtNum', fmtNum],
    ['fmtAgo', fmtAgo],
  ])('%s returns a dash for null, undefined and NaN', (_, fn) => {
    expect(fn(null)).toBe('—')
    expect(fn(undefined)).toBe('—')
    expect(fn(NaN)).toBe('—')
  })

  it('dash applies the formatter only to real values', () => {
    expect(dash(null, (v) => `x${v}`)).toBe('—')
    expect(dash(0, (v) => `x${v}`)).toBe('x0')
  })
})

describe('fmtDate', () => {
  it('omits the year in the current year', () => {
    expect(fmtDate('2026-09-24', TODAY)).toBe('24 Sep')
    expect(fmtDate('2026-01-05', TODAY)).toBe('5 Jan')
  })
  it('shows the year otherwise', () => {
    expect(fmtDate('2025-09-24', TODAY)).toBe('24 Sep 2025')
  })
  it('reads a timestamp as its IST calendar date', () => {
    // 20:00 UTC on 23 Sep is 01:30 IST on 24 Sep
    expect(fmtDate('2026-09-23T20:00:00+00:00', TODAY)).toBe('24 Sep')
  })
})

describe('fmtDateTime', () => {
  it('converts UTC to IST explicitly', () => {
    expect(fmtDateTime('2026-09-24T10:30:00+00:00', TODAY)).toBe('24 Sep, 16:00 IST')
    expect(fmtDateTime('2026-09-24T10:30:00Z', TODAY)).toBe('24 Sep, 16:00 IST')
  })
  it('crosses midnight into the next IST day', () => {
    expect(fmtDateTime('2026-09-23T20:00:00Z', TODAY)).toBe('24 Sep, 01:30 IST')
  })
  it('adds the year outside the current year', () => {
    expect(fmtDateTime('2025-12-31T06:30:00Z', TODAY)).toBe('31 Dec 2025, 12:00 IST')
  })
})

describe('fmtRelative', () => {
  it.each([
    ['2026-09-24', 'today'],
    ['2026-09-25', 'tomorrow'],
    ['2026-09-23', 'yesterday'],
    ['2026-09-30', 'in 6 d'],
    ['2026-09-21', '3 d ago'],
    ['2026-10-15', 'in 21 d'],
    ['2026-10-16', 'in 3 wk'],
    ['2026-10-29', 'in 5 wk'],
    ['2026-08-20', '5 wk ago'],
  ])('%s -> %s', (iso, want) => {
    expect(fmtRelative(iso, TODAY)).toBe(want)
  })
  it('uses the IST date of a timestamp', () => {
    expect(fmtRelative('2026-09-23T20:00:00Z', TODAY)).toBe('today')
  })
})

describe('fmtAgo', () => {
  const now = new Date('2026-09-24T12:00:00Z')
  it.each([
    ['2026-09-24T11:59:30Z', 'just now'],
    ['2026-09-24T11:20:00Z', '40 min ago'],
    ['2026-09-24T10:00:00Z', '2 h ago'],
    ['2026-09-22T10:00:00Z', '2 d ago'],
  ])('%s -> %s', (iso, want) => {
    expect(fmtAgo(iso, now)).toBe(want)
  })
})

describe('percentages', () => {
  it('fmtPct takes a fraction', () => {
    expect(fmtPct(0.034)).toBe('3.4%')
    expect(fmtPct(0.034, 2)).toBe('3.40%')
    expect(fmtPct(0.5, 0)).toBe('50%')
    expect(fmtPct(0)).toBe('0.0%')
  })
  it('shows a sign for negatives only', () => {
    expect(fmtPct(-0.0125, 2)).toBe('−1.25%')
    expect(fmtPct(0.0125, 2)).toBe('1.25%')
  })
  it('fmtPctPts takes a value already in percent', () => {
    expect(fmtPctPts(3.4)).toBe('3.4%')
    expect(fmtPctPts(-2.25, 2)).toBe('−2.25%')
  })
})

describe('money and quantities', () => {
  it('fmtInr groups en-IN with fixed decimals', () => {
    expect(fmtInr(1234.5)).toBe('₹1,234.50')
    expect(fmtInr(1234567.891)).toBe('₹12,34,567.89')
    expect(fmtInr(200000, 0)).toBe('₹2,00,000')
    expect(fmtInr(-12.5)).toBe('−₹12.50')
  })
  it('fmtCr converts rupees to crore', () => {
    expect(fmtCr(12_345_678)).toBe('₹1.23 cr')
    expect(fmtCr(12_345_678_901)).toBe('₹1,235 cr')
  })
  it('fmtCrValue takes crore', () => {
    expect(fmtCrValue(1234)).toBe('₹1,234 cr')
    expect(fmtCrValue(123456.4)).toBe('₹1,23,456 cr')
    expect(fmtCrValue(12.345)).toBe('₹12.35 cr')
  })
  it('fmtLakh converts rupees to lakh', () => {
    expect(fmtLakh(1_230_000)).toBe('12.3 L')
  })
  it('fmtQty groups en-IN integers', () => {
    expect(fmtQty(1234567)).toBe('12,34,567')
    expect(fmtQty(0)).toBe('0')
  })
  it('fmtNum groups with at most dp decimals', () => {
    expect(fmtNum(1234.5678, 2)).toBe('1,234.57')
    expect(fmtNum(12)).toBe('12')
    expect(fmtNum(-3.5, 1)).toBe('−3.5')
  })
})
