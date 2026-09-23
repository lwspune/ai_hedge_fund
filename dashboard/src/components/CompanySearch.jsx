import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import { companyHref } from '../useHashRoute'

// PostgREST `or` filter syntax treats , ( ) as separators: strip them (and %/*) from input.
const clean = (q) => q.replace(/[^A-Za-z0-9&. -]/g, '').trim().slice(0, 40)

export default function CompanySearch() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    const term = clean(q)
    if (term.length < 2) {
      setResults([])
      return
    }
    const t = setTimeout(async () => {
      const { data, error } = await supabase
        .from('companies')
        .select('symbol,name,status,industry')
        .or(`symbol.ilike.${term}*,name.ilike.*${term}*`)
        .order('status')
        .order('symbol')
        .limit(8)
      setError(error ? error.message : null)
      setResults(data || [])
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  return (
    <section className="panel" aria-labelledby="search-h">
      <h2 id="search-h">Companies <span className="muted">· every NSE-listed equity</span></h2>
      <label htmlFor="company-q" className="sr-only">Search by symbol or company name</label>
      <input
        id="company-q"
        className="search"
        type="search"
        placeholder="Symbol or name — e.g. TCS, Nectar…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoComplete="off"
      />
      {error && <p className="note error" role="alert">Search failed: {error}</p>}
      {results.length > 0 && (
        <ul className="search-results" aria-label="Matching companies">
          {results.map((c) => (
            <li key={c.symbol}>
              <a href={companyHref(c.symbol)}>
                <code>{c.symbol}</code> <span className="dim">{c.name}</span>
                {c.status === 'delisted' && <span className="status">delisted</span>}
              </a>
            </li>
          ))}
        </ul>
      )}
      {clean(q).length >= 2 && results.length === 0 && !error && (
        <p className="empty">No match.</p>
      )}
    </section>
  )
}
