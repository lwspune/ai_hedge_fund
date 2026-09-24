import {
  fmtCrValue, fmtDate, fmtInr, fmtNum, fmtPct, fmtPctPts, fmtQty, fmtRelative, todayIso,
} from '../../lib/format'
import { eventDetail, eventLabel } from '../../lib/events'
import { signalLabel } from '../../lib/signalLabels'
import Section from '../ui/Section'
import DataTable from '../ui/DataTable'
import { Stat, StatGrid } from '../ui/Stat'
import { Badge, SideBadge, StatusBadge } from '../ui/Badge'
import { EmptyState } from '../ui/States'

// ── Snapshot ──────────────────────────────────────────────────────────
export function Snapshot({ snap: s }) {
  return (
    <Section id="snapshot" title="Snapshot"
             meta={s ? `screener.in · ${s.consolidated ? 'consolidated' : 'standalone'} · fetched ${fmtDate(s.fetched_at)}` : null}>
      {!s ? <EmptyState title="Fundamentals not fetched yet."
                        hint={<>Run <code>python scripts/refresh_fundamentals.py --symbols …</code></>} />
        : (
          <StatGrid label="Snapshot">
            <Stat label="Market cap" value={fmtCrValue(s.market_cap_cr)} />
            <Stat label="Price" value={fmtInr(s.price)} />
            <Stat label="52w high / low" value={`${fmtNum(s.high_52w, 2)} / ${fmtNum(s.low_52w, 2)}`} />
            <Stat label="P/E" value={fmtNum(s.pe, 1)} />
            <Stat label="Book value" value={fmtInr(s.book_value)} />
            <Stat label="Dividend yield" value={fmtPctPts(s.dividend_yield, 2)} />
            <Stat label="ROCE" value={fmtPctPts(s.roce)} />
            <Stat label="ROE" value={fmtPctPts(s.roe)} />
            <Stat label="Debt / equity" value={fmtNum(s.debt_to_equity, 2)} />
            <Stat label="Revenue (TTM)" value={fmtCrValue(s.revenue_ttm)} />
            <Stat label="Net profit (TTM)" value={fmtCrValue(s.net_profit_ttm)} />
            <Stat label="Face value" value={fmtInr(s.face_value)} />
          </StatGrid>
        )}
    </Section>
  )
}

// ── From filings (F3 KPIs) ────────────────────────────────────────────
const FIN = [['gnpa', 'Gross NPA'], ['nnpa', 'Net NPA'], ['nim', 'NIM'], ['credit_cost', 'Credit cost'],
  ['pcr', 'PCR'], ['crar', 'CRAR'], ['casa', 'CASA'], ['roa', 'RoA']]
const KPI_LABEL = {
  order_book: 'Order book', order_win_value: 'Order win', capacity_utilisation: 'Capacity utilisation',
  guidance: 'Guidance', ...Object.fromEntries(FIN),
}

const kpiValue = (k) => (k.unit === '%' ? fmtPctPts(k.value, 2)
  : k.value_cr != null ? fmtCrValue(k.value_cr) : `${fmtNum(k.value, 2)} ${k.unit || ''}`.trim())

function Source({ k }) {
  const url = k.filings?.attachment_url
  const when = fmtDate(k.disclosed_at)
  return url
    ? <a href={url} target="_blank" rel="noopener noreferrer" className="nowrap"
         aria-label={`Source filing from ${when} (opens in a new tab)`}>{when} ↗</a>
    : <span className="t3 nowrap">{when}</span>
}

const KPI_COLUMNS = [
  { key: 'kpi', header: 'Metric', render: (k) => KPI_LABEL[k.kpi] || k.kpi },
  { key: 'value', header: 'Value', align: 'right', render: kpiValue },
  { key: 'quote', header: 'Quote', render: (k) => <span className="t2 cell-wrap">“{k.quote}”</span> },
  { key: 'source', header: 'Source', render: (k) => <Source k={k} /> },
]

