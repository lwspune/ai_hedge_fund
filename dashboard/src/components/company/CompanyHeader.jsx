import { fmtCrValue, fmtDate, fmtInr, fmtNum, fmtPctPts } from '../../lib/format'
import { Badge } from '../ui/Badge'
import { Stat } from '../ui/Stat'

const MAX_INDICES = 4

// Company identity + four headline stats. `children` (the tab bar) renders inside the header.
export default function CompanyHeader({ company: c, snap: s, children }) {
  const taxonomy = [...new Set([s?.sector, s?.industry, s?.basic_industry].filter(Boolean))].join(' › ')
    || c.industry
  const line = [taxonomy, c.series, c.listing_date ? `listed ${fmtDate(c.listing_date)}` : null].filter(Boolean)
  const indices = c.indices || []

  return (
    <header className="co-head">
      <div className="co-head-main">
        <div className="co-id">
          <h1 className="co-name">
            {c.name || c.symbol} <span className="co-sym">{c.symbol}</span>
          </h1>
          <p className="co-line">
            {line.join(' · ')}
            {c.status === 'delisted' && <> <Badge tone="neutral">Delisted {fmtDate(c.delisted_on)}</Badge></>}
          </p>
          {indices.length > 0 && (
            <p className="badges co-indices" aria-label="Index membership">
              {indices.slice(0, MAX_INDICES).map((i) => <Badge key={i}>{i}</Badge>)}
              {indices.length > MAX_INDICES && (
                <Badge title={indices.slice(MAX_INDICES).join(', ')}>+{indices.length - MAX_INDICES}</Badge>
              )}
            </p>
          )}
        </div>
        {s ? (
          <dl className="co-stats" aria-label="Headline figures">
            <Stat label="Price" value={fmtInr(s.price)} />
            <Stat label="Market cap" value={fmtCrValue(s.market_cap_cr)} />
            <Stat label="P/E" value={fmtNum(s.pe, 1)} />
            <Stat label="ROCE" value={fmtPctPts(s.roce)} />
          </dl>
        ) : <p className="co-stats-none">Fundamentals not fetched yet</p>}
      </div>
      {children}
    </header>
  )
}
