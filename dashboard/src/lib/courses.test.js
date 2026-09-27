import { describe, expect, it } from 'vitest'
import courses from '../courses.json'
import learnings from '../learnings.json'
import signals from '../signals.json'
import { findCourse, moduleNav, progressPct, readyModules, reviewDue, toggleDone } from './courses'

const LEARNING_IDS = new Set(learnings.map((l) => l.id))
const SIGNAL_NAMES = new Set(signals.map((s) => s.name))
const SLUG = /^[a-z0-9-]+$/
const DATE = /^\d{4}-\d{2}-\d{2}$/
const filled = (s) => typeof s === 'string' && s.trim().length > 0

describe('courses.json', () => {
  it('has courses with unique slug ids and a review date', () => {
    expect(courses.length).toBeGreaterThan(0)
    expect(new Set(courses.map((c) => c.id)).size).toBe(courses.length)
    for (const c of courses) {
      expect(c.id).toMatch(SLUG)
      expect(filled(c.title) && filled(c.summary)).toBe(true)
      expect(c.reviewed).toMatch(DATE)
      expect(c.reviewEveryDays).toBeGreaterThan(0)
    }
  })

  const cases = courses.flatMap((c) => c.modules.map((m) => [`${c.id}/${m.id}`, c, m]))

  it.each(cases)('%s is well formed', (_k, c, m) => {
    expect(m.id).toMatch(SLUG)
    expect(c.levels.map((l) => l.key)).toContain(m.level)
    expect(filled(m.title)).toBe(true)
    expect(['ready', 'planned']).toContain(m.status)
    if (m.status === 'planned') return
    expect(m.minutes).toBeGreaterThan(0)
    expect(m.goals.length).toBeGreaterThan(0)
    expect(m.lesson.length).toBeGreaterThan(0)
    m.lesson.forEach((p) => expect(filled(p)).toBe(true))
    expect(m.tryIt.steps.length).toBeGreaterThan(0)
    expect(filled(m.tryIt.deliverable)).toBe(true)
    expect(m.check.length).toBeGreaterThan(0)
    m.check.forEach((q) => expect(filled(q.q) && filled(q.a)).toBe(true))
    for (const f of m.india || []) {
      expect(filled(f.text) && filled(f.source)).toBe(true)
      expect(f.asOf).toMatch(DATE)
      if (f.url) expect(f.url).toMatch(/^https:\/\//)
    }
    for (const d of m.deeper || []) {
      expect(filled(d.title)).toBe(true)
      if (d.url) expect(d.url).toMatch(/^https:\/\//)
    }
    for (const id of m.learnings || []) expect(LEARNING_IDS.has(id)).toBe(true)
    for (const s of m.signals || []) expect(SIGNAL_NAMES.has(s)).toBe(true)
  })

  it('has unique module ids within a course and at least one ready module', () => {
    for (const c of courses) {
      expect(new Set(c.modules.map((m) => m.id)).size).toBe(c.modules.length)
      expect(readyModules(c).length).toBeGreaterThan(0)
    }
  })
})

const COURSE = {
  id: 'c', reviewed: '2026-01-01', reviewEveryDays: 180,
  modules: [
    { id: 'a', status: 'ready' }, { id: 'b', status: 'ready' },
    { id: 'p', status: 'planned' }, { id: 'c', status: 'ready' },
  ],
}

describe('course helpers', () => {
  it('finds a course by id', () => {
    expect(findCourse([COURSE], 'c')).toBe(COURSE)
    expect(findCourse([COURSE], 'nope')).toBeUndefined()
  })

  it('navigates ready modules only, skipping planned ones', () => {
    expect(moduleNav(COURSE, 'a')).toEqual({ prev: null, next: 'b' })
    expect(moduleNav(COURSE, 'b')).toEqual({ prev: 'a', next: 'c' })
    expect(moduleNav(COURSE, 'c')).toEqual({ prev: 'b', next: null })
  })

  it('flags a course whose review is overdue', () => {
    expect(reviewDue(COURSE, new Date('2026-06-29'))).toBe(false)
    expect(reviewDue(COURSE, new Date('2026-06-30'))).toBe(true)
  })

  it('counts progress over ready modules and ignores unknown ids', () => {
    expect(progressPct(COURSE, [])).toBe(0)
    expect(progressPct(COURSE, ['a', 'p', 'zzz'])).toBe(33)
    expect(progressPct(COURSE, ['a', 'b', 'c'])).toBe(100)
  })

  it('toggles a module in the done list without mutating it', () => {
    const done = ['a']
    expect(toggleDone(done, 'b')).toEqual(['a', 'b'])
    expect(toggleDone(done, 'a')).toEqual([])
    expect(done).toEqual(['a'])
  })
})
