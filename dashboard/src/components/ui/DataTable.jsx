import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { sortRows } from '../../lib/sort'
import { EmptyState } from './States'

// columns: [{ key, header, align: 'left'|'right', mono?, nowrap?, render?(row), sortable?,
//             sortValue?(row), title?, width? }]
// Numeric (right-aligned) columns are mono + nowrap by default; text columns wrap.
// stickyFirstCol pins the first column as a row header. scrollEnd starts scrolled to the right
// (newest period on statement tables). maxHeight makes the body scroll so the thead sticks.
export default function DataTable({
  columns, rows, rowKey, sort: initialSort, onSort, stickyFirstCol = false, emptyText,
  emptyHint, dense = false, caption, scrollEnd = false, maxHeight, expandedRow, renderExpanded,
}) {
  const [sort, setSort] = useState(initialSort || null)
  const scroller = useRef(null)
  const [more, setMore] = useState({ left: false, right: false, down: false })

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return rows
    const get = col.sortValue || ((r) => r[col.key])
    return sortRows(rows, get, sort.dir)
  }, [rows, columns, sort])

  useLayoutEffect(() => {
    const el = scroller.current
    if (el && scrollEnd) el.scrollLeft = el.scrollWidth
  }, [scrollEnd, rows])

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const update = () => setMore({
      left: el.scrollLeft > 1,
      right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1,
      down: el.scrollHeight > el.clientHeight + 1,
    })
    update()
    el.addEventListener('scroll', update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      ro.disconnect()
    }
  }, [rows])

  if (!rows || rows.length === 0) return <EmptyState title={emptyText || 'Nothing here.'} hint={emptyHint} />

  function toggle(key) {
    const next = sort?.key === key
      ? { key, dir: sort.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: columns.find((c) => c.key === key)?.align === 'right' ? 'desc' : 'asc' }
    setSort(next)
    onSort?.(next)
  }

  const cls = (c, i) => [
    c.align === 'right' ? 'r' : '',
    c.mono || c.align === 'right' ? 'mono' : '',
    c.nowrap || c.align === 'right' ? 'nowrap' : '',
    stickyFirstCol && i === 0 ? 'sticky-col' : '',
  ].filter(Boolean).join(' ') || undefined

  const wrapCls = ['dt', dense && 'dt-dense', more.right && 'more-right', more.left && 'more-left']
    .filter(Boolean).join(' ')

  // A scrolling table must be reachable by keyboard: make the scroller a focusable region.
  const scrolls = more.right || more.left || more.down
  return (
    <div className={wrapCls}>
      <div className="dt-scroll" ref={scroller} style={maxHeight ? { maxHeight } : undefined}
           tabIndex={scrolls ? 0 : undefined}
           role={scrolls ? 'region' : undefined}
           aria-label={scrolls ? `${caption || 'Table'} (scrollable)` : undefined}>
        <table>
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr>
              {columns.map((c, i) => {
                const active = sort?.key === c.key
                const ariaSort = c.sortable ? (active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none') : undefined
                return (
                  <th key={c.key} scope="col" className={cls(c, i)} aria-sort={ariaSort}
                      title={c.title} style={c.width ? { width: c.width } : undefined}>
                    {c.sortable ? (
                      <button type="button" className="dt-sort" onClick={() => toggle(c.key)}>
                        {c.header}
                        <span className="dt-arrow" aria-hidden="true">
                          {active ? (sort.dir === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </button>
                    ) : c.header}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, ri) => {
              const key = rowKey(row, ri)
              const open = expandedRow && renderExpanded ? expandedRow(row) : false
              return (
                <Fragment key={key}>
                  <tr className={open ? 'is-open' : undefined}>
                    {columns.map((c, i) => {
                      const v = c.render ? c.render(row) : row[c.key]
                      const content = v == null || v === '' ? '—' : v
                      return stickyFirstCol && i === 0
                        ? <th key={c.key} scope="row" className={cls(c, i)}>{content}</th>
                        : <td key={c.key} className={cls(c, i)}>{content}</td>
                    })}
                  </tr>
                  {open && (
                    <tr className="dt-expanded">
                      <td colSpan={columns.length}>{renderExpanded(row)}</td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
