import { daysFrom, fmtAgo, fmtDate, fmtRelative } from './format'

// Max age in calendar days per source. deals / filings mirror scripts/check_freshness.py;
// the scans run on the weekday daily refresh, so two days covers one missed run.
export const FRESHNESS_RULES = { deals: 6, filings: 5, buybackScan: 2, rightsScan: 2 }

export const ageDays = (latest, now = new Date()) => 0 - daysFrom(latest, now)

// Same comparison as check_freshness.stale(): stale when age > max age, or no row at all.
export function isStale(source, latest, now = new Date()) {
  if (latest == null) return true
  return ageDays(latest, now) > FRESHNESS_RULES[source]
}

const STRIP = [
  ['deals', 'Deals', fmtDate],
  ['buybackScan', 'Buyback scan', fmtAgo],
  ['rightsScan', 'Rights scan', fmtAgo],
  ['filings', 'Filings', fmtRelative],
]

// latest: { deals, buybackScan, rightsScan, filings } newest date/timestamp per source.
export function freshnessItems(latest, now = new Date()) {
  return STRIP.map(([key, label, fmt]) => ({
    key, label,
    text: latest[key] == null ? 'none' : fmt(latest[key], now),
    stale: isStale(key, latest[key], now),
  }))
}
