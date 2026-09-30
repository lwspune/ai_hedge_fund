import useLoad from '../lib/useLoad'
import { fmtDate } from '../lib/format'
import { loadLatestRegime, regimeStrip } from '../lib/regime'
import InfoPopover from './ui/InfoPopover'

// One line under the freshness strip: where the market stands today. Measurements, not a signal.
export default function RegimeStrip() {
  const { data } = useLoad(loadLatestRegime, [])
  const parts = regimeStrip(data)
  if (!parts) return <p className="regime-strip" aria-hidden="true">&nbsp;</p>
  return (
    <p className="regime-strip">
      <span className="sr-only">Market regime, {fmtDate(data.trade_date)}: </span>
      {parts.map((p, i) => (
        <span key={p.key}>
          {i > 0 && <span aria-hidden="true"> · </span>}
          <span className={p.tone ? `tone-${p.tone}` : undefined} title={p.note || undefined}>
            {p.text}{p.note && <span className="sr-only"> ({p.note})</span>}
          </span>
        </span>
      ))}
      <InfoPopover label="About the market regime">
        NIFTY 500 drawdown from its high since 2020, 20-day volatility and its percentile against every earlier
        day, and breadth over liquid mainboard stocks. Measurements, not a signal: amber marks a 10% correction
        or a 90th-percentile volatility, nothing more.
      </InfoPopover>
      <a className="regime-link" href="#/market">Market →</a>
    </p>
  )
}
