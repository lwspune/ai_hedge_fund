import useLoad from '../../lib/useLoad'
import { fmtCrValue, fmtDate, fmtNum, fmtPct, fmtPctPts } from '../../lib/format'
import { blanksPriceMetrics, flagLabel, fmtDaysToExit, fmtRank, loadRisk } from '../../lib/risk'
import { sectorLabel } from '../../lib/sectors'
import Section from '../ui/Section'
import { Stat, StatGrid } from '../ui/Stat'
import { Badge } from '../ui/Badge'
import { EmptyState, ErrorNote } from '../ui/States'
import { Loading, SkeletonStats } from '../ui/Skeleton'

const WARN = new Set(['asm', 'gsm', 'illiquid', 'action_unverified', 'price_break'])

const INFO = 'Measurements of how the stock behaves, not a signal: no verdict and no score. '
  + 'Closes are adjusted for splits and bonuses; beta and correlation are against NIFTY 500 over the last '
  + '250 sessions. Days to exit = ₹5 lakh sold at 10% of the median day’s turnover.'

// Risk lens: volatility, drawdown and liquidity from risk_metrics. Fetched only when the tab is open.
export default function RiskTab({ symbol }) {
  const { loading, error, data: r } = useLoad(() => loadRisk(symbol), [symbol])
  if (loading) {
    return <Loading label="Loading risk measurements"><SkeletonStats n={12} /></Loading>
  }
  if (error) return <ErrorNote what="risk measurements" message={error} />
  if (!r) {
    return (
      <Section id="risk" title="Risk">
        <EmptyState title="No risk measurements for this symbol."
                    hint="They are computed each trading day for listed symbols with prices in the last 400 days." />
      </Section>
    )
  }
  const flags = r.flags || []
  const blank = blanksPriceMetrics(flags)
  return (
    <Section id="risk" title="Risk" info={INFO}
             meta={`As of ${fmtDate(r.as_of)} · 400-day window · NIFTY 500 benchmark`
               + `${r.sector_index ? ` · sector: ${sectorLabel(r)}` : ''} · not a signal`}>
      {flags.length > 0 && (
        <p className="badges" aria-label="Risk flags">
          {flags.map((f) => <Badge key={f} tone={WARN.has(f) ? 'warn' : 'neutral'}>{flagLabel(f)}</Badge>)}
        </p>
      )}
      {blank && (
        <p className="risk-note">
          Price measurements are blank: the price history holds a jump that a recorded split, bonus or demerger
          doesn’t explain, so any volatility or drawdown figure would be wrong. Liquidity is unaffected.
        </p>
      )}
      <h3 className="subhead">Volatility</h3>
      <StatGrid label="Volatility">
        <Stat label="1y volatility" value={fmtPct(r.vol_1y, 0)} sub={fmtRank(r.vol_rank)} />
        <Stat label="3m volatility" value={fmtPct(r.vol_3m, 0)} />
        <Stat label="Beta (NIFTY 500)" value={fmtNum(r.beta_1y, 2)} />
        <Stat label="Correlation" value={fmtNum(r.corr_1y, 2)} />
        <Stat label="Idiosyncratic vol" value={fmtPct(r.idio_vol_1y, 0)} />
      </StatGrid>
      <h3 className="subhead">Drawdown</h3>
      <StatGrid label="Drawdown">
        <Stat label="Max drawdown" value={fmtPct(r.max_dd_1y, 0)} />
        <Stat label="Below window high" value={fmtPct(r.dd_now, 0)} />
        <Stat label="Worst day" value={fmtPct(r.worst_day_1y)} />
        <Stat label="Worst week" value={fmtPct(r.worst_week_1y)} />
      </StatGrid>
      <h3 className="subhead">Liquidity</h3>
      <StatGrid label="Liquidity">
        <Stat label="Median turnover (20 d)" value={fmtCrValue(r.adv_20_cr)} sub={fmtRank(r.liq_rank)} />
        <Stat label="Days to exit ₹5 lakh" value={fmtDaysToExit(r.days_to_exit_5l)} sub="at 10% of daily turnover"
              tone={r.days_to_exit_5l > 1 ? 'warn' : undefined} />
        <Stat label="Delivery (20 d median)" value={fmtPctPts(r.delivery_pct_20, 0)} />
      </StatGrid>
      {r.sector_index && (
        <>
          <h3 className="subhead">Sector</h3>
          <StatGrid label="Sector">
            <Stat label="Sector index" value={sectorLabel(r)}
                  title={r.sector_is_fallback ? 'The closest NSE sector index has under a year of history; '
                    + 'a broader one is used until it does.' : undefined} />
            <Stat label="Beta to sector" value={fmtNum(r.beta_sector_1y, 2)} />
            <Stat label="Correlation to sector" value={fmtNum(r.corr_sector_1y, 2)} />
            <Stat label="Sector 3m" value={fmtPct(r.sector_ret_3m)} sub={`stock ${fmtPct(r.ret_3m)}`} />
          </StatGrid>
        </>
      )}
    </Section>
  )
}
