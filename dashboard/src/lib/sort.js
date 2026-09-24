// Table sorting. Numbers compare numerically, strings case-insensitively (ISO dates therefore
// sort chronologically). Missing values always sink to the bottom, whatever the direction.

const missing = (v) => v == null || (typeof v === 'number' && Number.isNaN(v))

export function compareValues(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'en', { sensitivity: 'base', numeric: true })
}

export function sortRows(rows, accessor, dir = 'asc') {
  const sgn = dir === 'desc' ? -1 : 1
  return rows
    .map((row, i) => ({ row, i, v: accessor(row) }))
    .sort((x, y) => {
      const mx = missing(x.v), my = missing(y.v)
      if (mx || my) return mx === my ? x.i - y.i : mx ? 1 : -1
      return sgn * compareValues(x.v, y.v) || x.i - y.i
    })
    .map((x) => x.row)
}
