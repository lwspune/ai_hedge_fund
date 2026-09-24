import { useCallback, useEffect, useRef, useState } from 'react'

// Per-section data loading: each section fetches on its own so siblings never block each other.
// `load` returns the data, or a supabase { data, error } result, or throws. It re-runs when a
// value in `deps` changes or on reload(). Updates after unmount or a newer load are dropped.
export default function useLoad(load, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null })
  const [tick, setTick] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.resolve()
      .then(() => loadRef.current())
      .then((res) => {
        if (res && typeof res === 'object' && 'error' in res && 'data' in res) {
          if (res.error) throw res.error
          return res.data
        }
        return res
      })
      .then((data) => { if (live) setState({ loading: false, data, error: null }) })
      .catch((e) => {
        console.error('load failed', e)
        if (live) setState({ loading: false, data: null, error: e?.message || String(e) })
      })
    return () => { live = false }
    // deps is the caller's dependency list, spread on purpose
  }, [...deps, tick]) // oxlint-disable-line react/exhaustive-deps

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}
