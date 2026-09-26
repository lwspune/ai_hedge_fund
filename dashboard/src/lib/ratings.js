// Credit ratings (credit_ratings / current_credit_ratings, read from NSE rating filings).

const rank = (r) => [r.scale === 'domestic' ? 0 : 1, r.term === 'long' ? 0 : 1]

// The rating shown in the company header: domestic long term first (global ratings sit under the
// sovereign ceiling, so they aren't comparable), then global, then short term; newest within each.
export function headlineRating(rows) {
  if (!rows?.length) return null
  const sorted = [...rows].sort((a, b) => {
    const [ra, rb] = [rank(a), rank(b)]
    return ra[0] - rb[0] || ra[1] - rb[1] || String(b.disclosed_at).localeCompare(String(a.disclosed_at))
  })
  const [top] = sorted
  const others = sorted.filter((r) => r !== top && r.term === 'long')
  return { ...top, others }
}

export function ratingGrade(r) {
  const tail = r.watch ? `Watch ${r.watch}` : r.outlook
  return tail ? `${r.rating} · ${tail}` : r.rating
}

const ACTION = {
  assigned: ['Assigned', 'neutral'], reaffirmed: ['Reaffirmed', 'neutral'], revised: ['Revised', 'neutral'],
  upgraded: ['Upgraded', 'pos'], downgraded: ['Downgraded', 'neg'], withdrawn: ['Withdrawn', 'neutral'],
}

export function ratingAction(r) {
  if (r.action === 'watch') {
    return { label: 'On watch', tone: r.watch === 'positive' ? 'pos' : r.watch === 'negative' ? 'neg' : 'warn' }
  }
  const a = ACTION[r.action]
  if (!a) return { label: '—', tone: null }
  const from = r.prev_rating && (r.action === 'upgraded' || r.action === 'downgraded') ? ` from ${r.prev_rating}` : ''
  return { label: a[0] + from, tone: a[1] }
}
