import { useEffect, useId, useRef, useState } from 'react'
import { supabase } from '../supabaseClient'
import { companyHref } from '../useHashRoute'
import { Badge } from './ui/Badge'

// PostgREST `or` filter syntax treats , ( ) as separators: strip them (and %/*) from input.
const clean = (q) => q.replace(/[^A-Za-z0-9&. -]/g, '').trim().slice(0, 40)

const typing = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)

// Company combobox: 250 ms debounce, >= 2 chars, 8 results. Arrow keys move, Enter opens,
// Escape closes, '/' anywhere focuses it. Below 640px it collapses to an icon button.
export default function CompanySearch() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [expanded, setExpanded] = useState(false)
  const input = useRef(null)
  const wrap = useRef(null)
  const toggleBtn = useRef(null)
  const id = useId()
  const listId = `${id}-list`
  const term = clean(q)

  useEffect(() => {
    if (term.length < 2) {
      setResults([])
      setError(null)
      return
    }
    let live = true
    const t = setTimeout(async () => {
      const { data, error } = await supabase
        .from('companies')
        .select('symbol,name,status')
        .or(`symbol.ilike.${term}*,name.ilike.*${term}*`)
        .order('status')
        .order('symbol')
        .limit(8)
      if (!live) return
      if (error) console.error('company search failed', error)
      setError(error ? error.message : null)
      setResults(data || [])
      setActive(-1)
      setOpen(true)
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [term])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && !typing(document.activeElement) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        setExpanded(true)
        requestAnimationFrame(() => input.current?.focus())
      }
    }
    const onDown = (e) => { if (!wrap.current?.contains(e.target)) { setOpen(false); setExpanded(false) } }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [])

  function go(c) {
    window.location.hash = companyHref(c.symbol)
    setQ('')
    setOpen(false)
    setExpanded(false)
    input.current?.blur()
  }

  function onKeyDown(e) {
    const n = results.length
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      if (n) setActive((a) => (a + 1) % n)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (n) setActive((a) => (a <= 0 ? n - 1 : a - 1))
    } else if (e.key === 'Enter') {
      const pick = results[active >= 0 ? active : 0]
      if (open && pick) { e.preventDefault(); go(pick) }
    } else if (e.key === 'Escape') {
      if (open) setOpen(false)
      else if (q) setQ('')
      else if (expanded) { setExpanded(false); toggleBtn.current?.focus() }
    }
  }

  const showList = open && term.length >= 2
  return (
    <div className={`search${expanded ? ' is-expanded' : ''}`} ref={wrap}>
      <button ref={toggleBtn} type="button" className="search-toggle" aria-label="Search companies"
              aria-expanded={expanded}
              onClick={() => { setExpanded(true); requestAnimationFrame(() => input.current?.focus()) }}>
        <SearchIcon />
      </button>
      <div className="search-field">
        <SearchIcon />
        <label htmlFor={`${id}-q`} className="sr-only">Search company or symbol</label>
        <input
          ref={input}
          id={`${id}-q`}
          type="search"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showList}
          aria-controls={listId}
          aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
          placeholder="Search company or symbol"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => term.length >= 2 && setOpen(true)}
          onKeyDown={onKeyDown}
          autoComplete="off"
          spellCheck="false"
        />
        <kbd className="search-kbd" aria-hidden="true">/</kbd>
      </div>
      <div className="search-pop" hidden={!showList}>
        {error ? <p className="search-msg tone-neg" role="alert">Search failed.</p>
          : results.length === 0 ? <p className="search-msg">No match.</p> : null}
        <ul id={listId} role="listbox" aria-label="Matching companies" hidden={results.length === 0}>
          {results.map((c, i) => (
            <li key={c.symbol} id={`${id}-opt-${i}`} role="option" aria-selected={i === active}
                className={i === active ? 'is-active' : undefined}
                onMouseDown={(e) => e.preventDefault()} onClick={() => go(c)}
                onMouseEnter={() => setActive(i)}>
              <span className="mono search-sym">{c.symbol}</span>
              <span className="search-name">{c.name}</span>
              {c.status === 'delisted' && <Badge tone="neutral">Delisted</Badge>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="search-icon">
      <circle cx="7" cy="7" r="4.8" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.6 10.6 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}