export function FilingKpis({ kpis }) {
  if (!kpis?.length) return null
  const by = (kpi) => kpis.filter((k) => k.kpi === kpi)
  const book = by('order_book'), wins = by('order_win_value'), util = by('capacity_utilisation')
  const guide = by('guidance').slice(0, 6)
  const fin = FIN.map(([k, label]) => [label, by(k)[0]]).filter(([, v]) => v)
  const rows = [...book.slice(0, 4), ...util.slice(0, 2), ...fin.map(([, k]) => k), ...wins.slice(0, 8)]
  const nWins = Math.min(wins.length, 8)
  return (
    <Section id="kpis" title="From filings"
             info="Extracted by rule from filing PDFs; every value keeps its quote and source. Check the quote.">
      <StatGrid label="Latest values from filings">
        {book[0] && <Stat label="Order book" value={kpiValue(book[0])} sub={book[0].as_of ? `as on ${fmtDate(book[0].as_of)}` : null} />}
        {util[0] && <Stat label="Capacity utilisation" value={fmtPctPts(util[0].value, 0)} />}
        {fin.map(([label, k]) => <Stat key={label} label={label} value={fmtPctPts(k.value, 2)} title={`“${k.quote}”`} />)}
        {nWins > 0 && <Stat label="Order wins" value={fmtCrValue(wins.slice(0, 8).reduce((a, k) => a + (k.value_cr || 0), 0))} sub={`latest ${nWins}`} />}
      </StatGrid>
      {rows.length > 0 && (
        <div className="stack-top">
          <DataTable dense caption="Filing metrics with quotes" columns={KPI_COLUMNS} rows={rows} rowKey={(k) => k.id} />
        </div>
      )}
      {guide.length > 0 && (
        <>
          <h3 className="subhead">Management guidance</h3>
          <ul className="quote-list">
            {guide.map((k) => <li key={k.id}>“{k.quote}” <span className="src"><Source k={k} /></span></li>)}
          </ul>
        </>
      )}
    </Section>
  )
}

