import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'

const CLEAR_AFTER_MS = 8000

export const describeBuybackRefresh = (d) =>
  `Scanned ${d.scanned ?? 0} ids, ${d.upserted ?? 0} new${d.found?.length ? ` (${d.found.join(', ')})` : ''}.`

export const describeDealsRefresh = (d) =>
  `Refreshed ${d.inserted ?? 0} deals${d.dates?.length ? ` for ${d.dates.join(', ')}` : ''}.`

// Calls one of the two read-side edge functions (refresh-deals / refresh-buybacks), then
// `onDone`. `describe(data)` turns the function's JSON into the one-line status message,
// which clears itself after 8 s or on the next call.
export default function useEdgeRefresh(fn, describe, onDone) {
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!status) return
    const t = setTimeout(() => setStatus(null), CLEAR_AFTER_MS)
    return () => clearTimeout(t)
  }, [status])

  async function refresh() {
    setBusy(true)
    setStatus(null)
    setError(null)
    try {
      const { data, error } = await supabase.functions.invoke(fn, { method: 'POST' })
      if (error) throw error
      if (data?.ok === false) throw new Error(data.error || 'refresh failed')
      setStatus(describe(data))
      if (onDone) await onDone()
    } catch (e) {
      console.error(`${fn} failed`, e)
      setError(e?.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  return { busy, status, error, refresh }
}
