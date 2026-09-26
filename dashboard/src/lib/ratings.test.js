import { describe, expect, it } from 'vitest'
import { headlineRating, ratingAction, ratingGrade } from './ratings'

const row = (o) => ({ scale: 'domestic', term: 'long', outlook: null, watch: null, ...o })

describe('headlineRating', () => {
  it('picks the most recent domestic long-term rating', () => {
    const h = headlineRating([
      row({ agency: 'ICRA', rating: 'AA', disclosed_at: '2026-01-10T10:00:00+05:30' }),
      row({ agency: 'CRISIL', rating: 'AA-', outlook: 'Stable', disclosed_at: '2026-06-01T10:00:00+05:30' }),
      row({ agency: 'CRISIL', term: 'short', rating: 'A1+', disclosed_at: '2026-08-01T10:00:00+05:30' }),
      row({ agency: 'Fitch', scale: 'global', rating: 'BBB-', disclosed_at: '2026-09-01T10:00:00+05:30' }),
    ])
    expect(h.agency).toBe('CRISIL')
    expect(h.rating).toBe('AA-')
    expect(h.others.map((r) => r.agency)).toEqual(['ICRA', 'Fitch'])
  })

  it('falls back to a global rating, then short term, when that is all there is', () => {
    expect(headlineRating([row({ agency: 'Moody\'s', scale: 'global', rating: 'Baa3' })]).rating).toBe('Baa3')
    expect(headlineRating([row({ agency: 'CARE', term: 'short', rating: 'A1+' })]).rating).toBe('A1+')
  })

  it('is null without ratings', () => {
    expect(headlineRating([])).toBeNull()
    expect(headlineRating(null)).toBeNull()
  })
})

describe('ratingGrade', () => {
  it('shows the grade with its outlook or watch', () => {
    expect(ratingGrade(row({ agency: 'CRISIL', rating: 'AA-', outlook: 'Stable' }))).toBe('AA- · Stable')
    expect(ratingGrade(row({ agency: 'CARE', rating: 'BB', watch: 'developing' }))).toBe('BB · Watch developing')
    expect(ratingGrade(row({ agency: 'ICRA', term: 'short', rating: 'A1+' }))).toBe('A1+')
  })
})

describe('ratingAction', () => {
  it('describes the move and its direction', () => {
    expect(ratingAction({ action: 'upgraded', prev_rating: 'A' })).toEqual({ label: 'Upgraded from A', tone: 'pos' })
    expect(ratingAction({ action: 'downgraded', prev_rating: null })).toEqual({ label: 'Downgraded', tone: 'neg' })
    expect(ratingAction({ action: 'watch', watch: 'negative' })).toEqual({ label: 'On watch', tone: 'neg' })
    expect(ratingAction({ action: 'watch', watch: 'positive' })).toEqual({ label: 'On watch', tone: 'pos' })
    expect(ratingAction({ action: 'reaffirmed' })).toEqual({ label: 'Reaffirmed', tone: 'neutral' })
    expect(ratingAction({ action: null })).toEqual({ label: '—', tone: null })
  })
})