// ── Signal activity ───────────────────────────────────────────────────
export function SignalActivity({ buybacks, candidates }) {
  if (!buybacks?.length && !candidates?.length) return null
  return (
    <Section id="activity" title="Signal activity" info="Where the scanner has flagged this stock.">
      <ul className="line-list">
        {buybacks.map((b) => (
          <li key={`b${b.id}`}>
            <Badge tone="pos">{signalLabel('buyback_arb')}</Badge>
            <span className="num">{fmtInr(b.buyback_price)}</span>
            <span>entitlement <span className="num">{fmtPct(b.entitlement_small, 0)}</span></span>
            <span>record {fmtDate(b.record_date)}</span>
            <StatusBadge status={b.status} />
          </li>
        ))}
        {candidates.map((k, i) => (
          <li key={`c${i}`}>
            <Badge tone="neutral">{signalLabel(k.signal_name)}</Badge>
            <span>score <span className="num">{fmtNum(k.score, 3)}</span></span>
            <span>{fmtDate(k.created_at)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

// ── Events ────────────────────────────────────────────────────────────
export function UpcomingEvents({ events }) {
  const today = todayIso()
  const upcoming = (events || []).filter((e) => e.event_date >= today)
    .sort((a, b) => a.event_date.localeCompare(b.event_date))
  if (!upcoming.length) return null
  return (
    <Section id="upcoming" title="Upcoming events">
      <ul className="line-list">
        {upcoming.map((e) => (
          <li key={e.id}>
            <Badge tone="neutral">{eventLabel(e.event_type)}</Badge>
            <span>{fmtDate(e.event_date)}</span>
            <span className="t3">{fmtRelative(e.event_date)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

const EVENT_COLUMNS = [
  { key: 'event_date', header: 'Date', nowrap: true, sortable: true, render: (e) => fmtDate(e.event_date) },
  { key: 'event_type', header: 'Event', render: (e) => eventLabel(e.event_type) },
  { key: 'detail', header: 'Detail', render: (e) => <span className="t2">{eventDetail(e) || '—'}</span> },
  { key: 'record_date', header: 'Record date', nowrap: true, render: (e) => fmtDate(e.record_date) },
]

export function EventsTable({ events, ipo }) {
  return (
    <Section id="events" title="Events" info="Corporate actions, F&O bans and IPO lock-in expiries.">
      <DataTable caption="Corporate events" columns={EVENT_COLUMNS} rows={events} rowKey={(e) => e.id}
                 emptyText="No events recorded." />
      {ipo && (
        <p className="small t2 stack-top">
          IPO · {ipo.board === 'sme' ? 'SME' : 'Mainboard'} · issue {fmtInr(ipo.issue_price)} · listed {fmtDate(ipo.listing_date)}
          {ipo.listing_close != null && <> · day-1 close {fmtInr(ipo.listing_close)} ({fmtPct(ipo.listing_close / ipo.issue_price - 1)})</>}
        </p>
      )}
    </Section>
  )
}

// ── Financials ────────────────────────────────────────────────────────
function SeriesTable({ caption, rows, metrics }) {
  const list = [...(rows || [])]
  const columns = [
    { key: 'metric', header: 'Metric', render: (m) => m.label },
    ...list.map((r) => ({ key: r.period, header: r.period, align: 'right', render: (m) => m.fmt(r[m.key]) })),
  ]
  return (
    <DataTable caption={caption} columns={columns} rows={list.length ? metrics : []} rowKey={(m) => m.key}
               stickyFirstCol scrollEnd emptyText={`No ${caption.toLowerCase()} data.`} />
  )
}

const RESULTS = [
  { key: 'revenue', label: 'Revenue', fmt: (v) => fmtNum(v) },
  { key: 'net_profit', label: 'Net profit', fmt: (v) => fmtNum(v) },
  { key: 'opm', label: 'OPM %', fmt: (v) => fmtPctPts(v, 0) },
  { key: 'eps', label: 'EPS ₹', fmt: (v) => fmtNum(v, 2) },
]
const HOLDING = [
  { key: 'promoter', label: 'Promoters', fmt: (v) => fmtPctPts(v, 2) },
  { key: 'fii', label: 'FIIs', fmt: (v) => fmtPctPts(v, 2) },
  { key: 'dii', label: 'DIIs', fmt: (v) => fmtPctPts(v, 2) },
  { key: 'public', label: 'Public', fmt: (v) => fmtPctPts(v, 2) },
  { key: 'holders', label: 'Shareholders', fmt: (v) => fmtQty(v) },
]

export function Financials({ history }) {
  const h = history || {}
  return (
    <>
      <Section id="annual" title="Annual results" meta="₹ crore">
        <SeriesTable caption="Annual" rows={h.annual} metrics={RESULTS} />
      </Section>
      <Section id="quarterly" title="Quarterly results" meta="₹ crore">
        <SeriesTable caption="Quarterly" rows={h.quarterly} metrics={RESULTS} />
      </Section>
      <Section id="shareholding" title="Shareholding" meta="% of equity · public ≈ retail"
               info="Quarterly shareholding pattern from screener.in.">
        <SeriesTable caption="Shareholding" rows={h.shareholding} metrics={HOLDING} />
      </Section>
    </>
  )
}

// ── Filings ───────────────────────────────────────────────────────────
const FILING_COLUMNS = [
  { key: 'disclosed_at', header: 'Date', nowrap: true, sortable: true, render: (f) => fmtDate(f.disclosed_at) },
  { key: 'category', header: 'Category' },
  { key: 'subject', header: 'Subject', render: (f) => <span className="t2 cell-wrap" title={f.subject}>{f.subject}</span> },
  {
    key: 'doc', header: 'Document', nowrap: true,
    render: (f) => (f.attachment_url
      ? <a href={f.attachment_url} target="_blank" rel="noopener noreferrer"
           aria-label={`Open ${f.category} filing from ${fmtDate(f.disclosed_at)} (opens in a new tab)`}>PDF ↗</a>
      : null),
  },
]

// ── Deals ─────────────────────────────────────────────────────────────
const COMPANY_DEAL_COLUMNS = [
  { key: 'deal_date', header: 'Date', nowrap: true, sortable: true, render: (d) => fmtDate(d.deal_date) },
  { key: 'client', header: 'Client', render: (d) => <span className="cell-clip" title={d.client}>{d.client}</span> },
  { key: 'side', header: 'Side', render: (d) => <SideBadge side={d.side} /> },
  { key: 'qty', header: 'Qty', align: 'right', sortable: true, render: (d) => fmtQty(d.qty) },
  { key: 'price', header: 'Price', align: 'right', render: (d) => fmtInr(d.price) },
]

export function FilingsTable({ filings }) {
  return (
    <DataTable caption="Filings" columns={FILING_COLUMNS} rows={filings} rowKey={(f) => f.seq_id}
               emptyText="No filings indexed." />
  )
}

export function CompanyDeals({ deals }) {
  return (
    <Section id="co-deals" title="Bulk and block deals"
             info="Informational: bulk/block following is a null signal.">
      <DataTable dense caption="Bulk and block deals" columns={COMPANY_DEAL_COLUMNS} rows={deals}
                 rowKey={(d) => d.id} emptyText="No bulk or block deals." />
    </Section>
  )
}
