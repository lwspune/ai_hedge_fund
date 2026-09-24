import { DATA_TABS, dataHref } from '../useHashRoute'
import Tabs from '../components/ui/Tabs'
import BuybackTable from '../components/BuybackTable'
import DealsView from '../components/DealsView'
import ScanHistory from '../components/ScanHistory'
import TrackedPositions from '../components/TrackedPositions'

const LABELS = { deals: 'Deals', buybacks: 'Buybacks', positions: 'Positions', scans: 'Scans' }
const VIEWS = { deals: DealsView, buybacks: BuybackTable, positions: TrackedPositions, scans: ScanHistory }

export default function Data({ tab }) {
  const View = VIEWS[tab] || DealsView
  return (
    <>
      <h1 className="page-title">Data</h1>
      <Tabs label="Data tables" active={tab}
            tabs={DATA_TABS.map((id) => ({ id, label: LABELS[id], href: dataHref(id) }))} />
      <div className="tab-panel">
        <View />
      </div>
    </>
  )
}
