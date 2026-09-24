import { useState } from 'react'
import { supabase } from '../supabaseClient'
import useLoad from '../lib/useLoad'
import { toggle } from '../lib/filters'
import { todayIso } from '../lib/format'
import { COMPANY_TABS, companyHref } from '../useHashRoute'
import CompanyHeader from './company/CompanyHeader'
import {
  CompanyDeals, EventsTable, FilingKpis, FilingsTable, Financials, SignalActivity, Snapshot, UpcomingEvents,
} from './company/CompanySections'
import Section from './ui/Section'
import Tabs from './ui/Tabs'
import Chips from './ui/Chips'
import { EmptyState, ErrorNote } from './ui/States'
import { Loading, Skeleton, SkeletonStats, SkeletonTable } from './ui/Skeleton'

const all = async (queries) => {
  const res = await Promise.all(queries)
  const err = res.find((r) => r.error)
  if (err) throw err.error
  return res
}

// Header: identity + snapshot (the Financials tab reads its history too) + tab counts.
async function loadHeader(symbol) {
  const [co, snap, fil, deals] = await all([
    supabase.from('companies').select('*').eq('symbol', symbol).maybeSingle(),
    supabase.from('company_snapshot').select('*').eq('symbol', symbol).maybeSingle(),
    supabase.from('filings').select('seq_id', { count: 'exact', head: true }).eq('symbol', symbol),
    supabase.from('market_deals').select('id', { count: 'exact', head: true }).eq('symbol', symbol),
  ])
  return { company: co.data, snap: snap.data, filings: fil.count ?? 0, deals: deals.count ?? 0 }
}

function TabLoading({ label, cols = 4 }) {
  return <Loading label={label}><SkeletonTable rows={6} cols={cols} /></Loading>
}

function OverviewTab({ symbol, snap }) {
  const { loading, error, data } = useLoad(async () => {
    const [kp, bb, cand, ev] = await all([
      supabase.from('company_kpis').select('id,kpi,value,unit,value_cr,as_of,quote,disclosed_at,filings(attachment_url,category)')
        .eq('symbol', symbol).order('disclosed_at', { ascending: false }).limit(80),
      supabase.from('buybacks').select('*').eq('symbol', symbol).order('record_date', { ascending: false }),
      supabase.from('candidates').select('signal_name,score,created_at').eq('symbol', symbol)
        .order('created_at', { ascending: false }).limit(20),
      supabase.from('corporate_events').select('id,event_type,event_date').eq('symbol', symbol)
        .gte('event_date', todayIso()).order('event_date'),
    ])
    return { kpis: kp.data || [], buybacks: bb.data || [], candidates: cand.data || [], upcoming: ev.data || [] }
  }, [symbol])

  return (
    <>
      <Snapshot snap={snap} />
      {loading ? <div className="section"><Loading label="Loading filings and activity"><Skeleton lines={4} /></Loading></div>
        : error ? <ErrorNote what="filing metrics and signal activity" message={error} />
        : (
          <>
            <FilingKpis kpis={data.kpis} />
            <SignalActivity buybacks={data.buybacks} candidates={data.candidates} />
            <UpcomingEvents events={data.upcoming} />
          </>
        )}
    </>
  )
}

function EventsTab({ symbol }) {
  const { loading, error, data } = useLoad(async () => {
    const [ev, ipo] = await all([
      supabase.from('corporate_events').select('*').eq('symbol', symbol)
        .order('event_date', { ascending: false }).limit(60),
      supabase.from('ipos').select('*').eq('symbol', symbol).order('listing_date', { ascending: false }).limit(1),
    ])
    return { events: ev.data || [], ipo: (ipo.data || [])[0] }
  }, [symbol])
  if (loading) return <TabLoading label="Loading events" />
  if (error) return <ErrorNote what="events" message={error} />
  return <EventsTable events={data.events} ipo={data.ipo} />
}

function FilingsTab({ symbol }) {
  const [cats, setCats] = useState(() => new Set())
  const { loading, error, data } = useLoad(() => supabase.from('filings')
    .select('seq_id,category,subject,disclosed_at,attachment_url')
    .eq('symbol', symbol).order('disclosed_at', { ascending: false }).limit(50), [symbol])
  if (loading) return <TabLoading label="Loading filings" />
  if (error) return <ErrorNote what="filings" message={error} />
  const categories = [...new Set(data.map((f) => f.category).filter(Boolean))].sort()
  const rows = cats.size ? data.filter((f) => cats.has(f.category)) : data
  return (
    <Section id="filings" title="Filings" meta={`latest ${data.length} · NSE announcements, material categories`}>
      {categories.length > 1 && (
        <div className="chips">
          <Chips label="Category" options={categories.map((c) => [c, c])} selected={cats}
                 onToggle={(v) => setCats((s) => toggle(s, v))} />
        </div>
      )}
      <FilingsTable filings={rows} />
    </Section>
  )
}

function DealsTab({ symbol }) {
  const { loading, error, data } = useLoad(() => supabase.from('market_deals').select('*').eq('symbol', symbol)
    .order('deal_date', { ascending: false }).limit(50), [symbol])
  if (loading) return <TabLoading label="Loading deals" cols={5} />
  if (error) return <ErrorNote what="deals" message={error} />
  return <CompanyDeals deals={data} />
}

const TAB_LABEL = { overview: 'Overview', financials: 'Financials', events: 'Events', filings: 'Filings', deals: 'Deals' }

export default function CompanyPage({ symbol, tab }) {
  const head = useLoad(() => loadHeader(symbol), [symbol])

  if (head.loading && !head.data) {
    return (
      <div className="content">
        <Loading label={`Loading ${symbol}`}>
          <Skeleton lines={2} width="40%" />
          <div className="stack-top"><SkeletonStats n={12} /></div>
        </Loading>
      </div>
    )
  }
  if (head.error) return <div className="content"><ErrorNote what={symbol} message={head.error} /></div>
  const { company: c, snap, filings, deals } = head.data
  if (!c) {
    return (
      <div className="content">
        <h1 className="page-title">{symbol}</h1>
        <EmptyState title="No NSE company with this symbol." hint="Try the search box (press /)." />
      </div>
    )
  }

  const tabs = COMPANY_TABS
    .filter((id) => id !== 'deals' || deals > 0 || tab === 'deals')
    .map((id) => ({ id, label: TAB_LABEL[id], href: companyHref(c.symbol, id), count: id === 'filings' ? filings : null }))

  return (
    <>
      <div className="co-sticky">
        <div className="co-inner">
          <CompanyHeader company={c} snap={snap}>
            <Tabs label={`${c.name || c.symbol} sections`} tabs={tabs} active={tab} />
          </CompanyHeader>
        </div>
      </div>
      <div className="content co-body" key={symbol}>
        {tab === 'financials' ? <Financials history={snap?.history} />
          : tab === 'events' ? <EventsTab symbol={symbol} />
          : tab === 'filings' ? <FilingsTab symbol={symbol} />
          : tab === 'deals' ? <DealsTab symbol={symbol} />
          : <OverviewTab symbol={symbol} snap={snap} />}
      </div>
    </>
  )
}
