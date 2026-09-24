import OpenBuybacks from '../components/OpenBuybacks'
import RightsPanel from '../components/RightsPanel'
import UpcomingUnlocks from '../components/UpcomingUnlocks'

function StatusStrip({ items }) {
  if (!items) return <p className="status-strip" aria-hidden="true">&nbsp;</p>
  return (
    <p className="status-strip">
      <span className="sr-only">Data freshness: </span>
      {items.map((i, n) => (
        <span key={i.key}>
          {n > 0 && <span aria-hidden="true"> · </span>}
          <span className={i.stale ? 'tone-warn' : undefined}>
            {i.label} {i.text}{i.stale && <span className="sr-only"> (stale)</span>}
          </span>
        </span>
      ))}
    </p>
  )
}

// Today: what to act on, what to avoid. Nothing else.
export default function Desk({ freshness }) {
  return (
    <>
      <h1 className="sr-only">Desk</h1>
      <StatusStrip items={freshness} />
      <div className="group" role="group" aria-labelledby="act-h">
        <h2 id="act-h" className="group-label">Act</h2>
        <OpenBuybacks />
        <RightsPanel />
      </div>
      <div className="group" role="group" aria-labelledby="avoid-h">
        <h2 id="avoid-h" className="group-label">Avoid</h2>
        <UpcomingUnlocks />
      </div>
    </>
  )
}
