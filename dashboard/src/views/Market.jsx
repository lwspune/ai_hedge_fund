import { useState } from 'react'
import useLoad from '../lib/useLoad'
import { fmtDate, fmtNum, fmtPct } from '../lib/format'
import { DD_WARN, VOL_PCT_WARN, fmtVolPct, loadRegimeHistory } from '../lib/regime'
import Section from '../components/ui/Section'
import DataTable from '../components/ui/DataTable'
import LineChart from '../components/ui/LineChart'
import { EmptyState, ErrorNote } from '../components/ui/States'
import { Loading, SkeletonTable } from '../components/ui/Skeleton'

const S1 = 'var(--series-1)'
const S2 = 'var(--series-2)'
const pct0 = (v) => fmtPct(v, 0)
const pctile = (v) => (v == null ? '—' : fmtNum(v))

const INFO = 'Measurements of the market, not a signal: no label, no score, and nothing here gates an alert. '
  + 'Breadth covers liquid, regularly traded mainboard stocks (≥ ₹1 cr/day, printed on ≥ 80% of the last 250 '
  + 'sessions), on split / bonus-adjusted closes. The volatility percentile compares each day with every earlier '
  + 'day since 2020 only.'

const COLUMNS = [
  { key: 'trade_date', header: 'Date', nowrap: true, render: (r) => fmtDate(r.trade_date) },
  { key: 'n500_dd', header: 'NIFTY 500 off high', align: 'right', render: (r) => fmtPct(r.n500_dd) },
  { key: 'n50_dd', header: 'NIFTY 50 off high', align: 'right', render: (r) => fmtPct(r.n50_dd) },
  { key: 'n500_ret_1m', header: '1m', align: 'right', render: (r) => fmtPct(r.n500_ret_1m) },
  { key: 'n500_vol_20', header: 'Vol 20d', align: 'right', render: (r) => fmtPct(r.n500_vol_20, 0) },
  { key: 'n500_vol_pct', header: 'Vol pct', align: 'right', render: (r) => fmtVolPct(r.n500_vol_pct) ?? '—' },
  { key: 'pct_above_200', header: '> 200-DMA', align: 'right', render: (r) => pct0(r.pct_above_200) },
  { key: 'pct_above_50', header: '> 50-DMA', align: 'right', render: (r) => pct0(r.pct_above_50) },
  { key: 'new_highs', header: 'Highs', align: 'right', render: (r) => fmtNum(r.new_highs) },
  { key: 'new_lows', header: 'Lows', align: 'right', render: (r) => fmtNum(r.new_lows) },
  { key: 'up_share', header: 'Up', align: 'right', render: (r) => pct0(r.up_share) },
  { key: 'n_universe', header: 'Stocks', align: 'right', render: (r) => fmtNum(r.n_universe) },
]

const range = (vals, fmt) => {
  const v = vals.filter((x) => x != null)
  return v.length ? `from ${fmt(Math.min(...v))} to ${fmt(Math.max(...v))}` : 'no values'
}

// Market regime: where the market stands, with history since 2020. Three small multiples share one
// crosshair (hover or arrow keys), then the last 20 sessions as a table (the charts' table view).
export default function Market() {
  const { loading, error, data } = useLoad(() => loadRegimeHistory(), [])
  const [hover, setHover] = useState(null)

  if (loading) return <Loading label="Loading market regime"><SkeletonTable rows={8} cols={6} /></Loading>
  if (error) return <ErrorNote what="market regime" message={error} />
  if (!data?.length) {
    return (
      <Section id="market" title="Market regime" level={1}>
        <EmptyState title="No market regime rows yet."
                    hint="They are written each trading day by the scheduled refresh (backfilled from 2020)." />
      </Section>
    )
  }
  const dates = data.map((r) => r.trade_date)
  const col = (k) => data.map((r) => r[k])
  const last = data[data.length - 1]
  const dd = col('n500_dd')
  const ddLow = Math.min(...dd.filter((v) => v != null), -0.3)
  const ddMin = Math.floor(ddLow * 10 - 1e-9) / 10
  const ddTicks = []
  for (let k = 0; k >= Math.round(ddMin * 10); k -= 1) ddTicks.push(k / 10)

  return (
    <>
      <Section id="market" title="Market regime" level={1} info={INFO}
               meta={`As of ${fmtDate(last.trade_date)} · NIFTY 500 · not a signal`}>
        <div className="chart-stack">
          <LineChart title="How far below its high?" dates={dates} hover={hover} onHover={setHover}
                     series={[{ key: 'n500', label: 'NIFTY 500', color: S1, values: dd },
                              { key: 'n50', label: 'NIFTY 50', color: S2, values: col('n50_dd') }]}
                     yDomain={[ddMin, 0]} yTicks={ddTicks} fmtY={pct0}
                     refLine={{ value: DD_WARN, label: '−10%: a correction' }}
                     summary={`Drawdown from the high since 2020. Latest ${fmtDate(last.trade_date)}: NIFTY 500 `
                       + `${fmtPct(last.n500_dd)}, NIFTY 50 ${fmtPct(last.n50_dd)}; NIFTY 500 ${range(dd, fmtPct)}.`} />
          <LineChart title="How broad?" dates={dates} hover={hover} onHover={setHover}
                     series={[{ key: 'a200', label: 'Above 200-DMA', color: S1, values: col('pct_above_200') },
                              { key: 'a50', label: 'Above 50-DMA', color: S2, values: col('pct_above_50') }]}
                     yDomain={[0, 1]} yTicks={[0, 0.25, 0.5, 0.75, 1]} fmtY={pct0}
                     summary={'Share of liquid mainboard stocks above their moving averages. Latest: '
                       + `${pct0(last.pct_above_200)} above the 200-day, ${pct0(last.pct_above_50)} above the 50-day.`} />
          <LineChart title="How volatile against its own past?" dates={dates} hover={hover} onHover={setHover}
                     series={[{ key: 'vp', label: 'Volatility percentile', color: S1, values: col('n500_vol_pct') }]}
                     yDomain={[0, 100]} yTicks={[0, 25, 50, 75, 100]} fmtY={pctile}
                     refLine={{ value: VOL_PCT_WARN, label: '90th percentile: high volatility' }}
                     summary={'Percentile of NIFTY 500 20-day volatility against every earlier day since 2020. '
                       + `Latest: ${fmtVolPct(last.n500_vol_pct) ?? 'not yet computable'}.`} />
        </div>
        <p className="market-foot">
          Breadth: liquid mainboard stocks (≥ ₹1 cr/day), split / bonus-adjusted; {fmtNum(last.n_excluded)} excluded
          today for unadjustable breaks. Not a signal.
        </p>
      </Section>
      <Section id="market-recent" title="Last 20 sessions" level={2}>
        <DataTable dense caption="Market regime, last 20 sessions" columns={COLUMNS}
                   rows={data.slice(-20).reverse()} rowKey={(r) => r.trade_date} />
      </Section>
    </>
  )
}
