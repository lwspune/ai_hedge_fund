import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import { fmtDate } from '../lib/format'
import CompanyHeader from './company/CompanyHeader'
import {
  CompanyDeals, EventsTable, FilingKpis, FilingsTable, Financials, SignalActivity, Snapshot, UpcomingEvents,
} from './company/CompanySections'
import Section from './ui/Section'
import { ErrorNote } from './ui/States'
import { Loading, Skeleton, SkeletonStats } from './ui/Skeleton'

async function loadCompany(symbol) {
  const res = await Promise.all([
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
  const err = res.find((r) => r.error)
  if (err) throw err.error
  const [co, snap, ev, ipo, bb, cand, deals, fil, kp] = res.map((r) => r.data)
  return {
    company: co, snap, events: ev || [], ipo: (ipo || [])[0], buybacks: bb || [],
    candidates: cand || [], deals: deals || [], filings: fil || [], kpis: kp || [],
  }
}

export default function CompanyPage({ symbol }) {
  const { loading, error, data } = useLoad(() => loadCompany(symbol), [symbol])

  if (loading) {
    return (
      <Loading label={`Loading ${symbol}`}>
        <Skeleton lines={2} width="40%" />
        <div className="stack-top"><SkeletonStats n={12} /></div>
      </Loading>
    )
  }
  if (error) return <ErrorNote what={symbol} message={error} />
  const { company: c, snap, events, ipo, buybacks, candidates, deals, filings, kpis } = data
  if (!c) return <p className="empty-title">No NSE company with symbol <code>{symbol}</code>.</p>

  return (
    <>
      <CompanyHeader company={c} snap={snap} />
      <Snapshot snap={snap} />
      <FilingKpis kpis={kpis} />
      <SignalActivity buybacks={buybacks} candidates={candidates} />
      <UpcomingEvents events={events} />
      <EventsTable events={events} ipo={ipo} />
      <Financials history={snap?.history} />
      <Section id="filings" title="Filings" meta={filings.length ? `latest ${filings.length} · since ${fmtDate(filings.at(-1).disclosed_at)}` : null}>
        <FilingsTable filings={filings} />
      </Section>
      {deals.length > 0 && <CompanyDeals deals={deals} />}
    </>
  )
}
