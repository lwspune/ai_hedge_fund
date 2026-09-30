import { describe, expect, it } from 'vitest'
import { RISK_FLAGS, blanksPriceMetrics, flagLabel, fmtDaysToExit, fmtRank, riskChip } from './risk'

// The Python flags (scanner/risk.py FLAGS). A new flag there must get a label here.
const PY_FLAGS = ['short_history', 'sparse', 'action_unverified', 'price_break', 'illiquid', 'sme', 'asm', 'gsm']

describe('flagLabel', () => {
  it('labels every flag the loader can write', () => {
    expect([...RISK_FLAGS].sort()).toEqual([...PY_FLAGS].sort())
    for (const f of RISK_FLAGS) {
      expect(flagLabel(f), f).toMatch(/\w/)
      expect(flagLabel(f), f).not.toBe(f)
    }
  })

  it('passes an unknown flag through rather than hiding it', () => {
    expect(flagLabel('new_thing')).toBe('new_thing')
  })

  it('knows which flags blank the price metrics', () => {
    expect(blanksPriceMetrics(['action_unverified'])).toBe(true)
    expect(blanksPriceMetrics(['price_break', 'sme'])).toBe(true)
    expect(blanksPriceMetrics(['illiquid'])).toBe(false)
    expect(blanksPriceMetrics(null)).toBe(false)
  })
})

describe('fmtDaysToExit', () => {
  it('pluralises and dashes', () => {
    expect(fmtDaysToExit(1)).toBe('1 day')
    expect(fmtDaysToExit(12)).toBe('12 days')
    expect(fmtDaysToExit(1234)).toBe('1,234 days')
    expect(fmtDaysToExit(null)).toBe('—')
    expect(fmtDaysToExit(undefined)).toBe('—')
  })
})

describe('fmtRank', () => {
  it('reads as an ordinal percentile', () => {
    expect(fmtRank(82)).toBe('82nd pct of market')
    expect(fmtRank(81.6)).toBe('82nd pct of market')
    expect(fmtRank(1)).toBe('1st pct of market')
    expect(fmtRank(13)).toBe('13th pct of market')
    expect(fmtRank(0)).toBe('0th pct of market')
    expect(fmtRank(null)).toBeUndefined()
  })
})

describe('riskChip', () => {
  it('shows vol and exit days with an accessible label', () => {
    const c = riskChip('VRLLOG', { vol_1y: 0.34, days_to_exit_5l: 3, flags: [] })
    expect(c.text).toBe('vol 34% · exit 3 d')
    expect(c.label).toBe('VRLLOG risk: 1-year volatility 34%, 3 days to exit ₹5 lakh')
    expect(c.tone).toBe('neutral')
    expect(c.title).toBeUndefined()
  })

  it('warns on surveillance or illiquidity and lists flags', () => {
    const c = riskChip('X', { vol_1y: 0.6, days_to_exit_5l: 40, flags: ['illiquid', 'asm'] })
    expect(c.tone).toBe('warn')
    expect(c.title).toBe(`${flagLabel('illiquid')}; ${flagLabel('asm')}`)
    expect(c.label).toContain(flagLabel('asm'))
  })

  it('is null without a row and dashes blank metrics', () => {
    expect(riskChip('X', null)).toBeNull()
    const c = riskChip('X', { vol_1y: null, days_to_exit_5l: null, flags: ['price_break'] })
    expect(c.text).toBe('vol — · exit —')
    expect(c.tone).toBe('neutral')
  })
})
