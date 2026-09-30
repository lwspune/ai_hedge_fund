import { describe, expect, it } from 'vitest'
import { DD_WARN, VOL_PCT_WARN, loadRegimeHistory, regimeStrip, regimeTone } from './regime'

const row = (o) => ({
  trade_date: '2026-09-30', n500_dd: -0.062, n500_vol_20: 0.18, n500_vol_pct: 72, pct_above_200: 0.38,
  pct_above_50: 0.41, new_highs: 12, new_lows: 45, n_universe: 1400, n_excluded: 17, ...o,
})

describe('regimeTone', () => {
  it('warns only at a correction or a 90th-percentile volatility', () => {
    expect(DD_WARN).toBe(-0.10)
    expect(VOL_PCT_WARN).toBe(90)
    expect(regimeTone(row({ n500_dd: -0.10 })).dd).toBe('warn')
    expect(regimeTone(row({ n500_dd: -0.0999 })).dd).toBeNull()
    expect(regimeTone(row({ n500_vol_pct: 90 })).vol).toBe('warn')
    expect(regimeTone(row({ n500_vol_pct: 89.9 })).vol).toBeNull()
    expect(regimeTone(row({ n500_dd: null, n500_vol_pct: null }))).toEqual({ dd: null, vol: null })
  })
})

describe('regimeStrip', () => {
  it('reads as one line of parts', () => {
    const parts = regimeStrip(row())
    expect(parts.map((p) => p.text)).toEqual([
      'NIFTY 500 −6.2% from high', 'vol 18% (72nd pct)', '38% above 200-DMA', '12 highs / 45 lows',
    ])
    expect(parts.every((p) => p.tone == null)).toBe(true)
  })

  it('carries the warn tone with a word, not colour alone', () => {
    const [dd, vol] = regimeStrip(row({ n500_dd: -0.15, n500_vol_pct: 95 }))
    expect(dd).toMatchObject({ tone: 'warn', note: 'correction' })
    expect(vol).toMatchObject({ tone: 'warn', note: 'high volatility' })
  })

  it('dashes what is missing and is null without a row', () => {
    expect(regimeStrip(null)).toBeNull()
    const parts = regimeStrip(row({ n500_vol_pct: null, new_lows: null }))
    expect(parts[1].text).toBe('vol 18%')
    expect(parts[3].text).toBe('12 highs / — lows')
  })
})

describe('loadRegimeHistory', () => {
  it('pages past the 1,000-row cap and keeps date order', async () => {
    const all = Array.from({ length: 2345 }, (_, i) => ({ trade_date: `d${String(i).padStart(4, '0')}` }))
    const calls = []
    const fetchPage = async (from, to) => {
      calls.push([from, to])
      return { data: all.slice(from, to + 1), error: null }
    }
    const rows = await loadRegimeHistory(fetchPage)
    expect(rows).toHaveLength(2345)
    expect(rows[0].trade_date).toBe('d0000')
    expect(rows[2344].trade_date).toBe('d2344')
    expect(calls).toEqual([[0, 999], [1000, 1999], [2000, 2999]])
  })

  it('throws a page error', async () => {
    await expect(loadRegimeHistory(async () => ({ data: null, error: new Error('boom') }))).rejects.toThrow('boom')
  })
})
