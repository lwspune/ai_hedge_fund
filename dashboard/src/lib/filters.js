// Client-side filters for the Data view. An empty set means "no filter" (show all).

export function toggle(set, value) {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

export function filterDeals(rows, { sides, kinds, symbol } = {}) {
  const prefix = (symbol || '').trim().toUpperCase()
  return rows.filter((d) =>
    (!sides?.size || sides.has((d.side || '').toUpperCase()))
    && (!kinds?.size || kinds.has((d.kind || '').toLowerCase()))
    && (!prefix || (d.symbol || '').toUpperCase().startsWith(prefix)))
}
