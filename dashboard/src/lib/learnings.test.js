import { describe, expect, it } from 'vitest'
import learnings from '../learnings.json'
import signals from '../signals.json'
import { SECTIONS, groupLearnings } from './learnings'

const SIGNAL_NAMES = new Set(signals.map((s) => s.name))
const SECTION_KEYS = new Set(SECTIONS.map((s) => s.key))

describe('learnings.json', () => {
  it('has entries with unique ids', () => {
    expect(learnings.length).toBeGreaterThan(0)
    const ids = learnings.map((l) => l.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it.each(learnings.map((l) => [l.id, l]))('%s is complete', (_id, l) => {
    expect(l.id).toMatch(/^[a-z0-9-]+$/)
    expect(SECTION_KEYS.has(l.section)).toBe(true)
    for (const k of ['title', 'body', 'why', 'source']) expect(l[k]?.trim().length).toBeGreaterThan(0)
    expect(l.learned).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    for (const name of l.signals || []) expect(SIGNAL_NAMES.has(name)).toBe(true)
  })

  it('fills every section', () => {
    const grouped = groupLearnings(learnings)
    for (const g of grouped) expect(g.items.length).toBeGreaterThan(0)
  })
})

describe('groupLearnings', () => {
  it('groups in section order, keeps the file order within a section, and drops unknown sections', () => {
    const rows = [
      { id: 'a', section: 'concepts', learned: '2026-01-01' },
      { id: 'b', section: 'thesis', learned: '2026-01-01' },
      { id: 'c', section: 'concepts', learned: '2026-03-01' },
      { id: 'd', section: 'bogus', learned: '2026-03-01' },
    ]
    const g = groupLearnings(rows)
    expect(g.map((s) => s.key)).toEqual(SECTIONS.map((s) => s.key))
    expect(g.find((s) => s.key === 'thesis').items.map((i) => i.id)).toEqual(['b'])
    expect(g.find((s) => s.key === 'concepts').items.map((i) => i.id)).toEqual(['a', 'c'])
    expect(g.flatMap((s) => s.items).some((i) => i.id === 'd')).toBe(false)
  })
})
