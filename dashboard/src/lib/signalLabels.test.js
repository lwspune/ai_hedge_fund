import { describe, expect, it } from 'vitest'
import signals from '../signals.json'
import { roleLabel, signalHeadline, signalLabel, typeLabel } from './signalLabels'

describe('signalLabels', () => {
  it.each(signals.map((s) => s.name))('%s has a human label and a short headline', (name) => {
    expect(signalLabel(name)).not.toBe(name)
    expect(signalLabel(name)).not.toMatch(/_/)
    const h = signalHeadline(name)
    expect(h.length).toBeGreaterThan(0)
    expect(h.length).toBeLessThanOrEqual(90)
  })

  it('falls back to the raw name for an unknown signal', () => {
    expect(signalLabel('brand_new_signal')).toBe('brand_new_signal')
    expect(signalHeadline('brand_new_signal')).toBe('')
  })

  it('labels roles and types', () => {
    expect(roleLabel('primary')).toBe('Trade')
    expect(roleLabel('watch')).toBe('Watch')
    expect(roleLabel('lens')).toBe('Lens')
    expect(roleLabel('documented')).toBe('Control')
    expect(typeLabel('structural')).toBe('Structural')
    expect(typeLabel('drift')).toBe('Drift')
    expect(typeLabel('spread')).toBe('Spread')
    expect(roleLabel('other')).toBe('other')
  })
})
