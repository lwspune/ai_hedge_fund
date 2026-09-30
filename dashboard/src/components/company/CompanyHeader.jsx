import { fmtCrValue, fmtDate, fmtInr, fmtNum, fmtPct, fmtPctPts } from '../../lib/format'
import { headlineRating, ratingGrade } from '../../lib/ratings'
import { Badge } from '../ui/Badge'
import { Stat } from '../ui/Stat'

const MAX_INDICES = 4

// The headline credit rating; the other agencies' long-term ratings in the tooltip.
function RatingStat({ cr }) {
  const others = cr.others.map((r) => `${r.agency} ${ratingGrade(r)}`).join(', ')
  return (
    <Stat label="Credit rating" value={ratingGrade(cr)} sub={`${cr.agency} · ${fmtDate(cr.disclosed_at)}`}
          title={others ? `Also: ${others}` : undefined} />
  )
}

// Risk lens headline: 1-year volatility with beta vs NIFTY 500. Omitted when there is no risk row.
function RiskStat({ risk }) {
  return (
    <Stat label="1y vol" value={fmtPct(risk.vol_1y, 0)} sub={risk.beta_1y == null ? undefined : `β ${fmtNum(risk.beta_1y, 2)}`}
          title="Annualised volatility over the last 250 sessions; β against NIFTY 500. See the Risk tab." />
  )
}

// Company identity + four headline stats. `children` (the tab bar) renders inside the header.
export default function CompanyHeader({ company: c, snap: s, ratings, risk, children }) {
  const cr = headlineRating(ratings)
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
            {cr && <RatingStat cr={cr} />}
            {risk && <RiskStat risk={risk} />}
          </dl>
        ) : cr || risk ? (
          <dl className="co-stats" aria-label="Headline figures">
            {cr && <RatingStat cr={cr} />}
            {risk && <RiskStat risk={risk} />}
          </dl>
        ) : <p className="co-stats-none">Fundamentals not fetched yet</p>}
      </div>
      {children}
    </header>
  )
}
