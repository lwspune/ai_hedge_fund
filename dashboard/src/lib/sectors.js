// Sector indices (docs/SECTOR_INDICES_SPEC.md): the sector index a stock is measured against, and the
// latest-day sector table (sector_regime). Measurements, not a rotation signal.
import { supabase } from '../supabaseClient'

const N500 = '^CRSLDX'

// "Nifty Bank" · "Nifty India Manufacturing (fallback)" · "NIFTY 500" — never the raw ticker.
export function sectorLabel(r) {
  const idx = r?.sector_index
  if (!idx) return '—'
  if (idx === N500) return r.sector_is_fallback ? 'NIFTY 500 (no sector index yet)' : 'NIFTY 500'
  return r.sector_is_fallback ? `${idx} (fallback)` : idx
}

// Sorted by name, never by return: the table describes sectors, it doesn't rank them.
export async function loadSectors() {
  const { data, error } = await supabase.from('sector_regime').select('*').order('index_name')
  if (error) throw error
  return data || []
}
