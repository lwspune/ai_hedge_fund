import BuybackTable from '../components/BuybackTable'
import DealsView from '../components/DealsView'
import ScanHistory from '../components/ScanHistory'
import TrackedPositions from '../components/TrackedPositions'

export default function Data() {
  return (
    <>
      <h1 className="page-title">Data</h1>
      <DealsView />
      <BuybackTable />
      <TrackedPositions />
      <ScanHistory />
    </>
  )
}
