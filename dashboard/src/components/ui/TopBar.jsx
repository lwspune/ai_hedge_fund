import CompanySearch from '../CompanySearch'
import InfoPopover from './InfoPopover'

const NAV = [
  ['desk', 'Desk', '#/'],
  ['signals', 'Signals', '#/signals'],
  ['data', 'Data', '#/data'],
]

// Freshness dot: green when every source is within its rule, amber when any is stale.
function FreshnessDot({ items }) {
  if (!items) return <span className="fresh-dot is-unknown" aria-hidden="true" />
  const stale = items.filter((i) => i.stale)
  const label = stale.length
    ? `Data freshness: ${stale.map((i) => i.label).join(', ')} stale`
    : 'Data freshness: all sources fresh'
  return (
    <InfoPopover label={label} align="right"
                 icon={<span className={`fresh-dot ${stale.length ? 'is-stale' : 'is-fresh'}`} aria-hidden="true" />}>
      <span className="fresh-list">
        {items.map((i) => (
          <span key={i.key} className={i.stale ? 'tone-warn' : undefined}>
            {i.label} {i.text}{i.stale ? ' (stale)' : ''}
          </span>
        ))}
      </span>
    </InfoPopover>
  )
}

export default function TopBar({ route, freshness }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="wordmark" href="#/">Market Intel</a>
        <nav className="topnav" aria-label="Primary">
          {NAV.map(([page, label, href]) => (
            <a key={page} href={href} aria-current={route.page === page ? 'page' : undefined}>{label}</a>
          ))}
        </nav>
        <span className="topbar-spacer" />
        <CompanySearch />
        <FreshnessDot items={freshness} />
      </div>
    </header>
  )
}
