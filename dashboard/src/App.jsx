import { configured } from './supabaseClient'
import signals from './signals.json'
import SignalsOverview from './components/SignalsOverview'
import BuybackTable from './components/BuybackTable'
import DealsView from './components/DealsView'
import TrackedPositions from './components/TrackedPositions'
import ScanHistory from './components/ScanHistory'
import CompanySearch from './components/CompanySearch'
import UpcomingUnlocks from './components/UpcomingUnlocks'
import RightsPanel from './components/RightsPanel'
import CompanyPage from './components/CompanyPage'
import useHashRoute from './useHashRoute'

export default function App() {
  const route = useHashRoute()

  if (!configured) {
    return (
      <main className="banner-error" role="alert">
        Missing <code>VITE_SUPABASE_URL</code> / <code>VITE_SUPABASE_ANON_KEY</code>. Set them in <code>dashboard/.env</code>.
      </main>
    )
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="wordmark" href="#/">Market Intel</a>
          <span className="topbar-spacer" />
          <CompanySearch />
        </div>
      </header>
      <main className="content">
        {route.page === 'company' ? <CompanyPage symbol={route.symbol} /> : (
          <>
            <SignalsOverview signals={signals} />
            <RightsPanel />
            <UpcomingUnlocks />
            <BuybackTable />
            <DealsView />
            <TrackedPositions />
            <ScanHistory />
          </>
        )}
      </main>
      <footer className="app-footer">Read-only · data via Supabase · updated by scheduled refresh</footer>
    </>
  )
}
