import { useEffect, useId, useRef, useState } from 'react'
import { fmtDate } from '../../lib/format'

// A small time-series line chart (inline SVG, no dependency). One y-axis, a fixed domain, 2px lines,
// hairline grid, the latest value labelled at each line's end, a crosshair + tooltip that follows the
// pointer AND the keyboard (←/→, Shift = 20 steps, Home/End). `hover` / `onHover` let small multiples
// share one crosshair. series: [{ key, label, color (CSS var), values: (number|null)[] }] aligned to `dates`.
const M = { top: 10, right: 64, bottom: 24, left: 44 }
const LABEL_GAP = 13

function useWidth(ref) {
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}

function path(values, x, y) {
  let d = ''
  let pen = false
  values.forEach((v, i) => {
    if (v == null) { pen = false; return }
    d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
    pen = true
  })
  return d
}

const lastIndex = (values) => {
  for (let i = values.length - 1; i >= 0; i -= 1) if (values[i] != null) return i
  return -1
}

// End labels: sorted by y, pushed apart to LABEL_GAP; a moved label gets a leader line.
function endLabels(series, x, y) {
  const labels = series.map((s) => {
    const i = lastIndex(s.values)
    return i < 0 ? null : { key: s.key, color: s.color, value: s.values[i], x0: x(i), y0: y(s.values[i]) }
  }).filter(Boolean).sort((a, b) => a.y0 - b.y0)
  labels.forEach((l, k) => { l.y = k === 0 ? l.y0 : Math.max(l.y0, labels[k - 1].y + LABEL_GAP) })
  return labels
}

export default function LineChart({
  title, dates, series, yDomain, yTicks, fmtY, refLine, hover, onHover, height = 180, summary,
}) {
  const wrap = useRef(null)
  const w = useWidth(wrap) || 640
  const tipId = useId()
  const n = dates.length
  const iw = Math.max(40, w - M.left - M.right)
  const ih = height - M.top - M.bottom
  const [y0, y1] = yDomain
  const x = (i) => M.left + (n > 1 ? (i / (n - 1)) * iw : 0)
  const y = (v) => M.top + (1 - (Math.min(Math.max(v, y0), y1) - y0) / (y1 - y0)) * ih

  const years = []
  dates.forEach((d, i) => { if (i === 0 || d.slice(0, 4) !== dates[i - 1].slice(0, 4)) years.push([i, d.slice(0, 4)]) })

  const pick = (px) => {
    const i = Math.round(((px - M.left) / iw) * (n - 1))
    return Math.min(n - 1, Math.max(0, i))
  }
  const onPointerMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    onHover(pick(e.clientX - r.left))
  }
  const onKeyDown = (e) => {
    const cur = hover ?? n - 1
    const step = e.shiftKey ? 20 : 1
    const next = e.key === 'ArrowLeft' ? cur - step : e.key === 'ArrowRight' ? cur + step
      : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : null
    if (next == null) return
    e.preventDefault()
    onHover(Math.min(n - 1, Math.max(0, next)))
  }

  const tip = hover != null && hover < n ? {
    left: x(hover), date: dates[hover],
    rows: series.map((s) => ({ key: s.key, label: s.label, color: s.color, value: s.values[hover] })),
  } : null
  const tipText = tip ? `${fmtDate(tip.date)}: ${tip.rows.map((r) => `${r.label} ${fmtY(r.value)}`).join(', ')}` : ''

  return (
    <figure className="chart">
      <figcaption className="chart-head">
        <span className="chart-title">{title}</span>
        {series.length > 1 && (
          <span className="chart-legend">
            {series.map((s) => (
              <span key={s.key} className="chart-key">
                <svg width="14" height="8" aria-hidden="true"><line x1="0" y1="4" x2="14" y2="4" stroke={s.color} strokeWidth="2" strokeLinecap="round" /></svg>
                {s.label}
              </span>
            ))}
          </span>
        )}
        {refLine && (
          <span className="chart-key chart-note">
            <svg width="14" height="8" aria-hidden="true"><line x1="0" y1="4" x2="14" y2="4" className="chart-ref" /></svg>
            {refLine.label}
          </span>
        )}
      </figcaption>
      <p className="sr-only">{summary}</p>
      <div ref={wrap} className="chart-plot" tabIndex={0} role="group"
           aria-label={`${title}. Use the left and right arrow keys to read values by date.`}
           aria-describedby={tipId}
           onPointerMove={onPointerMove} onPointerLeave={() => onHover(null)}
           onFocus={() => onHover(hover ?? n - 1)} onBlur={() => onHover(null)} onKeyDown={onKeyDown}>
        <svg width={w} height={height} aria-hidden="true">
          {yTicks.map((t) => (
            <g key={t}>
              <line className="chart-grid" x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} />
              <text className="chart-axis" x={M.left - 6} y={y(t)} dy="0.32em" textAnchor="end">{fmtY(t)}</text>
            </g>
          ))}
          {years.map(([i, yr]) => (
            <text key={yr} className="chart-axis" x={x(i)} y={height - 6} textAnchor="start">{yr}</text>
          ))}
          {refLine && (
            <line className="chart-ref" x1={M.left} x2={M.left + iw} y1={y(refLine.value)} y2={y(refLine.value)} />
          )}
          {series.map((s) => (
            <path key={s.key} d={path(s.values, x, y)} fill="none" stroke={s.color} strokeWidth="2"
                  strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {endLabels(series, x, y).map((l) => (
            <g key={l.key}>
              {Math.abs(l.y - l.y0) > 0.5 && (
                <line className="chart-leader" x1={l.x0 + 3} y1={l.y0} x2={M.left + iw + 6} y2={l.y} />
              )}
              <line x1={M.left + iw + 6} x2={M.left + iw + 14} y1={l.y} y2={l.y} stroke={l.color} strokeWidth="2" strokeLinecap="round" />
              <text className="chart-end" x={M.left + iw + 17} y={l.y} dy="0.32em">{fmtY(l.value)}</text>
            </g>
          ))}
          {tip && (
            <g>
              <line className="chart-cross" x1={tip.left} x2={tip.left} y1={M.top} y2={M.top + ih} />
              {tip.rows.filter((r) => r.value != null).map((r) => (
                <circle key={r.key} cx={tip.left} cy={y(r.value)} r="4" fill={r.color} className="chart-dot" />
              ))}
            </g>
          )}
        </svg>
        {tip && (
          <div className="chart-tip" style={tip.left > w / 2 ? { right: w - tip.left + 10 } : { left: tip.left + 10 }}>
            <div className="chart-tip-date">{fmtDate(tip.date)}</div>
            {tip.rows.map((r) => (
              <div key={r.key} className="chart-tip-row">
                <svg width="12" height="8" aria-hidden="true"><line x1="0" y1="4" x2="12" y2="4" stroke={r.color} strokeWidth="2" strokeLinecap="round" /></svg>
                <strong>{fmtY(r.value)}</strong> <span>{r.label}</span>
              </div>
            ))}
          </div>
        )}
        <span id={tipId} className="sr-only" aria-live="polite">{tipText}</span>
      </div>
    </figure>
  )
}
