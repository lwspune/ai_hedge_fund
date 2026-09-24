import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'

const num = (v, d = 0) =>
  v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d })
const pct = (v) => (v == null ? '—' : Number(v).toFixed(2) + '%')

const EVENT_LABEL = {
  bonus: 'Bonus', split: 'Split', consolidation: 'Consolidation', rights: 'Rights',
  dividend: 'Dividend', buyback: 'Buyback', demerger: 'Demerger', fo_ban: 'F&O ban',
  ipo_listing: 'IPO listing', anchor_lockin_30: 'Anchor lock-in ends (50%)',
  anchor_lockin_90: 'Anchor lock-in ends (rest)',
}

function eventDetail(e) {
  const d = e.details || {}
  switch (e.event_type) {
    case 'bonus': return d.ratio
    case 'split':
    case 'consolidation': return `FV ₹${d.from_fv} → ₹${d.to_fv}`
    case 'rights': return `${d.ratio} @ ₹${d.premium} premium`
    case 'dividend': return `₹${d.amount}/sh${d.special ? ' (incl. special)' : ''}${d.interim ? ' · interim' : ''}`
    case 'ipo_listing': return `issue ₹${d.issue_price} · ${d.board}`
    case 'anchor_lockin_30':
    case 'anchor_lockin_90': return d.anchor_shares ? `${num(d.anchor_shares)} anchor shares` : ''
    default: return ''
  }
}

