import { configured } from './supabaseClient'
import useHashRoute from './useHashRoute'
import useLoad from './lib/useLoad'
import { loadFreshness } from './lib/queries'
import { freshnessItems } from './lib/freshness'
import TopBar from './components/ui/TopBar'
import CompanyPage from './components/CompanyPage'
import Desk from './views/Desk'
import Signals from './views/Signals'
import Data from './views/Data'

function Shell() {
  const route = useHashRoute()
  const fresh = useLoad(loadFreshness, [])
  const freshness = fresh.data ? freshnessItems(fresh.data) : null

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <TopBar route={route} freshness={freshness} />
      <main id="main" className="content" tabIndex={-1}>
        {route.page === 'company' ? <CompanyPage symbol={route.symbol} />
          : route.page === 'signals' ? <Signals />
          : route.page === 'data' ? <Data />
          : <Desk freshness={freshness} />}
      </main>
      <footer className="app-footer">Read-only · data via Supabase · updated by scheduled refresh</footer>
    </>
  )
}

export default function App() {
  if (!configured) {
    return (
      <main className="banner-error" role="alert">
        Missing <code>VITE_SUPABASE_URL</code> / <code>VITE_SUPABASE_ANON_KEY</code>. Set them in <code>dashboard/.env</code>.
      </main>
    )
  }
  return <Shell />
}
