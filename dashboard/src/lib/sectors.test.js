import { describe, expect, it } from 'vitest'
import { sectorLabel } from './sectors'

describe('sectorLabel', () => {
  it('names the index and says when it is a fallback', () => {
    expect(sectorLabel({ sector_index: 'Nifty Bank', sector_is_fallback: false })).toBe('Nifty Bank')
    expect(sectorLabel({ sector_index: 'Nifty India Manufacturing', sector_is_fallback: true }))
      .toBe('Nifty India Manufacturing (fallback)')
  })

  it('shows the NIFTY 500 benchmark by name, not its ticker', () => {
    expect(sectorLabel({ sector_index: '^CRSLDX', sector_is_fallback: false })).toBe('NIFTY 500')
    expect(sectorLabel({ sector_index: '^CRSLDX', sector_is_fallback: true })).toBe('NIFTY 500 (no sector index yet)')
  })

  it('dashes a stock without a sector', () => {
    expect(sectorLabel({ sector_index: null })).toBe('—')
    expect(sectorLabel(null)).toBe('—')
  })
})