function Ratio({ label, value }) {
  return (
    <div className="ratio">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function SeriesTable({ caption, rows, cols }) {
  if (!rows || rows.length === 0) return <p className="empty">No {caption.toLowerCase()} data.</p>
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {rows.map((r) => <th scope="col" key={r.period} className="r">{r.period}</th>)}
          </tr>
        </thead>
        <tbody>
          {cols.map(([key, label, fmt]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              {rows.map((r) => <td key={r.period} className="r">{fmt(r[key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const money = (k) => (k.value_cr != null ? `₹${num(k.value_cr)} cr` : `${num(k.value, 2)} ${k.unit || ''}`)

function Source({ k }) {
  const url = k.filings?.attachment_url
  const when = k.disclosed_at.slice(0, 10)
  return url
    ? <a href={url} target="_blank" rel="noopener noreferrer"
         aria-label={`Source filing from ${when} (opens in a new tab)`}>{when} ↗</a>
    : <span className="dim">{when}</span>
}

// F3: KPIs extracted from filing PDFs by rule (rule_v1). Every value shows the exact quote it came
// from and links its source filing, so any number can be checked.
function FilingKpis({ kpis }) {
  const by = (kpi) => kpis.filter((k) => k.kpi === kpi)
  const book = by('order_book'), wins = by('order_win_value'), util = by('capacity_utilisation')
  const guide = by('guidance').slice(0, 6)
  if (!kpis.length) return null
  return (
    <section className="panel" aria-labelledby="kpis-h">
      <h2 id="kpis-h">From filings <span className="muted">· extracted by rule from presentations, call transcripts, press releases &amp; order disclosures — check the quote</span></h2>
      <dl className="ratios">
        {book[0] && <div className="ratio"><dt>Order book{book[0].as_of ? ` (as on ${book[0].as_of})` : ''}</dt><dd>{money(book[0])}</dd></div>}
        {util[0] && <div className="ratio"><dt>Capacity utilisation</dt><dd>{num(util[0].value)}%</dd></div>}
        {wins.length > 0 && <div className="ratio"><dt>Order wins disclosed (latest {Math.min(wins.length, 8)})</dt>
          <dd>₹{num(wins.slice(0, 8).reduce((a, k) => a + (k.value_cr || 0), 0))} cr</dd></div>}
      </dl>
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">Metric</th><th scope="col" className="r">Value</th><th scope="col">Quote</th><th scope="col">Source</th></tr></thead>
          <tbody>
            {[...book.slice(0, 4), ...util.slice(0, 2), ...wins.slice(0, 8)].map((k) => (
              <tr key={k.id}>
                <td>{k.kpi.replace(/_/g, ' ')}</td>
                <td className="r">{k.kpi === 'capacity_utilisation' ? `${num(k.value)}%` : money(k)}</td>
                <td className="dim wrap">“{k.quote}”</td>
                <td><Source k={k} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {guide.length > 0 && (
        <>
          <h3 className="small">Management guidance (quotes)</h3>
          <ul className="plain">
            {guide.map((k) => <li key={k.id}>“{k.quote}” — <Source k={k} /></li>)}
          </ul>
        </>
      )}
    </section>
  )
}

export default function CompanyPage({ symbol }) {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let live = true
    setState({ loading: true })
    ;(async () => {
      const [co, snap, ev, ipo, bb, cand, deals, fil, kp] = await Promise.all([
        supabase.from('companies').select('*').eq('symbol', symbol).maybeSingle(),
        supabase.from('company_snapshot').select('*').eq('symbol', symbol).maybeSingle(),
        supabase.from('corporate_events').select('*').eq('symbol', symbol)
          .order('event_date', { ascending: false }).limit(60),
        supabase.from('ipos').select('*').eq('symbol', symbol).order('listing_date', { ascending: false }).limit(1),
        supabase.from('buybacks').select('*').eq('symbol', symbol).order('record_date', { ascending: false }),
        supabase.from('candidates').select('signal_name,score,created_at').eq('symbol', symbol)
          .order('created_at', { ascending: false }).limit(20),
        supabase.from('market_deals').select('*').eq('symbol', symbol)
          .order('deal_date', { ascending: false }).limit(15),
        supabase.from('filings').select('seq_id,category,subject,disclosed_at,attachment_url')
          .eq('symbol', symbol).order('disclosed_at', { ascending: false }).limit(25),
        supabase.from('company_kpis').select('id,kpi,value,unit,value_cr,as_of,quote,disclosed_at,filings(attachment_url,category)')
          .eq('symbol', symbol).order('disclosed_at', { ascending: false }).limit(80),
      ])
      const err = [co, snap, ev, ipo, bb, cand, deals, fil, kp].find((r) => r.error)
      if (!live) return
      if (err) setState({ loading: false, error: err.error.message })
      else setState({
        loading: false, company: co.data, snap: snap.data, events: ev.data || [],
        ipo: (ipo.data || [])[0], buybacks: bb.data || [], candidates: cand.data || [],
        deals: deals.data || [], filings: fil.data || [], kpis: kp.data || [],
      })
    })()
    return () => { live = false }
  }, [symbol])

  const back = <a href="#/" className="back">← All signals</a>
  if (state.loading) return <>{back}<div className="banner">Loading {symbol}…</div></>
  if (state.error) return <>{back}<div className="banner error" role="alert">⚠ {state.error}</div></>
  const { company: c, snap: s, events, ipo, buybacks, candidates, deals, filings, kpis } = state
  if (!c) return <>{back}<div className="banner">No NSE company with symbol <code>{symbol}</code>.</div></>
  const h = s?.history || {}
  const upcoming = events.filter((e) => e.event_date >= new Date().toISOString().slice(0, 10))

  return (
    <>
      {back}
      <header className="co-head">
        <h1>{c.name || c.symbol} <code className="co-sym">{c.symbol}</code></h1>
        <p className="subtitle">
          {[...new Set([s?.sector, s?.industry, s?.basic_industry].filter(Boolean))].join(' › ') || c.industry || 'Industry unknown'}
          {' · '}{c.series || '—'} · ISIN {c.isin || '—'}
          {c.listing_date && <> · listed {c.listing_date}</>}
          {c.status === 'delisted' && <> · <span className="status">delisted {c.delisted_on}</span></>}
        </p>
        {c.indices?.length > 0 && (
          <p className="tags" aria-label="Index membership">
            {c.indices.map((i) => <span key={i} className="tag">{i}</span>)}
          </p>
        )}
      </header>

      <section className="panel" aria-labelledby="ratios-h">
        <h2 id="ratios-h">Snapshot <span className="muted">· screener.in{s ? `, ${s.consolidated ? 'consolidated' : 'standalone'}, fetched ${s.fetched_at.slice(0, 10)}` : ''}</span></h2>
        {!s ? <p className="empty">Not fetched yet — run <code>scripts/refresh_fundamentals.py</code>.</p> : (
          <dl className="ratios">
            <Ratio label="Market cap" value={`₹${num(s.market_cap_cr)} cr`} />
            <Ratio label="Price" value={`₹${num(s.price, 2)}`} />
            <Ratio label="52w high / low" value={`${num(s.high_52w, 2)} / ${num(s.low_52w, 2)}`} />
            <Ratio label="P/E" value={num(s.pe, 1)} />
            <Ratio label="Book value" value={`₹${num(s.book_value, 2)}`} />
            <Ratio label="Dividend yield" value={pct(s.dividend_yield)} />
            <Ratio label="ROCE" value={pct(s.roce)} />
            <Ratio label="ROE" value={pct(s.roe)} />
            <Ratio label="Debt / equity" value={s.debt_to_equity == null ? '—' : num(s.debt_to_equity, 2)} />
            <Ratio label="Revenue (TTM)" value={`₹${num(s.revenue_ttm)} cr`} />
            <Ratio label="Net profit (TTM)" value={`₹${num(s.net_profit_ttm)} cr`} />
            <Ratio label="Face value" value={`₹${num(s.face_value, 2)}`} />
          </dl>
        )}
      </section>

      {(buybacks.length > 0 || candidates.length > 0) && (
        <section className="panel" aria-labelledby="flags-h">
          <h2 id="flags-h">Signal activity <span className="muted">· where the scanner has flagged this stock</span></h2>
          <ul className="plain">
            {buybacks.map((b) => (
              <li key={b.id}>
                <span className="badge badge-edge">buyback_arb</span> {b.company} · ₹{num(b.buyback_price)} ·
                entitlement {pct(b.entitlement_small * 100)} · record {b.record_date || '—'} ·{' '}
                <span className={`status status-${b.status}`}>{b.status}</span>
              </li>
            ))}
            {candidates.map((k, i) => (
              <li key={i}><code>{k.signal_name}</code> · score {num(k.score, 3)} · {k.created_at.slice(0, 10)}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel" aria-labelledby="events-h">
        <h2 id="events-h">Events <span className="muted">· corporate actions, F&amp;O bans, IPO lock-ins</span></h2>
        {upcoming.length > 0 && (
          <p className="note">Upcoming: {upcoming.map((e) => `${EVENT_LABEL[e.event_type]} ${e.event_date}`).join(' · ')}</p>
        )}
        {events.length === 0 ? <p className="empty">No events recorded.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Date</th><th scope="col">Event</th><th scope="col">Detail</th><th scope="col">Record date</th></tr></thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td className="dim">{e.event_date}</td>
                    <td>{EVENT_LABEL[e.event_type] || e.event_type}</td>
                    <td className="dim">{eventDetail(e)}</td>
                    <td className="dim">{e.record_date || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {ipo && (
          <p className="dim small">
            IPO: {ipo.board} · issue ₹{num(ipo.issue_price, 2)} · listed {ipo.listing_date}
            {ipo.listing_close && <> · day-1 close ₹{num(ipo.listing_close, 2)} ({pct((ipo.listing_close / ipo.issue_price - 1) * 100)})</>}
          </p>
        )}
      </section>

      <section className="panel" aria-labelledby="annual-h">
        <h2 id="annual-h">Annual results <span className="muted">· ₹ crore</span></h2>
        <SeriesTable caption="Annual results" rows={h.annual}
          cols={[['revenue', 'Revenue', (v) => num(v)], ['net_profit', 'Net profit', (v) => num(v)],
                 ['opm', 'OPM %', pct], ['eps', 'EPS ₹', (v) => num(v, 2)]]} />
      </section>

      <section className="panel" aria-labelledby="qtr-h">
        <h2 id="qtr-h">Quarterly results <span className="muted">· ₹ crore</span></h2>
        <SeriesTable caption="Quarterly results" rows={h.quarterly}
          cols={[['revenue', 'Revenue', (v) => num(v)], ['net_profit', 'Net profit', (v) => num(v)],
                 ['opm', 'OPM %', pct], ['eps', 'EPS ₹', (v) => num(v, 2)]]} />
      </section>

      <section className="panel" aria-labelledby="shp-h">
        <h2 id="shp-h">Shareholding <span className="muted">· quarterly · public % ≈ retail proxy</span></h2>
        <SeriesTable caption="Shareholding pattern" rows={h.shareholding}
          cols={[['promoter', 'Promoters', pct], ['fii', 'FIIs', pct], ['dii', 'DIIs', pct],
                 ['public', 'Public', pct], ['holders', 'Shareholders', (v) => num(v)]]} />
      </section>

      <FilingKpis kpis={kpis} />

      <section className="panel" aria-labelledby="filings-h">
        <h2 id="filings-h">Filings <span className="muted">· NSE announcements (material categories)</span></h2>
        {filings.length === 0 ? <p className="empty">No filings indexed.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Date</th><th scope="col">Category</th><th scope="col">Subject</th><th scope="col">Document</th></tr></thead>
              <tbody>
                {filings.map((f) => (
                  <tr key={f.seq_id}>
                    <td className="dim">{f.disclosed_at.slice(0, 10)}</td>
                    <td>{f.category}</td>
                    <td className="dim wrap" title={f.subject}>{(f.subject || '').slice(0, 110)}</td>
                    <td>{f.attachment_url
                      ? <a href={f.attachment_url} target="_blank" rel="noopener noreferrer"
                           aria-label={`Open ${f.category} filing from ${f.disclosed_at.slice(0, 10)} (opens in a new tab)`}>PDF ↗</a>
                      : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {deals.length > 0 && (
        <section className="panel" aria-labelledby="codeals-h">
          <h2 id="codeals-h">Bulk / block deals <span className="muted">· informational (smart_money_deals is null)</span></h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Date</th><th scope="col">Client</th><th scope="col">Side</th><th scope="col" className="r">Qty</th><th scope="col" className="r">Price</th></tr></thead>
              <tbody>
                {deals.map((d) => (
                  <tr key={d.id}>
                    <td className="dim">{d.deal_date}</td>
                    <td className="dim" title={d.client}>{(d.client || '').slice(0, 34)}</td>
                    <td><span className={`side side-${(d.side || '').toLowerCase()}`}>{d.side}</span></td>
                    <td className="r">{num(d.qty)}</td>
                    <td className="r">{num(d.price, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
