import { describe, expect, it } from 'vitest'
import { companyHref, dataHref, parseHash } from './useHashRoute'

describe('parseHash', () => {
  it.each([
    ['', { page: 'desk' }],
    ['#', { page: 'desk' }],
    ['#/', { page: 'desk' }],
    ['#/nope', { page: 'desk' }],
    ['#/signals', { page: 'signals' }],
    ['#/data', { page: 'data', tab: 'deals' }],
    ['#/data/deals', { page: 'data', tab: 'deals' }],
    ['#/data/buybacks', { page: 'data', tab: 'buybacks' }],
    ['#/data/positions', { page: 'data', tab: 'positions' }],
    ['#/data/scans', { page: 'data', tab: 'scans' }],
    ['#/data/bogus', { page: 'data', tab: 'deals' }],
    ['#/company/TCS', { page: 'company', symbol: 'TCS', tab: 'overview' }],
    ['#/company/TCS/overview', { page: 'company', symbol: 'TCS', tab: 'overview' }],
    ['#/company/TCS/financials', { page: 'company', symbol: 'TCS', tab: 'financials' }],
    ['#/company/TCS/events', { page: 'company', symbol: 'TCS', tab: 'events' }],
    ['#/company/TCS/filings', { page: 'company', symbol: 'TCS', tab: 'filings' }],
    ['#/company/TCS/deals', { page: 'company', symbol: 'TCS', tab: 'deals' }],
    ['#/company/TCS/bogus', { page: 'company', symbol: 'TCS', tab: 'overview' }],
    ['#/company/tcs', { page: 'company', symbol: 'TCS', tab: 'overview' }],
  ])('%s', (hash, want) => {
    expect(parseHash(hash)).toEqual(want)
  })

  it('decodes encoded symbols', () => {
    expect(parseHash('#/company/M%26M')).toEqual({ page: 'company', symbol: 'M&M', tab: 'overview' })
    expect(parseHash('#/company/BAJAJ-AUTO/events')).toEqual({ page: 'company', symbol: 'BAJAJ-AUTO', tab: 'events' })
  })

  it('sends invalid symbols to the desk', () => {
    expect(parseHash('#/company/<script>')).toEqual({ page: 'desk' })
    expect(parseHash('#/company/A%20B')).toEqual({ page: 'desk' })
    expect(parseHash('#/company/%E0%A4')).toEqual({ page: 'desk' })
    expect(parseHash(`#/company/${'X'.repeat(21)}`)).toEqual({ page: 'desk' })
  })
})

describe('hrefs', () => {
  it('round-trips through parseHash', () => {
    expect(parseHash(companyHref('M&M', 'filings'))).toEqual({ page: 'company', symbol: 'M&M', tab: 'filings' })
    expect(companyHref('TCS')).toBe('#/company/TCS')
    expect(dataHref('scans')).toBe('#/data/scans')
  })
})
